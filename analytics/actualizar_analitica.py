# analytics/actualizar_analitica.py
import os
import json
import logging
import boto3
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from utils import (
    success_response,
    error_response,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims,
    obtener_fecha_hora_peru,
    query_by_tenant,
    put_item_standard,
    get_item_standard
)
from utils.datetime_utils import PERU_TIMEZONE
from constants import THRESHOLD_GANANCIA_BAJA, THRESHOLD_STOCK_BAJO

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Clientes AWS
sns = boto3.client('sns')
lambda_client = boto3.client('lambda')

ALERTAS_TOPIC_ARN = os.environ.get('ALERTAS_SNS_TOPIC_ARN')

def handler(event, context):
    """
    EventBridge automático cada 4 horas (NO es endpoint público)
    
    Procesa TODAS las tiendas activas del sistema.
    Para cada tienda, calcula y guarda métricas agregadas para 3 periodos: dia, semana, mes.
    Emite alertas en SNS AlertasSAAI + notificación WebSocket mínima por tienda.
    
    ARQUITECTURA:
    - EventBridge trigger (cada 4h) → NO envía tenant_id
    - Lambda consulta t_tiendas (tenant_id="SAAI") → obtiene todas las tiendas
    - Filtra por estado="ACTIVA"
    - Itera sobre cada tienda y calcula 3 periodos
    
    Request EventBridge: { "source": "aws.events" }
    Response: { "success": true, "mensaje": "Analítica actualizada para N tiendas" }
    """
    try:
        # Detectar si viene de EventBridge
        is_eventbridge = event.get('source') == 'aws.events' or 'detail-type' in event
        
        if not is_eventbridge:
            # Este endpoint NO debe ser llamado manualmente desde API Gateway
            logger.warning("⚠️ ActualizarAnalitica llamado desde API Gateway (solo debe ejecutarse desde EventBridge)")
            return error_response("Este endpoint solo se ejecuta automáticamente desde EventBridge", 403)
        
        # Fecha de cálculo (hoy) - usar hora de Perú
        fecha_calc = datetime.now(PERU_TIMEZONE)
        fecha_str = fecha_calc.strftime('%Y-%m-%d')
        
        logger.info(f"🔄 Iniciando cálculo de analítica para TODAS las tiendas activas - Fecha {fecha_str}")
        
        # =================================================================
        # OBTENER TODAS LAS TIENDAS ACTIVAS
        # =================================================================
        try:
            result_tiendas = query_by_tenant(
                os.environ['TIENDAS_TABLE'],
                tenant_id='SAAI',  # Todas las tiendas están bajo tenant_id="SAAI"
                include_inactive=True  # Incluimos todas para filtrar manualmente
            )
            
            todas_tiendas = result_tiendas.get('items', [])
            
            # Filtrar solo tiendas ACTIVAS
            tiendas_activas = [
                t for t in todas_tiendas 
                if t.get('estado') == 'ACTIVA'
            ]
            
            logger.info(f"📊 Tiendas encontradas: {len(todas_tiendas)} total, {len(tiendas_activas)} activas")
            
            if not tiendas_activas:
                logger.warning("⚠️ No hay tiendas activas para procesar")
                return success_response(
                    mensaje="No hay tiendas activas para procesar analítica",
                    data={"tiendas_procesadas": 0}
                )
                
        except Exception as e_tiendas:
            logger.error(f"❌ Error consultando tiendas: {str(e_tiendas)}")
            return error_response("Error consultando tiendas", 500)
        
        # =================================================================
        # ITERAR SOBRE CADA TIENDA ACTIVA
        # =================================================================
        tiendas_procesadas = 0
        total_periodos_guardados = 0
        
        for tienda in tiendas_activas:
            tenant_id = tienda.get('codigo_tienda')
            
            if not tenant_id:
                logger.warning(f"⚠️ Tienda sin codigo_tienda: {tienda.get('entity_id')}")
                continue
            
            logger.info(f"\n🏪 Procesando tienda: {tenant_id}")
            
            # Calcular y guardar los 3 periodos para esta tienda
            periodos = [
                {'nombre': 'dia', 'dias': 1},
                {'nombre': 'semana', 'dias': 7},
                {'nombre': 'mes', 'dias': 30}
            ]
            
            resultados_guardados = 0
            alertas_semana = []
            
            for periodo_info in periodos:
                periodo_nombre = periodo_info['nombre']
                dias_periodo = periodo_info['dias']
                
                logger.info(f"  📊 Procesando periodo '{periodo_nombre}' ({dias_periodo} días)")
                
                # Período de análisis
                fecha_fin = fecha_calc
                if dias_periodo == 1:
                    fecha_inicio = fecha_calc
                else:
                    fecha_inicio = fecha_calc - timedelta(days=dias_periodo - 1)
            
                # =================================================================
                # CÁLCULOS DE ANALÍTICA
                # =================================================================
                
                # 1. VENTAS del período
                ventas_periodo = calcular_ventas_periodo(tenant_id, fecha_inicio, fecha_fin)
                
                # 2. GASTOS del período
                gastos_periodo = calcular_gastos_periodo(tenant_id, fecha_inicio, fecha_fin)
                
                # 3. GASTOS DIARIOS del período
                gastos_diarios = calcular_gastos_diarios(tenant_id, fecha_inicio, fecha_fin)
                
                # 4. Calcular BALANCE (ingresos - egresos)
                balance = ventas_periodo['total_ingresos'] - gastos_periodo['total_egresos']
                gastos_periodo['balance'] = round(balance, 2)
                
                # 5. INVENTARIO actual (solo para dia y semana, no mes para optimizar)
                if periodo_nombre in ['dia', 'semana']:
                    inventario_actual = calcular_inventario_actual(tenant_id)
                else:
                    inventario_actual = {"total_productos": 0, "productos_sin_stock": 0, "productos_bajo_stock": 0, "valor_total": 0.0}
                
                # 6. USUARIOS de la tienda (solo para semana, no repetir)
                if periodo_nombre == 'semana':
                    usuarios_tienda = calcular_usuarios_tienda(tenant_id)
                else:
                    usuarios_tienda = {"administradores": 0, "trabajadores": 0}
                
                # 7. PRODUCTOS TOP (más vendidos del período)
                productos_top = calcular_productos_top(tenant_id, fecha_inicio, fecha_fin)
                
                # 8. VENTAS DIARIAS del período
                ventas_diarias = calcular_ventas_diarias(tenant_id, fecha_inicio, fecha_fin)
                
                # 9. VENTAS POR TRABAJADOR del período
                ventas_por_trabajador = calcular_ventas_por_trabajador(tenant_id, fecha_inicio, fecha_fin)
                
                # Construir resultado analítico (convertir floats a Decimal)
                analitica_data = {
                    "periodo": {
                        "tipo": periodo_nombre,
                        "fecha_inicio": fecha_inicio.strftime('%Y-%m-%d'),
                        "fecha_fin": fecha_fin.strftime('%Y-%m-%d'),
                        "dias": dias_periodo
                    },
                    "ventas": convert_floats_to_decimal(ventas_periodo),
                    "gastos": convert_floats_to_decimal(gastos_periodo),
                    "inventario": convert_floats_to_decimal(inventario_actual),
                    "usuarios": usuarios_tienda,
                    "productos_top": productos_top,
                    "ventas_diarias": [convert_floats_to_decimal(v) for v in ventas_diarias],
                    "gastos_diarios": [convert_floats_to_decimal(g) for g in gastos_diarios],
                    "ventas_por_trabajador": [convert_floats_to_decimal(v) for v in ventas_por_trabajador],
                    "alertas_detectadas": [],
                    "updated_at": obtener_fecha_hora_peru()
                }
                
                # =================================================================
                # DETECCIÓN DE ALERTAS (solo para periodo 'semana')
                # =================================================================
                if periodo_nombre == 'semana':
                    # Alerta: Total ventas = 0
                    if ventas_periodo['total_ventas'] == 0:
                        alertas_semana.append({
                            "tipo": "totalventas_0",
                            "severidad": "CRITICAL", 
                            "mensaje": "No se registraron ventas en la semana"
                        })
                    
                    # Alerta: Ganancia baja del día (< 50 soles)
                    ventas_hoy = next((v for v in ventas_diarias if v['fecha'] == fecha_str), None)
                    if ventas_hoy and ventas_hoy.get('ingresos', 0) < THRESHOLD_GANANCIA_BAJA:
                        alertas_semana.append({
                            "tipo": "gananciaDiaBaja",
                            "severidad": "INFO",
                            "mensaje": f"Ganancia del día baja: S/ {ventas_hoy['ingresos']:.2f}"
                        })
                    
                    # Alerta: Producto top sin stock o stock bajo
                    if productos_top:
                        producto_mas_vendido = productos_top[0]
                        stock_producto = obtener_stock_producto(tenant_id, producto_mas_vendido['codigo_producto'])
                        if stock_producto == 0:
                            alertas_semana.append({
                                "tipo": "productoTopSinStock",
                                "severidad": "INFO",
                                "mensaje": f"Producto más vendido sin stock: {producto_mas_vendido['nombre']}"
                            })
                        elif stock_producto <= THRESHOLD_STOCK_BAJO:
                            alertas_semana.append({
                                "tipo": "productoTopStockBajo",
                                "severidad": "INFO",
                                "mensaje": f"Producto más vendido con stock bajo: {producto_mas_vendido['nombre']} ({stock_producto} unidades)"
                            })
                    
                    analitica_data["alertas_detectadas"] = alertas_semana
                
                # =================================================================
                # GUARDAR EN t_analitica
                # =================================================================
                entity_id = periodo_nombre  # 'dia', 'semana', 'mes'
                
                success = put_item_standard(
                    table_name=os.environ['ANALITICA_TABLE'],
                    tenant_id=tenant_id,
                    entity_id=entity_id,
                    data=analitica_data
                )
            
            if success:
                logger.info(f"  ✅ Analítica guardada: {periodo_nombre}")
                resultados_guardados += 1
            else:
                logger.error(f"  ❌ Error guardando analítica: {periodo_nombre}")
        
            # Fin del loop de periodos para esta tienda
        
            # =================================================================
            # PUBLICAR ALERTAS EN SNS (solo las de semana Y solo las NUEVAS)
            # =================================================================
            if ALERTAS_TOPIC_ARN and alertas_semana:
                # Obtener analítica anterior para comparar alertas
                try:
                    analitica_anterior = get_item_standard(
                        table_name=os.environ['ANALITICA_TABLE'],
                        tenant_id=tenant_id,
                        entity_id='semana'
                    )
                    
                    # Extraer tipos de alertas anteriores
                    alertas_anteriores_tipos = set()
                    if analitica_anterior:
                        alertas_previas = analitica_anterior.get('alertas_detectadas', [])
                        alertas_anteriores_tipos = {a.get('tipo') for a in alertas_previas if a.get('tipo')}
                    
                    # Filtrar solo alertas NUEVAS (que no estaban en el cálculo anterior)
                    alertas_nuevas = [
                        alerta for alerta in alertas_semana
                        if alerta.get('tipo') not in alertas_anteriores_tipos
                    ]
                    
                    # Publicar solo alertas nuevas
                    if alertas_nuevas:
                        await_publiar_alertas_sns(tenant_id, alertas_nuevas, 'SYSTEM_EVENTBRIDGE')
                        logger.info(f"  📤 {len(alertas_nuevas)} alertas NUEVAS publicadas a SNS (de {len(alertas_semana)} detectadas)")
                    else:
                        logger.info(f"  ℹ️ No hay alertas nuevas para publicar ({len(alertas_semana)} ya existían)")
                
                except Exception as e_alertas:
                    # Si falla la comparación, publicar todas por seguridad
                    logger.warning(f"  ⚠️ Error comparando alertas anteriores: {str(e_alertas)}, publicando todas")
                    await_publiar_alertas_sns(tenant_id, alertas_semana, 'SYSTEM_EVENTBRIDGE')
        
            logger.info(f"  ✅ Tienda {tenant_id} completada: {resultados_guardados}/3 periodos guardados")
            total_periodos_guardados += resultados_guardados
        
            # =================================================================
            # EMITIR NOTIFICACIÓN WEBSOCKET (una por tienda)
            # =================================================================
            try:
                event_payload = {
                    'tenant_id': tenant_id,
                    'event_type': 'analitica_actualizada',
                    'payload': {
                        'timestamp': obtener_fecha_hora_peru(),
                        'mensaje': 'Analítica actualizada. Refetch datos desde /analitica'
                    }
                }
            
                lambda_client.invoke(
                    FunctionName=os.environ['EMITIR_EVENTOS_WS_FUNCTION_NAME'],
                    InvocationType='Event',
                    Payload=json.dumps(event_payload)
                )
            
                logger.info(f"  🔔 WebSocket 'analitica_actualizada' enviado para {tenant_id}")
            except Exception as ws_error:
                logger.warning(f"  ⚠️ Error enviando WebSocket para {tenant_id}: {str(ws_error)}")
            
            tiendas_procesadas += 1
        
        # Fin del loop de tiendas
        
        logger.info(f"\n✅ ANALÍTICA COMPLETA: {tiendas_procesadas} tiendas procesadas, {total_periodos_guardados} periodos guardados")
        
        return success_response(
            mensaje=f"Analítica actualizada para {tiendas_procesadas} tiendas",
            data={
                "tiendas_procesadas": tiendas_procesadas,
                "total_periodos_guardados": total_periodos_guardados
            }
        )
        
    except Exception as e:
        logger.error(f"Error actualizando analítica: {str(e)}", exc_info=True)
        return error_response("Error interno del servidor", 500)

