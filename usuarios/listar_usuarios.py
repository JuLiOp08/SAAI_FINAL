# usuarios/listar_usuarios.py
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
USUARIOS_TABLE = os.environ.get('USUARIOS_TABLE')

def handler(event, context):
    """
    GET /usuarios - Listar usuarios de la tienda
    
    Según documento SAAI (ADMIN):
    Request:
    {
        "queryStringParameters": {
            "limit": 10,
            "next_token": "..." (opcional)
        }
    }
    
    Response:
    {
        "success": true,
        "data": {
            "usuarios": [
                {
                    "codigo_usuario": "T002U002",
                    "nombre": "Juan Perez",
                    "email": "juan@tienda.com",
                    "role": "worker"
                }
            ],
            "next_token": "..." (si hay más resultados)
        }
    }
    """
    try:
        log_request(event)
        
        # Extraer tenant_id del JWT
        tenant_id = extract_tenant_from_jwt_claims(event)
        if not tenant_id:
            return error_response("Token inválido - no se encontró codigo_tienda", 401)
        
        # Extraer parámetros de paginación SAAI 1.6
        pagination = extract_pagination_params(event, default_limit=50, max_limit=100)
        
        # Consultar usuarios de la tienda con paginación
        result = query_by_tenant(
            USUARIOS_TABLE, 
            tenant_id,
            limit=pagination['limit'],
            last_evaluated_key=pagination.get('exclusive_start_key')
        )
        
        items = result.get('items', [])
        last_evaluated_key = result.get('last_evaluated_key')
        
        # Formatear respuesta (query_by_tenant filtra INACTIVOS automáticamente)
        usuarios = []
        for item in items:
            usuario = {
                'codigo_usuario': item.get('codigo_usuario'),
                'nombre': item.get('nombre'),
                'email': item.get('email'),
                'role': item.get('role')
            }
            usuarios.append(usuario)
        
        logger.info(f"Usuarios listados: {len(usuarios)} para tienda {tenant_id}")
        
        # Preparar response con paginación
        response_data = {"usuarios": usuarios}
        
        # Agregar next_token si hay más resultados
        if last_evaluated_key:
            response_data['next_token'] = create_next_token(last_evaluated_key)
        
        return success_response(data=response_data)
        
    except Exception as e:
        logger.error(f"Error listando usuarios: {str(e)}")
        return error_response("Error interno del servidor", 500)