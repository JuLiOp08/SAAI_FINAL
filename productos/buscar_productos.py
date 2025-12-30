# productos/buscar_productos.py
import os
import logging
from utils import (
    success_response,
    error_response,
    validation_error_response,
    parse_request_body,
    log_request,
    extract_tenant_from_jwt_claims,
    query_by_tenant,
    get_item_standard
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
PRODUCTOS_TABLE = os.environ.get('PRODUCTOS_TABLE')

def handler(event, context):
    """
    POST /productos/buscar - Buscar productos
    
    Según documento SAAI (TRABAJADOR):
    
    EJEMPLO 1 – Buscar por código:
    Request:
    {
        "body": {
            "codigo_producto": "T002P001"
        }
    }
    
    EJEMPLO 2 – Buscar por nombre:
    Request:
    {
        "body": {
            "query": "coca"
        }
    }
    
    EJEMPLO 3 – Buscar por categoría:
    Request:
    {
        "body": {
            "categoria": "bebidas"
        }
    }
    
    Response:
    {
        "success": true,
        "data": {
            "productos": [
                {
                    "codigo_producto": "T002P001",
                    "nombre": "Coca Cola 500ml",
                    "precio": 3.5,
                    "stock": 12,
                    "categoria": "bebidas"
                }
            ]
        }
    }
    """
    try:
        log_request(event)
        
        # Extraer tenant_id del JWT
        tenant_id = extract_tenant_from_jwt_claims(event)
        if not tenant_id:
            return error_response("Token inválido - no se encontró codigo_tienda", 401)
        
        # Parse request body
        body = parse_request_body(event)
        if not body:
            return validation_error_response("Request body requerido")
        
        productos = []
        
        # Buscar por código específico
        if body.get('codigo_producto'):
            codigo_producto = body['codigo_producto']
            item = get_item_standard(PRODUCTOS_TABLE, tenant_id, codigo_producto)
            
            if item and item.get('data', {}).get('estado') == 'ACTIVO':
                data = item['data']
                producto = {
                    'codigo_producto': data.get('codigo_producto'),
                    'nombre': data.get('nombre'),
                    'precio': float(data.get('precio', 0)),
                    'stock': int(data.get('stock', 0)),
                    'categoria': data.get('categoria')
                }
                productos.append(producto)
        
        # Buscar por query (nombre) o categoría
        elif body.get('query') or body.get('categoria'):
            # Obtener todos los productos activos de la tienda
            items = query_by_tenant(PRODUCTOS_TABLE, tenant_id)
            
            query_text = body.get('query', '').lower().strip() if body.get('query') else None
            categoria = body.get('categoria', '').lower().strip() if body.get('categoria') else None
            
            for item in items:
                data = item.get('data', {})
                if data.get('estado') != 'ACTIVO':
                    continue
                
                match = False
                
                # Buscar por query en nombre
                if query_text and query_text in data.get('nombre', '').lower():
                    match = True
                
                # Buscar por categoría
                if categoria and categoria == data.get('categoria', '').lower():
                    match = True
                
                if match:
                    producto = {
                        'codigo_producto': data.get('codigo_producto'),
                        'nombre': data.get('nombre'),
                        'precio': float(data.get('precio', 0)),
                        'stock': int(data.get('stock', 0)),
                        'categoria': data.get('categoria')
                    }
                    productos.append(producto)
        
        else:
            return validation_error_response("Se requiere codigo_producto, query o categoria")
        
        logger.info(f"Productos encontrados: {len(productos)} para tienda {tenant_id}")
        
        return success_response(
            data={"productos": productos}
        )
        
    except Exception as e:
        logger.error(f"Error buscando productos: {str(e)}")
        return error_response("Error interno del servidor", 500)