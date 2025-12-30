# auth/login.py
import logging
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
    Endpoint público POST /login para autenticación multi-rol
    
    Según documento SAAI:
    - Valida usuario/password (TRABAJADOR, ADMIN, SAAI)
    - Genera JWT con claims multi-tenant (tenant_id, codigo_usuario, rol)
    - Guarda token activo en tabla correspondiente por rol
    - Retorna token + información del usuario
    
    Request:
    {
        "usuario": "T001U001" | "SAAI001",
        "password": "contraseña"
    }
    
    Response exitosa:
    {
        "exito": true,
        "mensaje": "Login exitoso",
        "data": {
            "token": "jwt_token...",
            "usuario": {
                "codigo_usuario": "T001U001",
                "nombre": "...",
                "email": "...",
                "rol": "TRABAJADOR|ADMIN|SAAI",
                "tenant_id": "T001"
            },
            "expires_in": 86400
        }
    }
    
    Args:
        event: Evento de API Gateway
        context: Contexto de Lambda
        
    Returns:
        dict: Respuesta HTTP formateada
    """
    try:
        log_request(event, context)
        
        # Parsear request body
        body = parse_request_body(event)
        
        # Validar campos obligatorios
        errores = validar_request_login(body)
        if errores:
            return validation_error_response(errores)
        
        usuario = body['usuario'].strip()
        password = body['password']
        
        logger.info(f"Intento de login para usuario: {usuario}")
        
        # Validar credenciales
        usuario_info = validar_credenciales(usuario, password)
        if not usuario_info:
            logger.warning(f"Credenciales inválidas para usuario: {usuario}")
            return error_response(
                mensaje="Usuario o contraseña incorrectos",
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
        
        # Preparar respuesta exitosa
        response_data = {
            'token': token_jwt,
            'usuario': {
                'codigo_usuario': usuario_info['codigo_usuario'],
                'nombre': usuario_info.get('nombre', ''),
                'email': usuario_info.get('email', ''),
                'rol': usuario_info['rol'],
                'tenant_id': usuario_info['tenant_id'],
                'telefono': usuario_info.get('telefono', ''),
                'ultimo_login': usuario_info.get('ultimo_login'),
                'estado': usuario_info.get('estado', 'ACTIVO')
            },
            'expires_in': 86400,  # 24 horas
            'token_type': 'Bearer',
            'generated_at': obtener_fecha_hora_peru()
        }
        
        # Agregar permisos para usuarios SAAI
        if usuario_info['rol'] == 'SAAI':
            response_data['usuario']['permisos'] = usuario_info.get('permisos', [])
        
        logger.info(f"Login exitoso para usuario: {usuario}, rol: {usuario_info['rol']}")
        
        return success_response(
            data=response_data,
            mensaje=f"Bienvenido {usuario_info.get('nombre', usuario)}",
            status_code=200
        )
        
    except Exception as e:
        logger.error(f"Error inesperado en login: {e}")
        return error_response(
            mensaje="Error interno del servidor durante el login",
            status_code=500
        )

def validar_request_login(body):
    """
    Valida los datos del request de login
    
    Args:
        body (dict): Body parseado del request
        
    Returns:
        dict: Errores de validación o diccionario vacío si es válido
    """
    errores = {}
    
    # Validar usuario
    usuario = body.get('usuario')
    if not usuario:
        errores['usuario'] = 'El campo usuario es obligatorio'
    elif not isinstance(usuario, str) or not usuario.strip():
        errores['usuario'] = 'El usuario debe ser una cadena de texto válida'
    elif len(usuario.strip()) < 3:
        errores['usuario'] = 'El usuario debe tener al menos 3 caracteres'
    elif len(usuario.strip()) > 20:
        errores['usuario'] = 'El usuario no puede tener más de 20 caracteres'
    
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

def generar_response_por_rol(usuario_info, token_jwt):
    """
    Genera información específica de respuesta según el rol
    
    Args:
        usuario_info (dict): Información del usuario
        token_jwt (str): Token JWT generado
        
    Returns:
        dict: Data específica por rol
    """
    try:
        rol = usuario_info['rol']
        
        base_response = {
            'token': token_jwt,
            'usuario': {
                'codigo_usuario': usuario_info['codigo_usuario'],
                'nombre': usuario_info.get('nombre', ''),
                'email': usuario_info.get('email', ''),
                'rol': rol,
                'tenant_id': usuario_info['tenant_id']
            },
            'expires_in': 86400,
            'generated_at': obtener_fecha_hora_peru()
        }
        
        # Información específica por rol
        if rol == 'TRABAJADOR':
            base_response['permisos'] = [
                'productos:read',
                'productos:write', 
                'ventas:read',
                'ventas:write'
            ]
            base_response['mensaje_bienvenida'] = "Acceso a gestión de productos y ventas habilitado"
            
        elif rol == 'ADMIN':
            base_response['permisos'] = [
                'productos:all',
                'ventas:all',
                'usuarios:all',
                'gastos:all',
                'analitica:all',
                'reportes:all'
            ]
            base_response['mensaje_bienvenida'] = "Panel administrativo completo habilitado"
            
        elif rol == 'SAAI':
            base_response['permisos'] = usuario_info.get('permisos', [])
            base_response['mensaje_bienvenida'] = "Acceso a plataforma SAAI habilitado"
        
        return base_response
        
    except Exception as e:
        logger.error(f"Error generando response por rol: {e}")
        return {
            'token': token_jwt,
            'usuario': usuario_info,
            'expires_in': 86400
        }

def log_evento_login(usuario_info, exito=True, motivo=None):
    """
    Registra evento de login para auditoría
    
    Args:
        usuario_info (dict): Información del usuario
        exito (bool): Si el login fue exitoso
        motivo (str): Motivo en caso de fallo
    """
    try:
        import json
        
        evento = {
            'tipo': 'LOGIN',
            'exito': exito,
            'usuario': usuario_info.get('codigo_usuario'),
            'tenant': usuario_info.get('tenant_id'),
            'rol': usuario_info.get('rol'),
            'timestamp': obtener_fecha_hora_peru(),
            'motivo': motivo
        }
        
        logger.info(f"AUDIT_LOGIN: {json.dumps(evento)}")
        
    except Exception as e:
        logger.error(f"Error logging evento de login: {e}")