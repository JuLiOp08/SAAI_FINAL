# usuarios/eliminar_usuario.py
import os
import logging
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
    DELETE /usuarios/{codigo_usuario} - Eliminar usuario (soft delete)
    
    Según documento SAAI (ADMIN):
    Request:
    {
        "body": {
            "motivo": "Usuario ya no trabaja"
        }
    }
    
    Response:
    {
        "success": true,
        "message": "Usuario eliminado",
        "data": {
            "codigo_usuario": "U002"
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
        
        # Parse request body para obtener motivo
        body = parse_request_body(event)
        motivo = body.get('motivo', 'Eliminado por el administrador') if body else 'Eliminado por el administrador'
        
        # Verificar que el usuario existe
        item = get_item_standard(USUARIOS_TABLE, tenant_id, codigo_usuario)
        if not item:
            return error_response("Usuario no encontrado", 404)
        
        usuario_data = item['data']
        
        # Verificar que el usuario está activo
        if usuario_data.get('estado') != 'ACTIVO':
            return error_response("El usuario ya está inactivo", 400)
        
        # Realizar eliminación lógica (soft delete)
        fecha_actual = obtener_fecha_hora_peru()
        
        usuario_data['estado'] = 'INACTIVO'
        usuario_data['motivo_baja'] = str(motivo).strip()
        usuario_data['fecha_baja'] = fecha_actual
        usuario_data['updated_at'] = fecha_actual
        
        if codigo_admin:
            usuario_data['baja_por'] = codigo_admin
        
        # Guardar en DynamoDB
        put_item_standard(
            USUARIOS_TABLE,
            tenant_id=tenant_id,
            entity_id=codigo_usuario,
            data=usuario_data
        )
        
        logger.info(f"Usuario eliminado (soft delete): {codigo_usuario} en tienda {tenant_id}")
        
        return success_response(
            message="Usuario eliminado",
            data={"codigo_usuario": codigo_usuario}
        )
        
    except Exception as e:
        logger.error(f"Error eliminando usuario: {str(e)}")
        return error_response("Error interno del servidor", 500)