# =================================================================
# FUNCIONES DE CÁLCULO
# =================================================================

def calcular_ventas_periodo(tenant_id, fecha_inicio, fecha_fin):
    """Calcula métricas de ventas para el período usando utils"""
    try:
        from boto3.dynamodb.conditions import Attr
        
        # Crear filtro para fechas (ventas usan estado='COMPLETADA' no 'ACTIVO')
        filter_expression = (
            Attr('data.fecha').between(
                fecha_inicio.strftime('%Y-%m-%d'), 
                fecha_fin.strftime('%Y-%m-%d')
            ) & Attr('data.estado').eq('COMPLETADA')
        )
        
        # Query usando utils
        result = query_by_tenant(
            table_name=os.environ['VENTAS_TABLE'],
            tenant_id=tenant_id,
            filter_expression=filter_expression
        )
        
        ventas = result.get('items', [])
        total_ventas = len(ventas)
        total_ingresos = sum(float(v.get('total', 0)) for v in ventas)
        
        return {
            "total_ventas": total_ventas,
            "total_ingresos": round(total_ingresos, 2)
        }
        
    except Exception as e:
        logger.error(f"Error calculando ventas período: {str(e)}")
        return {"total_ventas": 0, "total_ingresos": 0.0}

def calcular_gastos_periodo(tenant_id, fecha_inicio, fecha_fin):
    """Calcula métricas de gastos para el período usando utils"""
    try:
        from boto3.dynamodb.conditions import Attr
        
        # Crear filtro para fechas
        filter_expression = (
            Attr('data.fecha').between(
                fecha_inicio.strftime('%Y-%m-%d'), 
                fecha_fin.strftime('%Y-%m-%d')
            ) & Attr('data.estado').eq('ACTIVO')
        )
        
        # Query usando utils
        result = query_by_tenant(
            table_name=os.environ['GASTOS_TABLE'],
            tenant_id=tenant_id,
            filter_expression=filter_expression
        )
        
        gastos = result.get('items', [])
        total_gastos = len(gastos)
        total_egresos = sum(float(g.get('monto', 0)) for g in gastos)
        
        return {
            "total_gastos": total_gastos,
            "total_egresos": round(total_egresos, 2)
        }
        
    except Exception as e:
        logger.error(f"Error calculando gastos período: {str(e)}")
        return {"total_gastos": 0, "total_egresos": 0.0}

