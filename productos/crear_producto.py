# productos/crear_producto.py
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
    put_item_standard,
    increment_counter,
    obtener_fecha_hora_peru
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
PRODUCTOS_TABLE = os.environ.get('PRODUCTOS_TABLE')
COUNTERS_TABLE = os.environ.get('COUNTERS_TABLE')

def handler(event, context):
    """
    POST /productos - Crear nuevo producto en la tienda
    
    Según documento SAAI (TRABAJADOR):
    Request:
    {
        "body": {
            "nombre": "Coca Cola 500ml",
            "precio": 3.5,
            "stock": 20,
            "categoria": "bebidas",
            "descripcion": "Botella 500ml"
        }
    }
    
    Response:
    {
        "success": true,
        "message": "Producto creado",
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
        
        # Extraer usuario del JWT para auditoría
        user_data = extract_user_from_jwt_claims(event)
        codigo_usuario = user_data.get('codigo_usuario') if user_data else None
        
        # Parse request body
        body = parse_request_body(event)
        if not body:
            return validation_error_response("Request body requerido")
        
        # Validar campos obligatorios según documento
        required_fields = ['nombre', 'precio', 'stock', 'categoria']
        for field in required_fields:
            if not body.get(field):
                return validation_error_response(f"Campo {field} es obligatorio")
        
        # Validar tipos de datos
        try:
            precio = float(body['precio'])
            if precio <= 0:
                return validation_error_response("El precio debe ser mayor a 0")
        except (ValueError, TypeError):
            return validation_error_response("Precio debe ser un número válido")
        
        try:
            stock = int(body['stock'])
            if stock < 0:
                return validation_error_response("El stock debe ser mayor o igual a 0")
        except (ValueError, TypeError):
            return validation_error_response("Stock debe ser un número entero")
        
        # Generar código de producto
        contador = increment_counter(COUNTERS_TABLE, tenant_id, "PRODUCTOS")
        codigo_producto = f"{tenant_id}P{contador:03d}"
        
        # Crear entidad producto
        fecha_actual = obtener_fecha_hora_peru()
        
        producto_data = {
            'codigo_producto': codigo_producto,
            'nombre': str(body['nombre']).strip(),
            'precio': Decimal(str(precio)),
            'stock': stock,
            'categoria': str(body['categoria']).strip(),
            'estado': 'ACTIVO',
            'created_at': fecha_actual,
            'updated_at': fecha_actual
        }
        
        # Agregar descripción si se proporciona
        if body.get('descripcion'):
            producto_data['descripcion'] = str(body['descripcion']).strip()
        
        # Agregar auditoría si hay usuario
        if codigo_usuario:
            producto_data['created_by'] = codigo_usuario
        
        # Guardar en DynamoDB
        put_item_standard(
            PRODUCTOS_TABLE,
            tenant_id=tenant_id,
            entity_id=codigo_producto,
            data=producto_data
        )
        
        logger.info(f"Producto creado: {codigo_producto} en tienda {tenant_id}")
        
        return success_response(
            message="Producto creado",
            data={"codigo_producto": codigo_producto}
        )
        
    except Exception as e:
        logger.error(f"Error creando producto: {str(e)}")
        return error_response("Error interno del servidor", 500)