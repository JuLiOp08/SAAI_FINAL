# usuarios/listar_usuarios.py
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
USUARIOS_TABLE = os.environ.get('USUARIOS_TABLE')

def handler(event, context):
    """
    GET /usuarios - Listar usuarios de la tienda
    
    Según documento SAAI (ADMIN):
    Request:
    {
        "body": {}
    }
    
    Response:
    {
        "success": true,
        "data": {
            "usuarios": [
                {
                    "codigo_usuario": "U002",
                    "nombre": "Juan Perez",
                    "email": "juan@tienda.com",
                    "role": "worker"
                }
            ],
            "next_token": "..."
        }
    }
    """
    try:
        log_request(event)
        
        # Extraer tenant_id del JWT
        tenant_id = extract_tenant_from_jwt_claims(event)
        if not tenant_id:
            return error_response("Token inválido - no se encontró codigo_tienda", 401)
        
        # Consultar usuarios de la tienda
        items = query_by_tenant(USUARIOS_TABLE, tenant_id)
        
        # Formatear respuesta
        usuarios = []
        for item in items:
            data = item.get('data', {})
            if data.get('estado') == 'ACTIVO':
                usuario = {
                    'codigo_usuario': data.get('codigo_usuario'),
                    'nombre': data.get('nombre'),
                    'email': data.get('email'),
                    'role': data.get('role')
                }
                usuarios.append(usuario)
        
        logger.info(f"Usuarios listados: {len(usuarios)} para tienda {tenant_id}")
        
        return success_response(
            data={"usuarios": usuarios}
        )
        
    except Exception as e:
        logger.error(f"Error listando usuarios: {str(e)}")
        return error_response("Error interno del servidor", 500)