def calcular_inventario_actual(tenant_id):
    """Calcula métricas de inventario actual usando utils"""
    try:
        from boto3.dynamodb.conditions import Attr
        
        # Query productos activos usando utils
        result = query_by_tenant(
            table_name=os.environ['PRODUCTOS_TABLE'],
            tenant_id=tenant_id,
            filter_expression=Attr('data.estado').eq('ACTIVO')
        )
        
        productos = result.get('items', [])
        total_productos = len(productos)
        productos_sin_stock = 0
        productos_bajo_stock = 0
        valor_total = 0
        
        for producto in productos:
            stock = int(producto.get('stock', 0))
            precio = float(producto.get('precio', 0))
            
            valor_total += stock * precio
            
            if stock == 0:
                productos_sin_stock += 1
            elif stock <= THRESHOLD_STOCK_BAJO:
                productos_bajo_stock += 1
        
        return {
            "total_productos": total_productos,
            "productos_sin_stock": productos_sin_stock,
            "productos_bajo_stock": productos_bajo_stock,
            "valor_total": round(valor_total, 2)
        }
        
    except Exception as e:
        logger.error(f"Error calculando inventario: {str(e)}")
        return {"total_productos": 0, "productos_sin_stock": 0, "productos_bajo_stock": 0, "valor_total": 0.0}

