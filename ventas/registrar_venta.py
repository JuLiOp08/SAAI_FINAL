# ventas/registrar_venta.py
import os
import json
import logging
import boto3
from decimal import Decimal
from utils import (
    success_response,
    error_response,
    validation_error_response,
    parse_request_body,
    log_request,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims,
    get_item_standard,
    put_item_standard,
    obtener_fecha_hora_peru,
    decimal_to_float,
    generar_codigo_venta
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
VENTAS_TABLE = os.environ.get('VENTAS_TABLE')
PRODUCTOS_TABLE = os.environ.get('PRODUCTOS_TABLE')
COUNTERS_TABLE = os.environ.get('COUNTERS_TABLE')

# SNS para notificaciones
SNS_TOPIC_ARN = os.environ.get('ALERTAS_SNS_TOPIC_ARN')

# WebSocket API para notificaciones en tiempo real
WEBSOCKET_API_ENDPOINT = os.environ.get('WEBSOCKET_API_ENDPOINT')

# Nombre de función Lambda para WebSocket (desde env var)
EMITIR_EVENTOS_WS_FUNCTION_NAME = os.environ.get('EMITIR_EVENTOS_WS_FUNCTION_NAME')

# Inicializar clientes AWS
sns = boto3.client('sns')
lambda_client = boto3.client('lambda')

def handler(event, context):
    """
    POST /ventas - Registrar nueva venta (descuenta stock + SNS + WebSocket)
    
    Según documento SAAI (TRABAJADOR):
    Request:
    {
        "body": {
            "productos": [
                {
                    "codigo_producto": "T002P001",
                    "cantidad": 2
                }
            ],
            "metodo_pago": "efectivo"
        }
    }
    
    Response:
    {
        "success": true,
        "message": "Venta registrada",
        "data": {
            "codigo_venta": "T002V015",
            "total": 7.0,
            "fecha": "2025-11-08T15:30:00-05:00"
        }
    }
    """
    try:
        log_request(event)
        
        # Verificar rol TRABAJADOR
        tiene_permiso, error = verificar_rol_permitido(event, ['TRABAJADOR'])
        if not tiene_permiso:
            return error
        
        # Extraer tenant_id del JWT
        tenant_id = extract_tenant_from_jwt_claims(event)
        if not tenant_id:
            return error_response("Token inválido - no se encontró codigo_tienda", 401)
        
        # Extraer usuario para auditoría
        user_data = extract_user_from_jwt_claims(event)
        codigo_usuario = user_data.get('codigo_usuario') if user_data else None
        
        # Parse request body
        body = parse_request_body(event)
        if not body:
            return validation_error_response("Request body requerido")
        
        # Validar campos obligatorios según SAAI oficial
        productos = body.get('productos')
        metodo_pago = body.get('metodo_pago')
        
        if not productos or not isinstance(productos, list) or len(productos) == 0:
            return validation_error_response("Productos es obligatorio y debe ser una lista no vacía")
        
        if not metodo_pago:
            return validation_error_response("Metodo de pago es obligatorio")
        
        # Validar productos y calcular totales (similar a calcular_monto)
        total_subtotal = Decimal('0.00')
        productos_procesados = []
        productos_a_actualizar = []
        
        for item in productos:
            codigo_producto = item.get('codigo_producto')
            cantidad = item.get('cantidad')
            
            if not codigo_producto:
                return validation_error_response("codigo_producto es obligatorio en cada item")
            
            try:
                cantidad = int(cantidad)
                if cantidad <= 0:
                    return validation_error_response("La cantidad debe ser mayor a 0")
            except (ValueError, TypeError):
                return validation_error_response("La cantidad debe ser un número entero válido")
            
            # Obtener producto
            producto_data = get_item_standard(PRODUCTOS_TABLE, tenant_id, codigo_producto)
            if not producto_data or producto_data.get('estado') != 'ACTIVO':
                return error_response(f"Producto {codigo_producto} no encontrado o inactivo", 404)
            
            # Verificar stock disponible
            stock_actual = int(producto_data.get('stock', 0))
            if stock_actual < cantidad:
                return error_response(
                    f"Stock insuficiente para producto {codigo_producto}. Disponible: {stock_actual}, Solicitado: {cantidad}",
                    400
                )
            
            precio_unitario = producto_data.get('precio', Decimal('0.00'))
            if isinstance(precio_unitario, (int, float)):
                precio_unitario = Decimal(str(precio_unitario))
            
            # Calcular subtotal del item
            subtotal_item = precio_unitario * Decimal(str(cantidad))
            total_subtotal += subtotal_item
            
            # Preparar producto procesado
            producto_procesado = {
                'codigo_producto': codigo_producto,
                'nombre_producto': producto_data.get('nombre'),
                'precio_unitario': precio_unitario,
                'cantidad': cantidad,
                'subtotal_item': subtotal_item
            }
            
            productos_procesados.append(producto_procesado)
            
            # Preparar actualización de stock
            producto_actualizado = producto_data.copy()
            producto_actualizado['stock'] = stock_actual - cantidad
            producto_actualizado['updated_at'] = obtener_fecha_hora_peru()
            if codigo_usuario:
                producto_actualizado['updated_by'] = codigo_usuario
            
            productos_a_actualizar.append((codigo_producto, producto_actualizado))
        
        # Calcular total (sin IGV según documentación oficial SAAI)
        total = total_subtotal
        
        # Generar código de venta usando función de utils
        codigo_venta = generar_codigo_venta(tenant_id)
        
        # Crear entidad venta
        fecha_actual = obtener_fecha_hora_peru()
        
        venta_data = {
            'codigo_venta': codigo_venta,
            'productos': [  # Cambiar de 'items' a 'productos'
                {
                    'codigo_producto': producto['codigo_producto'],
                    'nombre_producto': producto['nombre_producto'],
                    'precio_unitario': producto['precio_unitario'],
                    'cantidad': producto['cantidad'],
                    'subtotal_item': producto['subtotal_item']
                }
                for producto in productos_procesados
            ],
            'total': total,  # Solo total, sin IGV
            'metodo_pago': str(metodo_pago).strip(),
            'fecha': obtener_fecha_hora_peru()[:10],  # Solo fecha YYYY-MM-DD
            'estado': 'COMPLETADA',
            'created_at': fecha_actual,
            'updated_at': fecha_actual
        }
        
        # Agregar auditoría si hay usuario
        if codigo_usuario:
            venta_data['codigo_usuario'] = codigo_usuario
            venta_data['created_by'] = codigo_usuario
        
        # Guardar venta en DynamoDB
        put_item_standard(
            VENTAS_TABLE,
            tenant_id=tenant_id,
            entity_id=codigo_venta,
            data=venta_data
        )
        
        # Actualizar stock de productos
        for codigo_producto, producto_actualizado in productos_a_actualizar:
            put_item_standard(
                PRODUCTOS_TABLE,
                tenant_id=tenant_id,
                entity_id=codigo_producto,
                data=producto_actualizado
            )
            
            logger.info(f"Stock actualizado para producto {codigo_producto}: nuevo stock = {producto_actualizado['stock']}")
        
        # Enviar notificación SNS
        try:
            sns_message = {
                'tipo': 'venta_realizada',
                'codigo_tienda': tenant_id,
                'codigo_venta': codigo_venta,
                'total': decimal_to_float(total),
                'fecha': fecha_actual,
                'trabajador': codigo_usuario or 'SISTEMA'
            }
            
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Message=json.dumps(sns_message),
                Subject=f"Nueva venta registrada - {codigo_venta}"
            )
            
            logger.info(f"Notificación SNS enviada para venta {codigo_venta}")
            
        except Exception as sns_error:
            logger.warning(f"Error enviando notificación SNS: {str(sns_error)}")
        
        # Enviar evento WebSocket en tiempo real
        try:
            # Invocar función emitir_eventos_ws para broadcasting
            lambda_client = boto3.client('lambda')
            
            event_payload = {
                'tenant_id': tenant_id,
                'event_type': 'venta_registrada',
                'payload': {
                    'codigo_venta': codigo_venta,
                    'items_count': len(productos_procesados),
                    'metodo_pago': metodo_pago,
                    'trabajador': codigo_usuario or 'SISTEMA',
                    'fecha': fecha_actual,
                    'productos_vendidos': [
                        {
                            'codigo': producto['codigo_producto'],
                            'nombre': producto['nombre_producto'],
                            'cantidad': producto['cantidad'],
                            'subtotal': decimal_to_float(producto['subtotal_item'])
                        }
                        for producto in productos_procesados
                    ]
                }
            }
            
            lambda_client.invoke(
                FunctionName=EMITIR_EVENTOS_WS_FUNCTION_NAME,
                InvocationType='Event',  # Async
                Payload=json.dumps(event_payload)
            )
            
            logger.info(f"Evento WebSocket 'venta_registrada' enviado para {codigo_venta}")
                
        except Exception as ws_error:
            logger.warning(f"Error enviando evento WebSocket: {str(ws_error)}")
        
        logger.info(f"Venta registrada: {codigo_venta} en tienda {tenant_id}. Total: {decimal_to_float(total)}")
        
        return success_response(
            mensaje="Venta registrada",
            data={
                "codigo_venta": codigo_venta,
                "total": decimal_to_float(total),
                "fecha": fecha_actual
            }
        )
        
    except Exception as e:
        logger.error(f"Error registrando venta: {str(e)}")
        return error_response("Error interno del servidor", 500)