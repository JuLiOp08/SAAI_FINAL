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
    get_item_standard,
    extract_pagination_params,
    create_next_token
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
PRODUCTOS_TABLE = os.environ.get('PRODUCTOS_TABLE')

def handler(event, context):
    """
    POST /productos/buscar - Buscar productos con paginación SAAI 1.6
    
    Query Parameters:
    - limit: número máximo de items por página (default: 50, max: 100)
    - next_token: token para la siguiente página
    
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
            "productos": [...],
            "next_token": "base64_encoded_token"  // Solo si hay más páginas
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
        
        # Extraer parámetros de paginación según SAAI 1.6
        pagination = extract_pagination_params(event, default_limit=50, max_limit=100)
        
        productos = []
        next_token = None
        
        # Buscar por código específico
        if body.get('codigo_producto'):
            codigo_producto = body['codigo_producto']
            item = get_item_standard(PRODUCTOS_TABLE, tenant_id, codigo_producto)
            
            if item and item.get('estado') == 'ACTIVO':
                producto = {
                    'codigo_producto': item.get('codigo_producto'),
                    'nombre': item.get('nombre'),
                    'precio': float(item.get('precio', 0)),
                    'stock': int(item.get('stock', 0)),
                    'categoria': item.get('categoria')
                }
                productos.append(producto)
        
        # Buscar por query (nombre) o categoría con paginación
        elif body.get('query') or body.get('categoria'):
            # Usar query_by_tenant con paginación (filtra INACTIVOS automáticamente)
            result = query_by_tenant(
                PRODUCTOS_TABLE, 
                tenant_id,
                limit=pagination['limit'],
                last_evaluated_key=pagination['exclusive_start_key']
            )
            
            query_text = body.get('query', '').lower().strip() if body.get('query') else None
            categoria = body.get('categoria', '').lower().strip() if body.get('categoria') else None
            
            for item in result.get('items', []):
                # Los items ya están filtrados (solo ACTIVOS) por query_by_tenant
                match = False
                
                # Buscar por query en nombre
                if query_text and query_text in item.get('nombre', '').lower():
                    match = True
                
                # Buscar por categoría
                if categoria and categoria == item.get('categoria', '').lower():
                    match = True
                
                if match:
                    producto = {
                        'codigo_producto': item.get('codigo_producto'),
                        'nombre': item.get('nombre'),
                        'precio': float(item.get('precio', 0)),
                        'stock': int(item.get('stock', 0)),
                        'categoria': item.get('categoria')
                    }
                    productos.append(producto)
            
            # Preparar next_token si hay más páginas
            if result.get('last_evaluated_key'):
                next_token = create_next_token(result['last_evaluated_key'])
        
        else:
            return validation_error_response("Se requiere codigo_producto, query o categoria")
        
        # Preparar respuesta con paginación
        response_data = {"productos": productos}
        if next_token:
            response_data["next_token"] = next_token
        
        logger.info(f"Productos encontrados: {len(productos)} para tienda {tenant_id}")
        
        return success_response(data=response_data)
        
    except Exception as e:
        logger.error(f"Error buscando productos: {str(e)}")
        return error_response("Error interno del servidor", 500)