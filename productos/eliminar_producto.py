# productos/eliminar_producto.py
import os
import logging
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
    obtener_fecha_hora_peru
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
PRODUCTOS_TABLE = os.environ.get('PRODUCTOS_TABLE')

def handler(event, context):
    """
    DELETE /productos/{codigo_producto} - Eliminar producto (soft delete)
    
    Según documento SAAI (TRABAJADOR):
    Request:
    {
        "body": {
            "motivo": "Producto descontinuado"
        }
    }
    
    Response:
    {
        "success": true,
        "message": "Producto eliminado",
        "data": {
            "codigo_producto": "T002P001"
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
        
        # Obtener código de producto del path
        codigo_producto = event.get('pathParameters', {}).get('codigo_producto')
        if not codigo_producto:
            return validation_error_response("Código de producto requerido en el path")
        
        # Parse request body para obtener motivo
        body = parse_request_body(event)
        motivo = body.get('motivo', 'Eliminado por el usuario') if body else 'Eliminado por el usuario'
        
        # Verificar que el producto existe
        item = get_item_standard(PRODUCTOS_TABLE, tenant_id, codigo_producto)
        if not item:
            return error_response("Producto no encontrado", 404)
        
        producto_data = item['data']
        
        # Verificar que el producto está activo
        if producto_data.get('estado') != 'ACTIVO':
            return error_response("El producto ya está inactivo", 400)
        
        # Realizar eliminación lógica (soft delete)
        fecha_actual = obtener_fecha_hora_peru()
        
        producto_data['estado'] = 'INACTIVO'
        producto_data['motivo_baja'] = str(motivo).strip()
        producto_data['fecha_baja'] = fecha_actual
        producto_data['updated_at'] = fecha_actual
        
        if codigo_usuario:
            producto_data['baja_por'] = codigo_usuario
        
        # Guardar en DynamoDB
        put_item_standard(
            PRODUCTOS_TABLE,
            tenant_id=tenant_id,
            entity_id=codigo_producto,
            data=producto_data
        )
        
        logger.info(f"Producto eliminado (soft delete): {codigo_producto} en tienda {tenant_id}")
        
        return success_response(
            message="Producto eliminado",
            data={"codigo_producto": codigo_producto}
        )
        
    except Exception as e:
        logger.error(f"Error eliminando producto: {str(e)}")
        return error_response("Error interno del servidor", 500)