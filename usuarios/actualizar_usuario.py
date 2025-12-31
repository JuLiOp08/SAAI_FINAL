# usuarios/actualizar_usuario.py
import os
import logging
from constants import ALLOWED_ROLES
from utils import (
    success_response,
    error_response,
    validation_error_response,
    parse_request_body,
    log_request,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims,
    get_item_standard,
    put_item_standard,
    obtener_fecha_hora_peru
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
USUARIOS_TABLE = os.environ.get('USUARIOS_TABLE')

def handler(event, context):
    """
    PUT /usuarios/{codigo_usuario} - Actualizar usuario
    
    Según documento SAAI (ADMIN):
    Request:
    {
        "body": {
            "nombre": "Juan P.",
            "role": "worker"
        }
    }
    
    Response:
    {
        "success": true,
        "message": "Usuario actualizado",
        "data": {
            "codigo_usuario": "T002U002"
        }
    }
    """
    try:
        log_request(event)
        
        # Extraer tenant_id del JWT
        tenant_id = extract_tenant_from_jwt_claims(event)
        if not tenant_id:
            return error_response("Token inválido - no se encontró codigo_tienda", 401)
        
        # Extraer usuario admin para auditoría
        user_data = extract_user_from_jwt_claims(event)
        codigo_admin = user_data.get('codigo_usuario') if user_data else None
        
        # Obtener código de usuario del path
        codigo_usuario = event.get('pathParameters', {}).get('codigo_usuario')
        if not codigo_usuario:
            return validation_error_response("Código de usuario requerido en el path")
        
        # Parse request body
        body = parse_request_body(event)
        if not body:
            return validation_error_response("Request body requerido")
        
        # Verificar que el usuario existe
        usuario_data = get_item_standard(USUARIOS_TABLE, tenant_id, codigo_usuario)
        if not usuario_data:
            return error_response("Usuario no encontrado", 404)
        
        # Verificar que el usuario está activo
        if usuario_data.get('estado') != 'ACTIVO':
            return error_response("No se puede actualizar un usuario inactivo", 400)
        
        # Actualizar campos permitidos
        fecha_actual = obtener_fecha_hora_peru()
        
        if 'nombre' in body:
            usuario_data['nombre'] = str(body['nombre']).strip()
        
        if 'role' in body:
            role = str(body['role']).strip().lower()
            if role not in ALLOWED_ROLES:
                return validation_error_response(f"Role debe ser uno de: {', '.join(ALLOWED_ROLES)}")
            usuario_data['role'] = role
        
        # Actualizar metadatos
        usuario_data['updated_at'] = fecha_actual
        if codigo_admin:
            usuario_data['updated_by'] = codigo_admin
        
        # Guardar en DynamoDB
        put_item_standard(
            USUARIOS_TABLE,
            tenant_id=tenant_id,
            entity_id=codigo_usuario,
            data=usuario_data
        )
        
        logger.info(f"Usuario actualizado: {codigo_usuario} en tienda {tenant_id}")
        
        return success_response(
            message="Usuario actualizado",
            data={"codigo_usuario": codigo_usuario}
        )
        
    except Exception as e:
        logger.error(f"Error actualizando usuario: {str(e)}")
        return error_response("Error interno del servidor", 500)