def calcular_usuarios_tienda(tenant_id):
    """Calcula usuarios activos por rol usando utils"""
    try:
        from boto3.dynamodb.conditions import Attr
        
        # Query usuarios activos usando utils
        result = query_by_tenant(
            table_name=os.environ['USUARIOS_TABLE'],
            tenant_id=tenant_id,
            filter_expression=Attr('data.estado').eq('ACTIVO')
        )
        
        usuarios = result.get('items', [])
        administradores = 0
        trabajadores = 0
        
        for usuario in usuarios:
            # El rol está dentro del campo 'rol', y puede ser 'ADMIN'/'TRABAJADOR' o 'admin'/'worker'
            role = usuario.get('rol', usuario.get('role', '')).upper()
            if role in ['ADMIN', 'ADMINISTRADOR']:
                administradores += 1
            elif role in ['TRABAJADOR', 'WORKER']:
                trabajadores += 1
        
        return {
            "administradores": administradores,
            "trabajadores": trabajadores
        }
        
    except Exception as e:
        logger.error(f"Error calculando usuarios: {str(e)}")
        return {"administradores": 0, "trabajadores": 0}

def calcular_productos_top(tenant_id, fecha_inicio, fecha_fin):
    """Calcula productos más vendidos del período usando utils"""
    try:
        from boto3.dynamodb.conditions import Attr
        
        # Query ventas del período usando utils (estado COMPLETADA)
        filter_expression = (
            Attr('data.fecha').between(
                fecha_inicio.strftime('%Y-%m-%d'), 
                fecha_fin.strftime('%Y-%m-%d')
            ) & Attr('data.estado').eq('COMPLETADA')
        )
        
        result = query_by_tenant(
            table_name=os.environ['VENTAS_TABLE'],
            tenant_id=tenant_id,
            filter_expression=filter_expression
        )
        
        ventas = result.get('items', [])
        productos_vendidos = {}
        
        # Contabilizar productos vendidos
        for venta in ventas:
            productos = venta.get('productos', [])
            for producto in productos:
                codigo = producto.get('codigo_producto')
                cantidad = int(producto.get('cantidad', 0))
                
                if codigo not in productos_vendidos:
                    productos_vendidos[codigo] = {
                        'codigo_producto': codigo,
                        'nombre': producto.get('nombre', codigo),
                        'cantidad_vendida': 0
                    }
                
                productos_vendidos[codigo]['cantidad_vendida'] += cantidad
        
        # Ordenar por cantidad vendida y tomar top 5
        productos_top = sorted(productos_vendidos.values(), 
                             key=lambda x: x['cantidad_vendida'], 
                             reverse=True)[:5]
        
        return productos_top
        
    except Exception as e:
        logger.error(f"Error calculando productos top: {str(e)}")
        return []

