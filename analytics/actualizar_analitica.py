# analytics/actualizar_analitica.py
import os
import json
import logging
import boto3
from datetime import datetime, timedelta, timezone
from utils import (
    success_response,
    error_response,
    parse_request_body,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims,
    obtener_fecha_hora_peru,
    query_by_tenant,
    put_item_standard,
    get_item_standard
)
from constants import THRESHOLD_GANANCIA_BAJA, THRESHOLD_STOCK_BAJO

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Clientes AWS
sns = boto3.client('sns')
lambda_client = boto3.client('lambda')

ALERTAS_TOPIC_ARN = os.environ.get('ALERTAS_SNS_TOPIC_ARN')

def handler(event, context):
    """
    POST /analitica
    
    Calcula y guarda métricas agregadas por tienda/fecha.
    Emite alertas en SNS AlertasSAAI + notificación WebSocket mínima.
    
    NOTA: Este endpoint normalmente se ejecuta automáticamente cada 4 horas
    mediante EventBridge, no por acción directa del usuario.
    
    Request: { "body": { "fecha": "2025-11-08" } }
    Response: { "success": true, "message": "Analítica actualizada" }
    """
    try:
        # JWT validation + tenant
        tenant_id = extract_tenant_from_jwt_claims(event)
        user_info = extract_user_from_jwt_claims(event)
        codigo_usuario = user_info.get('codigo_usuario') if user_info else None
        
        if not tenant_id or not codigo_usuario:
            return error_response("Token inválido - datos faltantes", 401)
        
        # Parse body
        body = parse_request_body(event)
        fecha_param = body.get('fecha')
        
        # Fecha de cálculo (default: hoy)
        lima_now = obtener_fecha_hora_peru()
        if fecha_param:
            try:
                fecha_calc = datetime.strptime(fecha_param, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            except ValueError:
                return error_response("Formato de fecha inválido. Use YYYY-MM-DD", 400)
        else:
            fecha_calc = datetime.now(timezone.utc)
        
        fecha_str = fecha_calc.strftime('%Y-%m-%d')
        
        logger.info(f"🧮 Calculando analítica para tienda {tenant_id}, fecha {fecha_str}")
        
        # Período de análisis: últimos 7 días hasta fecha_calc
        fecha_fin = fecha_calc
        fecha_inicio = fecha_calc - timedelta(days=6)
        
        # =================================================================
        # CÁLCULOS DE ANALÍTICA
        # =================================================================
        
        # 1. VENTAS del período
        ventas_periodo = calcular_ventas_periodo(tenant_id, fecha_inicio, fecha_fin)
        
        # 2. GASTOS del período
        gastos_periodo = calcular_gastos_periodo(tenant_id, fecha_inicio, fecha_fin)
        
        # 3. Calcular BALANCE (ingresos - egresos)
        balance = ventas_periodo['total_ingresos'] - gastos_periodo['total_egresos']
        gastos_periodo['balance'] = round(balance, 2)
        
        # 4. INVENTARIO actual
        inventario_actual = calcular_inventario_actual(tenant_id)
        
        # 5. USUARIOS de la tienda
        usuarios_tienda = calcular_usuarios_tienda(tenant_id)
        
        # 6. PRODUCTOS TOP (más vendidos del período)
        productos_top = calcular_productos_top(tenant_id, fecha_inicio, fecha_fin)
        
        # 7. VENTAS DIARIAS del período
        ventas_diarias = calcular_ventas_diarias(tenant_id, fecha_inicio, fecha_fin)
        
        # Construir resultado analítico
        analitica_data = {
            "periodo": {
                "fecha_inicio": fecha_inicio.strftime('%Y-%m-%d'),
                "fecha_fin": fecha_fin.strftime('%Y-%m-%d'),
                "dias": 7
            },
            "ventas": ventas_periodo,
            "gastos": gastos_periodo,
            "inventario": inventario_actual,
            "usuarios": usuarios_tienda,
            "productos_top": productos_top,
            "ventas_diarias": ventas_diarias,
            "alertas_detectadas": [],
            "updated_at": obtener_fecha_hora_peru()
        }
        
        # =================================================================
        # DETECCIÓN DE ALERTAS
        # =================================================================
        alertas = []
        
        # Alerta: Total ventas = 0
        if ventas_periodo['total_ventas'] == 0:
            alertas.append({
                "tipo": "totalventas_0",
                "severidad": "CRITICAL", 
                "mensaje": "No se registraron ventas en el período"
            })
        
        # Alerta: Ganancia baja del día (< 50 soles)
        ventas_hoy = next((v for v in ventas_diarias if v['fecha'] == fecha_str), None)
        if ventas_hoy and ventas_hoy.get('ingresos', 0) < THRESHOLD_GANANCIA_BAJA:
            alertas.append({
                "tipo": "gananciaDiaBaja",
                "severidad": "INFO",
                "mensaje": f"Ganancia del día baja: S/ {ventas_hoy['ingresos']:.2f}"
            })
        
        # Alerta: Producto top sin stock o stock bajo
        if productos_top:
            producto_mas_vendido = productos_top[0]
            stock_producto = obtener_stock_producto(tenant_id, producto_mas_vendido['codigo_producto'])
            if stock_producto == 0:
                alertas.append({
                    "tipo": "productoTopSinStock",
                    "severidad": "INFO",
                    "mensaje": f"Producto más vendido sin stock: {producto_mas_vendido['nombre']}"
                })
            elif stock_producto <= THRESHOLD_STOCK_BAJO:
                alertas.append({
                    "tipo": "productoTopStockBajo",
                    "severidad": "INFO",
                    "mensaje": f"Producto más vendido con stock bajo: {producto_mas_vendido['nombre']} ({stock_producto} unidades)"
                })
        
        analitica_data["alertas_detectadas"] = alertas
        
        # =================================================================
        # GUARDAR EN t_analitica
        # =================================================================
        entity_id = f"{fecha_inicio.strftime('%Y-%m-%d')}_{fecha_fin.strftime('%Y-%m-%d')}"
        
        # Usar función estándar de utils
        success = put_item_standard(
            table_name=os.environ['ANALITICA_TABLE'],
            tenant_id=tenant_id,
            entity_id=entity_id,
            data=analitica_data
        )
        
        if not success:
            return error_response("Error guardando analítica", 500)
        
        logger.info(f"✅ Analítica guardada: {entity_id}")
        
        # =================================================================
        # PUBLICAR ALERTAS EN SNS
        # =================================================================
        if ALERTAS_TOPIC_ARN and alertas:
            await_publiar_alertas_sns(tenant_id, alertas, codigo_usuario)
        
        # =================================================================
        # EMITIR NOTIFICACIÓN WEBSOCKET (MÍNIMA)
        # =================================================================
        try:
            # Payload mínimo: solo notifica que la analítica fue actualizada
            # El frontend debe hacer refetch a GET /analitica para obtener los datos
            event_payload = {
                'tenant_id': tenant_id,
                'event_type': 'analitica_actualizada',
                'payload': {
                    'periodo': {
                        'fecha_inicio': fecha_inicio.strftime('%Y-%m-%d'),
                        'fecha_fin': fecha_fin.strftime('%Y-%m-%d')
                    },
                    'timestamp': obtener_fecha_hora_peru(),
                    'mensaje': 'Analítica actualizada. Refetch datos desde /analitica'
                }
            }
            
            lambda_client.invoke(
                FunctionName=os.environ['EMITIR_EVENTOS_WS_FUNCTION_NAME'],
                InvocationType='Event',  # Async
                Payload=json.dumps(event_payload)
            )
            
            logger.info(f"🔔 Notificación WebSocket 'analitica_actualizada' enviada (payload mínimo)")
        except Exception as ws_error:
            logger.warning(f"Error enviando notificación WebSocket: {str(ws_error)}")
            # No fallar por WebSocket
        
        return success_response("Analítica actualizada")
        
    except Exception as e:
        logger.error(f"Error actualizando analítica: {str(e)}")
        return error_response("Error interno del servidor", 500)

# =================================================================
# FUNCIONES DE CÁLCULO
# =================================================================

def calcular_ventas_periodo(tenant_id, fecha_inicio, fecha_fin):
    """Calcula métricas de ventas para el período usando utils"""
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
            table_name=os.environ['VENTAS_TABLE'],
            tenant_id=tenant_id,
            filter_expression=filter_expression
        )
        
        ventas = result.get('items', [])
        total_ventas = len(ventas)
        total_ingresos = sum(float(v.get('total', 0)) for v in ventas)
        promedio_diario = total_ventas / 7.0 if total_ventas > 0 else 0
        
        return {
            "total_ventas": total_ventas,
            "total_ingresos": round(total_ingresos, 2),
            "promedio_diario": round(promedio_diario, 1)
        }
        
    except Exception as e:
        logger.error(f"Error calculando ventas período: {str(e)}")
        return {"total_ventas": 0, "total_ingresos": 0.0, "promedio_diario": 0.0}

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
        
        # Query ventas del período usando utils
        filter_expression = (
            Attr('data.fecha').between(
                fecha_inicio.strftime('%Y-%m-%d'), 
                fecha_fin.strftime('%Y-%m-%d')
            ) & Attr('data.estado').eq('ACTIVO')
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
        
        # Query ventas del período usando utils
        filter_expression = (
            Attr('data.fecha').between(
                fecha_inicio.strftime('%Y-%m-%d'), 
                fecha_fin.strftime('%Y-%m-%d')
            ) & Attr('data.estado').eq('ACTIVO')
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

def await_publiar_alertas_sns(tenant_id, alertas, codigo_usuario):
    """Publica alertas en SNS AlertasSAAI"""
    try:
        for alerta in alertas:
            message_body = {
                "titulo": f"Alerta Analítica: {alerta['tipo']}",
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