# productos/listar_productos.py
import os
import logging
from utils import (
    success_response,
    error_response,
    log_request,
    extract_tenant_from_jwt_claims,
    query_by_tenant,
    extract_pagination_params,
    create_next_token
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
PRODUCTOS_TABLE = os.environ.get('PRODUCTOS_TABLE')

def handler(event, context):
    """
    GET /productos - Listar productos de la tienda con paginación SAAI 1.6
    
    Query Parameters:
    - limit: número máximo de items por página (default: 50, max: 100)
    - next_token: token para la siguiente página
    
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
        
        # Extraer parámetros de paginación según SAAI 1.6
        pagination = extract_pagination_params(event, default_limit=50, max_limit=100)
        
        # Consultar productos de la tienda (filtra INACTIVOS automáticamente)
        result = query_by_tenant(
            PRODUCTOS_TABLE, 
            tenant_id,
            limit=pagination['limit'],
            last_evaluated_key=pagination['exclusive_start_key']
        )
        
        # Formatear respuesta
        productos = []
        for item in result.get('items', []):
            # Los items ya están filtrados (solo ACTIVOS) por query_by_tenant
            producto = {
                'codigo_producto': item.get('codigo_producto'),
                'nombre': item.get('nombre'),
                'precio': float(item.get('precio', 0)),
                'stock': int(item.get('stock', 0)),
                'categoria': item.get('categoria')
            }
            productos.append(producto)
        
        # Preparar respuesta con paginación
        response_data = {"productos": productos}
        
        # Agregar next_token si hay más páginas
        if result.get('last_evaluated_key'):
            next_token = create_next_token(result['last_evaluated_key'])
            if next_token:
                response_data["next_token"] = next_token
        
        logger.info(f"Productos listados: {len(productos)} para tienda {tenant_id}")
        
        return success_response(data=response_data)
        
    except Exception as e:
        logger.error(f"Error listando productos: {str(e)}")
        return error_response("Error interno del servidor", 500)