def calcular_ventas_diarias(tenant_id, fecha_inicio, fecha_fin):
    """Calcula ventas por día del período usando utils"""
    try:
        from boto3.dynamodb.conditions import Attr
        
        # Query ventas del período usando utils (estado COMPLETADA)
        filter_expression = (
            Attr('data.fecha').between(
                fecha_inicio.strftime('%Y-%m-%d'), 
                fecha_fin.strftime('%Y-%m-%d')
            ) & Attr('data.estado').eq('COMPLETADA')
        )
        
        result = query_by_tenant(
            table_name=os.environ['VENTAS_TABLE'],
            tenant_id=tenant_id,
            filter_expression=filter_expression
        )
        
        ventas = result.get('items', [])
        ventas_por_dia = {}
        
        # Agrupar ventas por día
        for venta in ventas:
            fecha_venta = venta.get('fecha', '')[:10]  # YYYY-MM-DD
            total = float(venta.get('total', 0))
            
            if fecha_venta not in ventas_por_dia:
                ventas_por_dia[fecha_venta] = {'cantidad': 0, 'ingresos': 0}
            
            ventas_por_dia[fecha_venta]['cantidad'] += 1
            ventas_por_dia[fecha_venta]['ingresos'] += total
        
        # Convertir a lista ordenada
        ventas_diarias = []
        fecha_actual = fecha_inicio
        while fecha_actual <= fecha_fin:
            fecha_str = fecha_actual.strftime('%Y-%m-%d')
            dia_data = ventas_por_dia.get(fecha_str, {'cantidad': 0, 'ingresos': 0})
            
            ventas_diarias.append({
                'fecha': fecha_str,
                'cantidad': dia_data['cantidad'],
                'ingresos': round(dia_data['ingresos'], 2)
            })
            
            fecha_actual += timedelta(days=1)
        
        return ventas_diarias
        
    except Exception as e:
        logger.error(f"Error calculando ventas diarias: {str(e)}")
        return []

