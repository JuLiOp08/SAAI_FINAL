# tiendas/listar_tiendas.py
import os
import logging
from utils import (
    success_response,
    error_response,
    log_request,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims,
    query_by_tenant,
    extract_pagination_params,
    create_next_token
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
        
        # Validar que el usuario sea SAAI
        user_info = extract_user_from_jwt_claims(event)
        if not user_info or user_info.get('rol') != 'SAAI':
            return error_response("Solo usuarios SAAI pueden listar tiendas", 403)
        
        # Extraer parámetros de paginación
        pagination = extract_pagination_params(event)
        
        # Para SAAI, listar todas las tiendas (tenant_id = "SAAI") con paginación
        result = query_by_tenant(
            TIENDAS_TABLE, 
            "SAAI",
            limit=pagination['limit'],
            last_evaluated_key=pagination['exclusive_start_key'],
            include_inactive=True  # Incluir todas las tiendas (ACTIVA, SUSPENDIDA, ELIMINADA)
        )
        
        # Formatear respuesta
        tiendas = []
        for item in result['items']:
            data = item.get('data', {})
            # Incluir todas las tiendas (ACTIVA, SUSPENDIDA, ELIMINADA)
            tienda = {
                'codigo_tienda': data.get('codigo_tienda'),
                'nombre_tienda': data.get('nombre_tienda'),
                'email_tienda': data.get('email_tienda'),
                'telefono': data.get('telefono'),
                'estado': data.get('estado'),
                'created_at': data.get('created_at', '').split('T')[0] if data.get('created_at') else None
            }
            tiendas.append(tienda)
        
        # Ordenar por fecha de creación descendente
        tiendas.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Preparar respuesta
        response_data = {"tiendas": tiendas}
        
        # Agregar next_token si hay más páginas
        if result.get('last_evaluated_key'):
            next_token = create_next_token(result['last_evaluated_key'])
            if next_token:
                response_data["next_token"] = next_token
        
        logger.info(f"Tiendas listadas: {len(tiendas)}")
        
        return success_response(data=response_data)
        
    except Exception as e:
        logger.error(f"Error listando tiendas: {str(e)}")
        return error_response("Error interno del servidor", 500)