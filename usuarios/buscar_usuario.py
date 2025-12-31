# usuarios/buscar_usuario.py
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
    extract_pagination_params,
    create_next_token
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
USUARIOS_TABLE = os.environ.get('USUARIOS_TABLE')

def handler(event, context):
    """
    POST /usuarios/buscar - Buscar usuarios por query
    
    Según documento SAAI (ADMIN):
    Request:
    {
        "body": {
            "query": "juan"
        },
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
                    "codigo_usuario": "U002",
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
        
        # Parse request body
        body = parse_request_body(event)
        if not body:
            return validation_error_response("Request body requerido")
        
        query = body.get('query')
        if not query:
            return validation_error_response("Campo query es obligatorio")
        
        query_text = str(query).lower().strip()
        
        # Extraer parámetros de paginación SAAI 1.6
        limit, next_token = extract_pagination_params(event)
        
        # Obtener todos los usuarios activos de la tienda con paginación
        result = query_by_tenant(
            USUARIOS_TABLE, 
            tenant_id,
            limit=limit,
            next_token=next_token
        )
        
        items = result.get('items', [])
        last_evaluated_key = result.get('last_evaluated_key')
        
        # Buscar en nombre, email o código
        usuarios_encontrados = []
        for item in items:
            data = item.get('data', {})
            if data.get('estado') != 'ACTIVO':
                continue
            
            # Buscar en campos de texto
            nombre = data.get('nombre', '').lower()
            email = data.get('email', '').lower()
            codigo = data.get('codigo_usuario', '').lower()
            
            if (query_text in nombre or query_text in email or query_text in codigo):
                usuario = {
                    'codigo_usuario': data.get('codigo_usuario'),
                    'nombre': data.get('nombre'),
                    'email': data.get('email'),
                    'role': data.get('role')
                }
                usuarios_encontrados.append(usuario)
        
        logger.info(f"Usuarios encontrados: {len(usuarios_encontrados)} para query '{query_text}' en tienda {tenant_id}")
        
        # Preparar response con paginación
        response_data = {"usuarios": usuarios_encontrados}
        
        # Agregar next_token si hay más resultados
        if last_evaluated_key:
            response_data['next_token'] = create_next_token(last_evaluated_key)
        
        return success_response(data=response_data)
        
    except Exception as e:
        logger.error(f"Error buscando usuarios: {str(e)}")
        return error_response("Error interno del servidor", 500)