# usuarios/crear_usuario.py
import os
import re
import hashlib
import logging
from constants import ALLOWED_ROLES, EMAIL_REGEX
from utils import (
    success_response,
    error_response,
    validation_error_response,
    parse_request_body,
    log_request,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims,
    verificar_rol_permitido,
    query_by_tenant,
    put_item_standard,
    generar_codigo_usuario,
    obtener_fecha_hora_peru
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
USUARIOS_TABLE = os.environ.get('USUARIOS_TABLE')
COUNTERS_TABLE = os.environ.get('COUNTERS_TABLE')

def handler(event, context):
    """
    POST /usuarios - Crear usuario en la tienda
    
    Según documento SAAI (ADMIN):
    Request:
    {
        "body": {
            "nombre": "Juan Perez",
            "email": "juan@tienda.com",
            "password": "123456",
            "role": "worker"
        }
    }
    
    Response:
    {
        "success": true,
        "message": "Usuario creado",
        "data": {
            "codigo_usuario": "T002U002"
        }
    }
    """
    try:
        log_request(event)
        
        # Verificar rol ADMIN
        tiene_permiso, error = verificar_rol_permitido(event, ['ADMIN'])
        if not tiene_permiso:
            return error
        
        # Extraer tenant_id del JWT
        tenant_id = extract_tenant_from_jwt_claims(event)
        if not tenant_id:
            return error_response("Token inválido - no se encontró codigo_tienda", 401)
        
        # Extraer usuario admin para auditoría
        user_data = extract_user_from_jwt_claims(event)
        codigo_admin = user_data.get('codigo_usuario') if user_data else None
        
        # Parse request body
        body = parse_request_body(event)
        if not body:
            return validation_error_response("Request body requerido")
        
        # Validar campos obligatorios
        required_fields = ['nombre', 'email', 'password', 'role']
        for field in required_fields:
            if not body.get(field):
                return validation_error_response(f"Campo {field} es obligatorio")
        
        nombre = str(body['nombre']).strip()
        email = str(body['email']).strip().lower()
        password = str(body['password']).strip()
        role = str(body['role']).strip().lower()
        
        # Validar rol con constants centralizadas
        if role not in ALLOWED_ROLES:
            return validation_error_response(f"Role debe ser uno de: {', '.join(ALLOWED_ROLES)}")
        
        # Validar formato de email con RFC 5322
        if not re.match(EMAIL_REGEX, email):
            return validation_error_response("Email con formato inválido")
        
        # Validar email único en la tienda
        result = query_by_tenant(USUARIOS_TABLE, tenant_id)
        for item in result.get('items', []):
            if item.get('email') == email and item.get('estado') == 'ACTIVO':
                return error_response("Ya existe un usuario con este email en la tienda", 400)
        
        # Generar código de usuario usando función de utils
        codigo_usuario = generar_codigo_usuario(tenant_id)
        
        # Hash de la password con salt
        salt = os.urandom(32)
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        
        # Crear usuario
        fecha_actual = obtener_fecha_hora_peru()
        
        usuario_data = {
            'codigo_usuario': codigo_usuario,
            'nombre': nombre,
            'email': email,
            'role': role,
            'password': password_hash.hex(),
            'salt': salt.hex(),
            'estado': 'ACTIVO',
            'created_at': fecha_actual,
            'updated_at': fecha_actual
        }
        
        if codigo_admin:
            usuario_data['created_by'] = codigo_admin
        
        # Guardar en DynamoDB
        put_item_standard(
            USUARIOS_TABLE,
            tenant_id=tenant_id,
            entity_id=codigo_usuario,
            data=usuario_data
        )
        
        logger.info(f"Usuario creado: {codigo_usuario} en tienda {tenant_id}")
        
        return success_response(
            mensaje="Usuario creado",
            data={"codigo_usuario": codigo_usuario}
        )
        
    except Exception as e:
        logger.error(f"Error creando usuario: {str(e)}")
        return error_response("Error interno del servidor", 500)