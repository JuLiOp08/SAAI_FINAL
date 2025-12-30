# tiendas/listar_tiendas.py
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
TIENDAS_TABLE = os.environ.get('TIENDAS_TABLE')

def handler(event, context):
    """
    GET /tiendas - Listar tiendas registradas
    
    Según documento SAAI (SAAI):
    Request:
    {
        "body": {}
    }
    
    Response:
    {
        "success": true,
        "data": {
            "tiendas": [
                {
                    "codigo_tienda": "T002",
                    "nombre_tienda": "Bodega San Juan",
                    "estado": "ACTIVA",
                    "created_at": "2025-11-08"
                }
            ],
            "next_token": "..."
        }
    }
    """
    try:
        log_request(event)
        
        # Para SAAI, listar todas las tiendas (tenant_id = "SAAI")
        items = query_by_tenant(TIENDAS_TABLE, "SAAI")
        
        # Formatear respuesta
        tiendas = []
        for item in items:
            data = item.get('data', {})
            # Incluir todas las tiendas (ACTIVA, SUSPENDIDA, ELIMINADA)
            tienda = {
                'codigo_tienda': data.get('codigo_tienda'),
                'nombre_tienda': data.get('nombre_tienda'),
                'estado': data.get('estado'),
                'created_at': data.get('created_at', '').split('T')[0] if data.get('created_at') else None
            }
            tiendas.append(tienda)
        
        # Ordenar por fecha de creación descendente
        tiendas.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        logger.info(f"Tiendas listadas: {len(tiendas)}")
        
        return success_response(
            data={"tiendas": tiendas}
        )
        
    except Exception as e:
        logger.error(f"Error listando tiendas: {str(e)}")
        return error_response("Error interno del servidor", 500)