def calcular_gastos_diarios(tenant_id, fecha_inicio, fecha_fin):
    """Calcula gastos por día del período usando utils"""
    try:
        from boto3.dynamodb.conditions import Attr
        
        # Query gastos del período usando utils (estado ACTIVO)
        filter_expression = (
            Attr('data.fecha').between(
                fecha_inicio.strftime('%Y-%m-%d'), 
                fecha_fin.strftime('%Y-%m-%d')
            ) & Attr('data.estado').eq('ACTIVO')
        )
        
        result = query_by_tenant(
            table_name=os.environ['GASTOS_TABLE'],
            tenant_id=tenant_id,
            filter_expression=filter_expression
        )
        
        gastos = result.get('items', [])
        gastos_por_dia = {}
        
        # Agrupar gastos por día
        for gasto in gastos:
            fecha_gasto = gasto.get('fecha', '')[:10]  # YYYY-MM-DD
            monto = float(gasto.get('monto', 0))
            
            if fecha_gasto not in gastos_por_dia:
                gastos_por_dia[fecha_gasto] = {'cantidad': 0, 'egresos': 0}
            
            gastos_por_dia[fecha_gasto]['cantidad'] += 1
            gastos_por_dia[fecha_gasto]['egresos'] += monto
        
        # Convertir a lista ordenada
        gastos_diarios = []
        fecha_actual = fecha_inicio
        while fecha_actual <= fecha_fin:
            fecha_str = fecha_actual.strftime('%Y-%m-%d')
            dia_data = gastos_por_dia.get(fecha_str, {'cantidad': 0, 'egresos': 0})
            
            gastos_diarios.append({
                'fecha': fecha_str,
                'cantidad': dia_data['cantidad'],
                'egresos': round(dia_data['egresos'], 2)
            })
            
            fecha_actual += timedelta(days=1)
        
        return gastos_diarios
        
    except Exception as e:
        logger.error(f"Error calculando gastos diarios: {str(e)}")
        return []

