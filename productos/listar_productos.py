# productos/listar_productos.py
import os
import logging
from utils import (
    success_response,
    error_response,
    log_request,
    extract_tenant_from_jwt_claims,
    query_by_tenant
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
PRODUCTOS_TABLE = os.environ.get('PRODUCTOS_TABLE')

def handler(event, context):
    """
    GET /productos - Listar productos de la tienda
    
    Según documento SAAI (TRABAJADOR):
    Request:
    {
        "body": {}
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
        
        # Consultar productos de la tienda (solo ACTIVOS)
        items = query_by_tenant(PRODUCTOS_TABLE, tenant_id)
        
        # Filtrar solo productos activos y formatear respuesta
        productos = []
        for item in items:
            data = item.get('data', {})
            if data.get('estado') == 'ACTIVO':
                producto = {
                    'codigo_producto': data.get('codigo_producto'),
                    'nombre': data.get('nombre'),
                    'precio': float(data.get('precio', 0)),
                    'stock': int(data.get('stock', 0)),
                    'categoria': data.get('categoria')
                }
                productos.append(producto)
        
        logger.info(f"Productos listados: {len(productos)} para tienda {tenant_id}")
        
        return success_response(
            data={"productos": productos}
        )
        
    except Exception as e:
        logger.error(f"Error listando productos: {str(e)}")
        return error_response("Error interno del servidor", 500)