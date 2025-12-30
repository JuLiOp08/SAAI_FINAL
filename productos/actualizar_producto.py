# productos/actualizar_producto.py
import os
import logging
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
    obtener_fecha_hora_peru
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
PRODUCTOS_TABLE = os.environ.get('PRODUCTOS_TABLE')

def handler(event, context):
    """
    PUT /productos/{codigo_producto} - Actualizar producto
    
    Según documento SAAI (TRABAJADOR):
    Request:
    {
        "body": {
            "precio": 3.8,
            "stock": 15,
            "categoria": "bebidas"
        }
    }
    
    Response:
    {
        "success": true,
        "message": "Producto actualizado",
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
        
        # Parse request body
        body = parse_request_body(event)
        if not body:
            return validation_error_response("Request body requerido")
        
        # Verificar que el producto existe
        item = get_item_standard(PRODUCTOS_TABLE, tenant_id, codigo_producto)
        if not item:
            return error_response("Producto no encontrado", 404)
        
        producto_data = item['data']
        
        # Verificar que el producto está activo
        if producto_data.get('estado') != 'ACTIVO':
            return error_response("No se puede actualizar un producto inactivo", 400)
        
        # Actualizar campos permitidos
        fecha_actual = obtener_fecha_hora_peru()
        
        # Solo actualizar campos que se envían en el request
        if 'nombre' in body:
            producto_data['nombre'] = str(body['nombre']).strip()
        
        if 'precio' in body:
            try:
                precio = float(body['precio'])
                if precio <= 0:
                    return validation_error_response("El precio debe ser mayor a 0")
                producto_data['precio'] = Decimal(str(precio))
            except (ValueError, TypeError):
                return validation_error_response("Precio debe ser un número válido")
        
        if 'stock' in body:
            try:
                stock = int(body['stock'])
                if stock < 0:
                    return validation_error_response("El stock debe ser mayor o igual a 0")
                producto_data['stock'] = stock
            except (ValueError, TypeError):
                return validation_error_response("Stock debe ser un número entero")
        
        if 'categoria' in body:
            producto_data['categoria'] = str(body['categoria']).strip()
        
        if 'descripcion' in body:
            producto_data['descripcion'] = str(body['descripcion']).strip()
        
        # Actualizar metadatos
        producto_data['updated_at'] = fecha_actual
        if codigo_usuario:
            producto_data['updated_by'] = codigo_usuario
        
        # Guardar en DynamoDB
        put_item_standard(
            PRODUCTOS_TABLE,
            tenant_id=tenant_id,
            entity_id=codigo_producto,
            data=producto_data
        )
        
        logger.info(f"Producto actualizado: {codigo_producto} en tienda {tenant_id}")
        
        return success_response(
            message="Producto actualizado",
            data={"codigo_producto": codigo_producto}
        )
        
    except Exception as e:
        logger.error(f"Error actualizando producto: {str(e)}")
        return error_response("Error interno del servidor", 500)