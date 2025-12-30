# tiendas/buscar_tienda.py
import os
import logging
from utils import (
    success_response,
    error_response,
    validation_error_response,
    parse_request_body,
    log_request,
    extract_tenant_from_jwt_claims,
    query_by_tenant
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
TIENDAS_TABLE = os.environ.get('TIENDAS_TABLE')

def handler(event, context):
    """
    POST /tiendas/buscar - Buscar tiendas por query
    
    Según documento SAAI (SAAI):
    Request:
    {
        "body": {
            "query": "San Juan"
        }
    }
    
    Response:
    {
        "success": true,
        "data": {
            "tiendas": [
                {
                    "codigo_tienda": "T002",
                    "nombre_tienda": "Bodega San Juan",
                    "estado": "ACTIVA"
                }
            ]
        }
    }
    """
    try:
        log_request(event)
        
        # Parse request body
        body = parse_request_body(event)
        if not body:
            return validation_error_response("Request body requerido")
        
        query = body.get('query')
        if not query:
            return validation_error_response("Campo query es obligatorio")
        
        query_text = str(query).lower().strip()
        
        # Obtener todas las tiendas
        items = query_by_tenant(TIENDAS_TABLE, "SAAI")
        
        # Buscar en nombre_tienda o codigo_tienda
        tiendas_encontradas = []
        for item in items:
            data = item.get('data', {})
            
            # Buscar en nombre o código
            nombre = data.get('nombre_tienda', '').lower()
            codigo = data.get('codigo_tienda', '').lower()
            
            if query_text in nombre or query_text in codigo:
                tienda = {
                    'codigo_tienda': data.get('codigo_tienda'),
                    'nombre_tienda': data.get('nombre_tienda'),
                    'estado': data.get('estado')
                }
                tiendas_encontradas.append(tienda)
        
        logger.info(f"Tiendas encontradas: {len(tiendas_encontradas)} para query '{query_text}'")
        
        return success_response(
            data={"tiendas": tiendas_encontradas}
        )
        
    except Exception as e:
        logger.error(f"Error buscando tiendas: {str(e)}")
        return error_response("Error interno del servidor", 500)