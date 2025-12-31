# auth/login.py
import logging
from constants import ROLE_MAPPING
from utils import (
    success_response,
    error_response,
    validation_error_response,
    parse_request_body,
    log_request,
    generar_token_jwt,
    obtener_fecha_hora_peru
)
from .credentials_validator import (
    validar_credenciales,
    verificar_tienda_activa,
    actualizar_ultimo_login
)
from .token_manager import (
    guardar_token_activo,
    invalidar_todos_los_tokens_usuario
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    """
    POST /login - Autenticación multi-rol
    
    Según documento SAAI oficial:
    Request:
    {
        "body": {
            "email": "admin@tienda.com",
            "password": "123456"
        }
    }
    
    Response:
    {
        "success": true,
        "message": "Login exitoso",
        "data": {
            "token": "jwt_token",
            "user": {
                "codigo_usuario": "A001",
                "nombre": "Administrador",
                "role": "admin",
                "codigo_tienda": "T002"
            },
            "expires": 1731100000
        }
    }
    """
    try:
        log_request(event, context)
        
        # Parsear request body
        body = parse_request_body(event)
        
        # Validar campos obligatorios
        errores = validar_request_login(body)
        if errores:
            return validation_error_response(errores)
        
        usuario = body.get('usuario', '').strip() if 'usuario' in body else None
        email = body.get('email', '').strip()
        password = body['password']
        
        logger.info(f"Intento de login - email: {email}, usuario: {usuario}")
        
        # Validar credenciales
        usuario_info = None
        
        # Si viene usuario (formato legacy SAAI001), usar método anterior 
        if usuario:
            logger.info(f"Login legacy con usuario: {usuario}")
            usuario_info = validar_credenciales(usuario, password)
        
        # Si viene email, buscar en todas las tiendas
        elif email:
            logger.info(f"Login con email: {email}")
            from .credentials_validator import buscar_y_validar_credenciales_por_email
            usuario_info = buscar_y_validar_credenciales_por_email(email, password)
        
        else:
            logger.warning("Request sin datos válidos de usuario/email")
            return error_response(
                mensaje="Debe proporcionar email + password o usuario + password",
                status_code=400
            )
        if not usuario_info:
            logger.warning(f"Credenciales inválidas - email: {email}, usuario: {usuario}")
            return error_response(
                mensaje="Email/usuario o contraseña incorrectos",
                status_code=401
            )
        
        # Verificar que la tienda esté activa (solo para usuarios normales)
        tenant_id = usuario_info['tenant_id']
        if not verificar_tienda_activa(tenant_id):
            logger.warning(f"Intento de login en tienda inactiva: {tenant_id}")
            return error_response(
                mensaje="La tienda no está disponible actualmente",
                status_code=403
            )
        
        # Invalidar tokens anteriores (logout previo automático)
        invalidar_tokens_anteriores(usuario_info)
        
        # Generar nuevo token JWT
        token_jwt = generar_token_jwt(
            codigo_usuario=usuario_info['codigo_usuario'],
            codigo_tienda=usuario_info['tenant_id'],
            rol=usuario_info['rol'],
            datos_adicionales={
                'nombre': usuario_info.get('nombre', ''),
                'email': usuario_info.get('email', '')
            }
        )
        
        if not token_jwt:
            logger.error(f"Error generando token JWT para usuario: {usuario}")
            return error_response(
                mensaje="Error interno generando token de acceso",
                status_code=500
            )
        
        # Guardar token como activo en base de datos
        token_guardado = guardar_token_activo(token_jwt, usuario_info)
        if not token_guardado:
            logger.error(f"Error guardando token activo para usuario: {usuario}")
            return error_response(
                mensaje="Error interno guardando sesión",
                status_code=500
            )
        
        # Actualizar fecha de último login
        actualizar_ultimo_login(usuario_info['tenant_id'], usuario_info['codigo_usuario'])
        
        # Preparar respuesta exitosa según documentación oficial SAAI
        import time
        
        # Mapear rol interno a formato API
        role_api = mapear_rol_api(usuario_info['rol'])
        
        # Calcular timestamp de expiración (24 horas desde ahora)
        expires_timestamp = int(time.time()) + 86400
        
        response_data = {
            'token': token_jwt,
            'user': {
                'codigo_usuario': usuario_info['codigo_usuario'],
                'nombre': usuario_info.get('nombre', ''),
                'role': role_api,
                'codigo_tienda': usuario_info['tenant_id']
            },
            'expires': expires_timestamp
        }
        
        logger.info(f"Login exitoso para usuario: {usuario_info['codigo_usuario']}, role: {role_api}")
        
        return success_response(
            data=response_data,
            message="Login exitoso"
        )
        
    except Exception as e:
        logger.error(f"Error inesperado en login: {e}")
        return error_response(
            message="Error interno del servidor",
            status_code=500
        )


def mapear_rol_api(rol_interno):
    """
    Mapea el rol interno al valor estándar para API según documentación SAAI
    
    Args:
        rol_interno (str): Rol interno (TRABAJADOR, ADMIN, SAAI)
        
    Returns:
        str: Rol en formato API (worker, admin, saai)
    """
    from constants import ROLE_MAPPING
    return ROLE_MAPPING.get(rol_interno, rol_interno.lower())


def validar_request_login(body):
    """
    Valida los datos del request de login
    
    Soporta dos formatos:
    1. Legacy: {"usuario": "SAAI001", "password": "123"}
    2. Nuevo: {"email": "admin@mail.com", "password": "123"}
    
    Args:
        body (dict): Body parseado del request
        
    Returns:
        dict: Errores de validación o diccionario vacío si es válido
    """
    errores = {}
    
    # Verificar que tenga al menos uno de los formatos
    tiene_usuario = body.get('usuario')
    tiene_email = body.get('email')
    
    if not tiene_usuario and not tiene_email:
        errores['auth'] = 'Debe proporcionar: (usuario + password) o (email + password)'
        return errores
    
    # Validar formato legacy (usuario)
    if tiene_usuario:
        usuario = body.get('usuario')
        if not isinstance(usuario, str) or not usuario.strip():
            errores['usuario'] = 'El usuario debe ser una cadena de texto válida'
        elif len(usuario.strip()) < 3:
            errores['usuario'] = 'El usuario debe tener al menos 3 caracteres'
        elif len(usuario.strip()) > 20:
            errores['usuario'] = 'El usuario no puede tener más de 20 caracteres'
    
    # Validar formato nuevo (email)
    if tiene_email:
        email = body.get('email', '')
        if not isinstance(email, str) or not email.strip():
            errores['email'] = 'El email debe ser una cadena válida'
        elif '@' not in email or '.' not in email:
            errores['email'] = 'El email debe tener formato válido'
        elif len(email) > 100:
            errores['email'] = 'El email no puede tener más de 100 caracteres'
    
    # Validar password
    password = body.get('password')
    if not password:
        errores['password'] = 'El campo password es obligatorio'
    elif not isinstance(password, str):
        errores['password'] = 'La contraseña debe ser una cadena de texto'
    elif len(password) < 4:
        errores['password'] = 'La contraseña debe tener al menos 4 caracteres'
    elif len(password) > 50:
        errores['password'] = 'La contraseña no puede tener más de 50 caracteres'
    
    return errores


def invalidar_tokens_anteriores(usuario_info):
    """
    Invalida tokens anteriores del usuario (logout previo automático)
    
    Args:
        usuario_info (dict): Información del usuario validado
    """
    try:
        from .token_manager import invalidar_todos_los_tokens_usuario
        
        tenant_id = usuario_info['tenant_id']
        codigo_usuario = usuario_info['codigo_usuario']
        rol = usuario_info['rol']
        
        # Invalidar tokens anteriores
        invalidar_todos_los_tokens_usuario(tenant_id, codigo_usuario, rol)
        
        logger.info(f"Tokens anteriores invalidados para usuario: {codigo_usuario}")
        
    except Exception as e:
        # No fallar el login por esto, solo log el error
        logger.warning(f"Error invalidando tokens anteriores: {e}")