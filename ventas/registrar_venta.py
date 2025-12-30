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
    increment_counter,
    obtener_fecha_hora_peru,
    decimal_to_float
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

# Inicializar clientes AWS
sns = boto3.client('sns')
apigateway = boto3.client('apigatewaymanagementapi', endpoint_url=WEBSOCKET_API_ENDPOINT)

def handler(event, context):
    """
    POST /ventas - Registrar nueva venta (descuenta stock + SNS + WebSocket)
    
    Según documento SAAI (TRABAJADOR):
    Request:
    {
        "body": {
            "cliente": "Juan Pérez",
            "items": [
                {
                    "codigo_producto": "P001",
                    "cantidad": 2
                },
                {
                    "codigo_producto": "P002",
                    "cantidad": 1
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
            "codigo_venta": "V001",
            "total": 148.09
        }
    }
    """
    try:
        log_request(event)
        
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
        
        # Validar campos obligatorios
        cliente = body.get('cliente')
        items = body.get('items')
        metodo_pago = body.get('metodo_pago')
        
        if not cliente:
            return validation_error_response("Cliente es obligatorio")
        
        if not items or not isinstance(items, list) or len(items) == 0:
            return validation_error_response("Items es obligatorio y debe ser una lista no vacía")
        
        if not metodo_pago:
            return validation_error_response("Metodo de pago es obligatorio")
        
        # Validar items y calcular totales (similar a calcular_monto)
        total_subtotal = Decimal('0.00')
        items_procesados = []
        productos_a_actualizar = []
        
        for item in items:
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
            producto = get_item_standard(PRODUCTOS_TABLE, tenant_id, codigo_producto)
            if not producto or producto.get('estado') != 'ACTIVO':
                return error_response(f"Producto {codigo_producto} no encontrado o inactivo", 404)
            
            # Verificar stock disponible
            stock_actual = int(producto.get('stock', 0))
            if stock_actual < cantidad:
                return error_response(
                    f"Stock insuficiente para producto {codigo_producto}. Disponible: {stock_actual}, Solicitado: {cantidad}",
                    400
                )
            
            precio_unitario = producto.get('precio', Decimal('0.00'))
            if isinstance(precio_unitario, (int, float)):
                precio_unitario = Decimal(str(precio_unitario))
            
            # Calcular subtotal del item
            subtotal_item = precio_unitario * Decimal(str(cantidad))
            total_subtotal += subtotal_item
            
            # Preparar item procesado
            item_procesado = {
                'codigo_producto': codigo_producto,
                'nombre_producto': producto.get('nombre'),
                'precio_unitario': precio_unitario,
                'cantidad': cantidad,
                'subtotal_item': subtotal_item
            }
            
            items_procesados.append(item_procesado)
            
            # Preparar actualización de stock
            producto_actualizado = producto.copy()
            producto_actualizado['stock'] = stock_actual - cantidad
            producto_actualizado['updated_at'] = obtener_fecha_hora_peru()
            if codigo_usuario:
                producto_actualizado['updated_by'] = codigo_usuario
            
            productos_a_actualizar.append((codigo_producto, producto_actualizado))
        
        # Calcular IGV y total
        igv_rate = Decimal('0.18')
        igv = total_subtotal * igv_rate
        total = total_subtotal + igv
        
        # Generar código de venta
        contador = increment_counter(COUNTERS_TABLE, tenant_id, "VENTAS")
        codigo_venta = f"V{contador:03d}"
        
        # Crear entidad venta
        fecha_actual = obtener_fecha_hora_peru()
        
        venta_data = {
            'codigo_venta': codigo_venta,
            'cliente': str(cliente).strip(),
            'items': [
                {
                    'codigo_producto': item['codigo_producto'],
                    'nombre_producto': item['nombre_producto'],
                    'precio_unitario': item['precio_unitario'],
                    'cantidad': item['cantidad'],
                    'subtotal_item': item['subtotal_item']
                }
                for item in items_procesados
            ],
            'subtotal': total_subtotal,
            'igv': igv,
            'total': total,
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
                'cliente': cliente,
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
        
        # Enviar notificación WebSocket (intentar)
        try:
            if WEBSOCKET_API_ENDPOINT:
                websocket_message = {
                    'type': 'nueva_venta',
                    'codigo_tienda': tenant_id,
                    'codigo_venta': codigo_venta,
                    'total': decimal_to_float(total),
                    'cliente': cliente,
                    'timestamp': fecha_actual
                }
                
                # Note: En un entorno real, aquí enviaríamos a conexiones activas del WebSocket
                logger.info(f"WebSocket message prepared for venta {codigo_venta}")
                
        except Exception as ws_error:
            logger.warning(f"Error preparando notificación WebSocket: {str(ws_error)}")
        
        logger.info(f"Venta registrada: {codigo_venta} en tienda {tenant_id}. Total: {decimal_to_float(total)}")
        
        return success_response(
            message="Venta registrada",
            data={
                "codigo_venta": codigo_venta,
                "total": decimal_to_float(total)
            }
        )
        
    except Exception as e:
        logger.error(f"Error registrando venta: {str(e)}")
        return error_response("Error interno del servidor", 500)