def calcular_ventas_por_trabajador(tenant_id, fecha_inicio, fecha_fin):
    """Calcula ventas por trabajador del período usando utils"""
    try:
        from boto3.dynamodb.conditions import Attr
        
        # Query ventas del período usando utils (estado COMPLETADA)
        filter_expression = (
            Attr('data.fecha').between(
                fecha_inicio.strftime('%Y-%m-%d'), 
                fecha_fin.strftime('%Y-%m-%d')
            ) & Attr('data.estado').eq('COMPLETADA')
        )
        
        result = query_by_tenant(
            table_name=os.environ['VENTAS_TABLE'],
            tenant_id=tenant_id,
            filter_expression=filter_expression
        )
        
        ventas = result.get('items', [])
        trabajadores = {}
        
        # Contabilizar ventas por trabajador
        for venta in ventas:
            codigo_usuario = venta.get('codigo_usuario')
            total = float(venta.get('total', 0))
            
            if not codigo_usuario:
                continue
            
            if codigo_usuario not in trabajadores:
                trabajadores[codigo_usuario] = {
                    'codigo_usuario': codigo_usuario,
                    'nombre_usuario': None,
                    'total_ventas': 0,
                    'total_ingresos': 0
                }
            
            trabajadores[codigo_usuario]['total_ventas'] += 1
            trabajadores[codigo_usuario]['total_ingresos'] += total
        
        # Obtener nombres de trabajadores de t_usuarios
        for codigo_usuario in trabajadores.keys():
            try:
                usuario_data = get_item_standard(
                    table_name=os.environ['USUARIOS_TABLE'],
                    tenant_id=tenant_id,
                    entity_id=codigo_usuario
                )
                
                if usuario_data:
                    rol = usuario_data.get('rol', usuario_data.get('role', '')).upper()
                    # Solo incluir trabajadores (filtrar admins)
                    if rol in ['TRABAJADOR', 'WORKER']:
                        nombre = usuario_data.get('nombre', codigo_usuario)
                        trabajadores[codigo_usuario]['nombre_usuario'] = nombre
                    else:
                        # Marcar para eliminar si no es trabajador
                        trabajadores[codigo_usuario] = None
            except Exception as e:
                logger.warning(f"Error obteniendo usuario {codigo_usuario}: {str(e)}")
                trabajadores[codigo_usuario]['nombre_usuario'] = codigo_usuario
        
        # Filtrar trabajadores None (admins) y ordenar por total_ventas
        trabajadores_validos = [
            t for t in trabajadores.values() 
            if t is not None
        ]
        
        trabajadores_ordenados = sorted(
            trabajadores_validos,
            key=lambda x: x['total_ventas'],
            reverse=True
        )
        
        # Redondear ingresos
        for trabajador in trabajadores_ordenados:
            trabajador['total_ingresos'] = round(trabajador['total_ingresos'], 2)
        
        return trabajadores_ordenados
        
    except Exception as e:
        logger.error(f"Error calculando ventas por trabajador: {str(e)}")
        return []

def obtener_stock_producto(tenant_id, codigo_producto):
    """Obtiene stock actual de un producto usando utils"""
    try:
        producto_data = get_item_standard(
            table_name=os.environ['PRODUCTOS_TABLE'],
            tenant_id=tenant_id,
            entity_id=codigo_producto
        )
        
        if producto_data:
            return int(producto_data.get('stock', 0))
        return 0
        
    except Exception as e:
        logger.error(f"Error obteniendo stock producto {codigo_producto}: {str(e)}")
        return 0

def convert_floats_to_decimal(obj):
    """Convierte recursivamente floats a Decimal para DynamoDB"""
    if isinstance(obj, dict):
        return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimal(i) for i in obj]
    elif isinstance(obj, float):
        return Decimal(str(obj))
    return obj

def await_publiar_alertas_sns(tenant_id, alertas, codigo_usuario):
    """Publica alertas en SNS AlertasSAAI"""
    try:
        for alerta in alertas:
            message_body = {
                "titulo": f"Alerta Analitica: {alerta['tipo']}",
                "mensaje": alerta['mensaje'],
                "detalle": {
                    "tipo_calculo": "analitica_automatica",
                    "ejecutado_por": codigo_usuario
                }
            }
            
            # Publicar en SNS
            sns.publish(
                TopicArn=ALERTAS_TOPIC_ARN,
                Message=json.dumps(message_body),
                MessageAttributes={
                    'tenant_id': {'DataType': 'String', 'StringValue': tenant_id},
                    'tipo': {'DataType': 'String', 'StringValue': alerta['tipo']},
                    'severidad': {'DataType': 'String', 'StringValue': alerta['severidad']},
                    'origen': {'DataType': 'String', 'StringValue': 'actualizarAnalitica'},
                    'ts': {'DataType': 'String', 'StringValue': obtener_fecha_hora_peru()}
                }
            )
            
            logger.info(f"📤 Alerta SNS publicada: {alerta['tipo']} - {alerta['severidad']}")
    
    except Exception as e:
        logger.error(f"Error publicando alertas SNS: {str(e)}")
