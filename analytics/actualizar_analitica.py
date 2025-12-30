# analytics/actualizar_analitica.py
import os
import json
import logging
import boto3
from datetime import datetime, timedelta, timezone
from boto3.dynamodb.conditions import Key
from decimal import Decimal
from utils import (
    success_response,
    error_response,
    log_request,
    get_lima_datetime,
    get_tenant_id_from_jwt,
    get_codigo_usuario_from_jwt
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB
dynamodb = boto3.resource('dynamodb')
analitica_table = dynamodb.Table(os.environ['ANALITICA_TABLE'])
ventas_table = dynamodb.Table(os.environ['VENTAS_TABLE'])
productos_table = dynamodb.Table(os.environ['PRODUCTOS_TABLE'])
usuarios_table = dynamodb.Table(os.environ['USUARIOS_TABLE'])
gastos_table = dynamodb.Table(os.environ['GASTOS_TABLE'])

# SNS y Lambda
sns = boto3.client('sns')
lambda_client = boto3.client('lambda')

ALERTAS_TOPIC_ARN = os.environ.get('ALERTAS_SNS_TOPIC_ARN')

def handler(event, context):
    """
    POST /analitica
    
    Calcula y guarda métricas agregadas por tienda/fecha.
    Emite alertas en SNS AlertasSAAI + WebSocket.
    
    Request: { "body": { "fecha": "2025-11-08" } }
    Response: { "success": true, "message": "Analítica actualizada" }
    """
    try:
        log_request(event)
        
        # JWT validation + tenant
        tenant_id = get_tenant_id_from_jwt(event)
        codigo_usuario = get_codigo_usuario_from_jwt(event)
        
        # Parse body
        body = json.loads(event.get('body', '{}'))
        fecha_param = body.get('fecha')
        
        # Fecha de cálculo (default: hoy)
        lima_now = get_lima_datetime()
        if fecha_param:
            try:
                fecha_calc = datetime.strptime(fecha_param, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            except ValueError:
                return error_response("Formato de fecha inválido. Use YYYY-MM-DD", 400)
        else:
            fecha_calc = lima_now
        
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
        
        # 3. INVENTARIO actual
        inventario_actual = calcular_inventario_actual(tenant_id)
        
        # 4. USUARIOS de la tienda
        usuarios_tienda = calcular_usuarios_tienda(tenant_id)
        
        # 5. PRODUCTOS TOP (más vendidos del período)
        productos_top = calcular_productos_top(tenant_id, fecha_inicio, fecha_fin)
        
        # 6. VENTAS DIARIAS del período
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
            "updated_at": lima_now.isoformat()
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
        if ventas_hoy and ventas_hoy.get('ingresos', 0) < 50:
            alertas.append({
                "tipo": "gananciaDiaBaja",
                "severidad": "INFO",
                "mensaje": f"Ganancia del día baja: S/ {ventas_hoy['ingresos']:.2f}"
            })
        
        # Alerta: Producto top sin stock
        if productos_top:
            producto_mas_vendido = productos_top[0]
            stock_producto = obtener_stock_producto(tenant_id, producto_mas_vendido['codigo_producto'])
            if stock_producto == 0:
                alertas.append({
                    "tipo": "productoTopSinStock",
                    "severidad": "INFO",
                    "mensaje": f"Producto más vendido sin stock: {producto_mas_vendido['nombre']}"
                })
        
        analitica_data["alertas_detectadas"] = alertas
        
        # =================================================================
        # GUARDAR EN t_analitica
        # =================================================================
        entity_id = f"{fecha_inicio.strftime('%Y-%m-%d')}_{fecha_fin.strftime('%Y-%m-%d')}"
        
        analitica_table.put_item(Item={
            'tenant_id': tenant_id,
            'entity_id': entity_id,
            'data': json.loads(json.dumps(analitica_data, default=decimal_default))
        })
        
        logger.info(f"✅ Analítica guardada: {entity_id}")
        
        # =================================================================
        # PUBLICAR ALERTAS EN SNS
        # =================================================================
        if ALERTAS_TOPIC_ARN and alertas:
            await_publiar_alertas_sns(tenant_id, alertas, codigo_usuario)
        
        # =================================================================
        # EMITIR EVENTO WEBSOCKET
        # =================================================================
        try:
            lambda_client.invoke(
                FunctionName=f"{os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'saai-backend-dev')}-EmitirEventosWs",
                InvocationType='Event',
                Payload=json.dumps({
                    'tenant_id': tenant_id,
                    'evento_tipo': 'analitica_actualizada',
                    'timestamp': lima_now.isoformat(),
                    'data': {'fecha': fecha_str}
                })
            )
            logger.info(f"📡 WebSocket event emitido: analitica_actualizada")
        except Exception as ws_error:
            logger.error(f"Error emitiendo WebSocket: {str(ws_error)}")
            # No fallar por WebSocket
        
        return success_response("Analítica actualizada")
        
    except Exception as e:
        logger.error(f"Error actualizando analítica: {str(e)}")
        return error_response("Error interno del servidor", 500)

# =================================================================
# FUNCIONES DE CÁLCULO
# =================================================================

def calcular_ventas_periodo(tenant_id, fecha_inicio, fecha_fin):
    """Calcula métricas de ventas para el período"""
    try:
        # Query ventas del período
        response = ventas_table.query(
            IndexName='tenant-created-index',  # Asume GSI por fecha
            KeyConditionExpression=Key('tenant_id').eq(tenant_id),
            FilterExpression='#data.#fecha BETWEEN :inicio AND :fin AND #data.#estado = :estado',
            ExpressionAttributeNames={
                '#data': 'data',
                '#fecha': 'fecha',
                '#estado': 'estado'
            },
            ExpressionAttributeValues={
                ':inicio': fecha_inicio.strftime('%Y-%m-%d'),
                ':fin': fecha_fin.strftime('%Y-%m-%d'),
                ':estado': 'ACTIVO'
            }
        )
        
        ventas = response.get('Items', [])
        total_ventas = len(ventas)
        total_ingresos = sum(float(v['data'].get('total', 0)) for v in ventas)
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
    """Calcula métricas de gastos para el período"""
    try:
        response = gastos_table.query(
            KeyConditionExpression=Key('tenant_id').eq(tenant_id),
            FilterExpression='#data.#fecha BETWEEN :inicio AND :fin AND #data.#estado = :estado',
            ExpressionAttributeNames={
                '#data': 'data',
                '#fecha': 'fecha',
                '#estado': 'estado'
            },
            ExpressionAttributeValues={
                ':inicio': fecha_inicio.strftime('%Y-%m-%d'),
                ':fin': fecha_fin.strftime('%Y-%m-%d'),
                ':estado': 'ACTIVO'
            }
        )
        
        gastos = response.get('Items', [])
        total_gastos = len(gastos)
        total_egresos = sum(float(g['data'].get('monto', 0)) for g in gastos)
        
        # Balance = ingresos - egresos (necesita ventas)
        ventas_periodo = calcular_ventas_periodo(tenant_id, fecha_inicio, fecha_fin)
        balance = ventas_periodo['total_ingresos'] - total_egresos
        
        return {
            "total_gastos": total_gastos,
            "total_egresos": round(total_egresos, 2),
            "balance": round(balance, 2)
        }
        
    except Exception as e:
        logger.error(f"Error calculando gastos período: {str(e)}")
        return {"total_gastos": 0, "total_egresos": 0.0, "balance": 0.0}

def calcular_inventario_actual(tenant_id):
    """Calcula métricas de inventario actual"""
    try:
        response = productos_table.query(
            KeyConditionExpression=Key('tenant_id').eq(tenant_id),
            FilterExpression='#data.#estado = :estado',
            ExpressionAttributeNames={
                '#data': 'data',
                '#estado': 'estado'
            },
            ExpressionAttributeValues={
                ':estado': 'ACTIVO'
            }
        )
        
        productos = response.get('Items', [])
        total_productos = len(productos)
        productos_sin_stock = 0
        productos_bajo_stock = 0
        valor_total = 0
        
        for producto in productos:
            data = producto['data']
            stock = int(data.get('stock', 0))
            precio = float(data.get('precio', 0))
            
            valor_total += stock * precio
            
            if stock == 0:
                productos_sin_stock += 1
            elif stock <= 5:  # Umbral stock bajo
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
    """Calcula usuarios activos por rol"""
    try:
        response = usuarios_table.query(
            KeyConditionExpression=Key('tenant_id').eq(tenant_id),
            FilterExpression='#data.#estado = :estado',
            ExpressionAttributeNames={
                '#data': 'data',
                '#estado': 'estado'
            },
            ExpressionAttributeValues={
                ':estado': 'ACTIVO'
            }
        )
        
        usuarios = response.get('Items', [])
        administradores = 0
        trabajadores = 0
        
        for usuario in usuarios:
            role = usuario['data'].get('role', '')
            if role == 'admin':
                administradores += 1
            elif role == 'worker':
                trabajadores += 1
        
        return {
            "administradores": administradores,
            "trabajadores": trabajadores
        }
        
    except Exception as e:
        logger.error(f"Error calculando usuarios: {str(e)}")
        return {"administradores": 0, "trabajadores": 0}

def calcular_productos_top(tenant_id, fecha_inicio, fecha_fin):
    """Calcula productos más vendidos del período"""
    try:
        # Query ventas del período
        response = ventas_table.query(
            KeyConditionExpression=Key('tenant_id').eq(tenant_id),
            FilterExpression='#data.#fecha BETWEEN :inicio AND :fin AND #data.#estado = :estado',
            ExpressionAttributeNames={
                '#data': 'data',
                '#fecha': 'fecha',
                '#estado': 'estado'
            },
            ExpressionAttributeValues={
                ':inicio': fecha_inicio.strftime('%Y-%m-%d'),
                ':fin': fecha_fin.strftime('%Y-%m-%d'),
                ':estado': 'ACTIVO'
            }
        )
        
        ventas = response.get('Items', [])
        productos_vendidos = {}
        
        # Contabilizar productos vendidos
        for venta in ventas:
            productos = venta['data'].get('productos', [])
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
    """Calcula ventas por día del período"""
    try:
        # Query ventas del período
        response = ventas_table.query(
            KeyConditionExpression=Key('tenant_id').eq(tenant_id),
            FilterExpression='#data.#fecha BETWEEN :inicio AND :fin AND #data.#estado = :estado',
            ExpressionAttributeNames={
                '#data': 'data',
                '#fecha': 'fecha',
                '#estado': 'estado'
            },
            ExpressionAttributeValues={
                ':inicio': fecha_inicio.strftime('%Y-%m-%d'),
                ':fin': fecha_fin.strftime('%Y-%m-%d'),
                ':estado': 'ACTIVO'
            }
        )
        
        ventas = response.get('Items', [])
        ventas_por_dia = {}
        
        # Agrupar ventas por día
        for venta in ventas:
            fecha_venta = venta['data'].get('fecha', '')[:10]  # YYYY-MM-DD
            total = float(venta['data'].get('total', 0))
            
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
    """Obtiene stock actual de un producto"""
    try:
        response = productos_table.get_item(
            Key={'tenant_id': tenant_id, 'entity_id': codigo_producto}
        )
        
        if 'Item' in response:
            return int(response['Item']['data'].get('stock', 0))
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
                    'ts': {'DataType': 'String', 'StringValue': get_lima_datetime().isoformat()}
                }
            )
            
            logger.info(f"📤 Alerta SNS publicada: {alerta['tipo']} - {alerta['severidad']}")
    
    except Exception as e:
        logger.error(f"Error publicando alertas SNS: {str(e)}")

def decimal_default(obj):
    """Serialización Decimal para JSON"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")