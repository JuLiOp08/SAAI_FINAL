# utils/jwt_utils.py
import jwt
import os
import logging
from datetime import datetime, timedelta, timezone
from .datetime_utils import obtener_fecha_hora_peru, PERU_TIMEZONE

# Configurar logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuración JWT
JWT_SECRET = os.environ.get('JWT_SECRET', 'saai-secret-key-2025')
JWT_ALGORITHM = 'HS256'
JWT_AUDIENCE = os.environ.get('JWT_AUDIENCE', 'SAAI-Frontend')
JWT_EXPIRES_IN = int(os.environ.get('JWT_EXPIRES_IN', 86400))  # 24 horas por defecto

def generar_token_jwt(codigo_usuario, codigo_tienda, rol, datos_adicionales=None):
    """
    Genera un token JWT con los claims necesarios para SAAI
    
    Args:
        codigo_usuario (str): Código del usuario
        codigo_tienda (str): Código de la tienda (tenant_id)
        rol (str): Rol del usuario (TRABAJADOR, ADMIN, SAAI)
        datos_adicionales (dict, optional): Claims adicionales
        
    Returns:
        str: Token JWT generado
    """
    try:
        ahora = datetime.now(timezone.utc)
        expiracion = ahora + timedelta(seconds=JWT_EXPIRES_IN)
        
        # Claims estándar + custom claims
        payload = {
            # Claims estándar JWT
            'iss': 'SAAI-Backend',  # Issuer
            'iat': int(ahora.timestamp()),  # Issued at
            'exp': int(expiracion.timestamp()),  # Expiration
            'aud': JWT_AUDIENCE,  # Audience
            
            # Claims custom SAAI
            'codigo_usuario': codigo_usuario,
            'tenant_id': codigo_tienda,  # Crítico para multi-tenancy
            'rol': rol,
            'scope': obtener_scope_por_rol(rol),
            'timezone': 'America/Lima',
            
            # Metadata
            'generated_at': obtener_fecha_hora_peru(),
            'version': '1.0'
        }
        
        # Agregar datos adicionales si existen
        if datos_adicionales:
            payload.update(datos_adicionales)
        
        # Generar token
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        logger.info(f"Token JWT generado para usuario: {codigo_usuario}, rol: {rol}, tienda: {codigo_tienda}")
        return token
        
    except Exception as e:
        logger.error(f"Error generando token JWT: {e}")
        return None

def verificar_token_jwt(token):
    """
    Verifica y decodifica un token JWT
    
    Args:
        token (str): Token JWT a verificar
        
    Returns:
        dict: Payload decodificado o None si es inválido
    """
    try:
        # Remover 'Bearer ' si está presente
        if token.startswith('Bearer '):
            token = token[7:]
        
        # Decodificar y verificar token (incluir audience esperado)
        payload = jwt.decode(
            token, 
            JWT_SECRET, 
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE
        )
        
        # Validaciones adicionales
        if not payload.get('codigo_usuario'):
            logger.error("Token JWT sin codigo_usuario")
            return None
        
        if not payload.get('tenant_id'):
            logger.error("Token JWT sin tenant_id")
            return None
        
        if not payload.get('rol'):
            logger.error("Token JWT sin rol")
            return None
        
        # Verificar que el rol sea válido
        if payload['rol'] not in ['TRABAJADOR', 'ADMIN', 'SAAI']:
            logger.error(f"Rol inválido en token: {payload['rol']}")
            return None
        
        logger.info(f"Token JWT verificado exitosamente para usuario: {payload.get('codigo_usuario')}")
        return payload
        
    except jwt.ExpiredSignatureError:
        logger.error("Token JWT expirado")
        return None
    except jwt.InvalidTokenError as e:
        logger.error(f"Token JWT inválido: {e}")
        return None
    except Exception as e:
        logger.error(f"Error verificando token JWT: {e}")
        return None

def obtener_scope_por_rol(rol):
    """
    Obtiene los scopes/permisos según el rol
    
    Args:
        rol (str): Rol del usuario
        
    Returns:
        list: Lista de scopes disponibles
    """
    scopes = {
        'TRABAJADOR': [
            'productos:read',
            'productos:write',
            'ventas:read',
            'ventas:write',
            'notificaciones:read'
        ],
        'ADMIN': [
            'productos:read',
            'productos:write',
            'ventas:read',
            'ventas:write',
            'usuarios:read',
            'usuarios:write',
            'gastos:read',
            'gastos:write',
            'analitica:read',
            'analitica:write',
            'reportes:read',
            'reportes:write',
            'predicciones:read',
            'predicciones:write',
            'notificaciones:read'
        ],
        'SAAI': [
            'tiendas:read',
            'tiendas:write',
            'usuarios:read',
            'usuarios:write',
            'notificaciones:read',
            'sistema:admin'
        ]
    }
    
    return scopes.get(rol, [])

def validar_scope_requerido(payload, scope_requerido):
    """
    Valida si el usuario tiene un scope específico
    
    Args:
        payload (dict): Payload del JWT
        scope_requerido (str): Scope a validar
        
    Returns:
        bool: True si tiene el scope, False en caso contrario
    """
    scopes = payload.get('scope', [])
    return scope_requerido in scopes

def extraer_token_de_header(auth_header):
    """
    Extrae el token del header Authorization
    
    Args:
        auth_header (str): Header Authorization
        
    Returns:
        str: Token extraído o None
    """
    if not auth_header:
        return None
    
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    
    return auth_header

def generar_claims_authorizer(payload):
    """
    Genera los claims que el authorizer debe pasar al Lambda
    
    Args:
        payload (dict): Payload del JWT decodificado
        
    Returns:
        dict: Claims para el authorizer context
    """
    return {
        'codigo_usuario': payload.get('codigo_usuario'),
        'tenant_id': payload.get('tenant_id'),
        'rol': payload.get('rol'),
        'scope': ','.join(payload.get('scope', [])),
        'generated_at': payload.get('generated_at'),
        'version': payload.get('version', '1.0')
    }

def token_expira_pronto(payload, minutos_threshold=30):
    """
    Verifica si un token expira pronto
    
    Args:
        payload (dict): Payload del JWT
        minutos_threshold (int): Minutos antes de considerar "pronto"
        
    Returns:
        bool: True si expira pronto
    """
    try:
        exp = payload.get('exp')
        if not exp:
            return True
        
        ahora = datetime.now(timezone.utc)
        expiracion = datetime.fromtimestamp(exp, timezone.utc)
        
        tiempo_restante = expiracion - ahora
        return tiempo_restante.total_seconds() < (minutos_threshold * 60)
        
    except Exception:
        return True

def renovar_token_si_es_necesario(token, minutos_threshold=30):
    """
    Renueva un token si está próximo a expirar
    
    Args:
        token (str): Token actual
        minutos_threshold (int): Minutos antes de renovar
        
    Returns:
        str: Token renovado o el mismo token si no es necesario
    """
    try:
        payload = verificar_token_jwt(token)
        if not payload:
            return None
        
        if token_expira_pronto(payload, minutos_threshold):
            # Renovar token con los mismos datos
            nuevo_token = generar_token_jwt(
                payload['codigo_usuario'],
                payload['tenant_id'],
                payload['rol'],
                {k: v for k, v in payload.items() 
                 if k not in ['iss', 'iat', 'exp', 'aud', 'generated_at']}
            )
            
            logger.info(f"Token renovado para usuario: {payload['codigo_usuario']}")
            return nuevo_token
        
        return token
        
    except Exception as e:
        logger.error(f"Error renovando token: {e}")
        return None

def validar_token_en_base_datos(token, tabla_tokens, tenant_id, codigo_usuario):
    """
    Valida si un token existe y está activo en la base de datos
    
    Args:
        token (str): Token a validar
        tabla_tokens (str): Nombre de la tabla de tokens
        tenant_id (str): ID del tenant
        codigo_usuario (str): Código del usuario
        
    Returns:
        bool: True si el token es válido en BD
    """
    try:
        from .dynamodb_utils import get_item_standard
        
        # Buscar token en la tabla correspondiente
        token_data = get_item_standard(tabla_tokens, tenant_id, codigo_usuario)
        
        if not token_data:
            logger.warning(f"Token no encontrado en BD: {codigo_usuario}")
            return False
        
        # Verificar si el token coincide y está activo
        if token_data.get('token') != token and token_data.get('estado') == 'ACTIVO':
            logger.warning(f"Token inválido en BD para usuario: {codigo_usuario}")
            return False
        
        # Verificar fecha de expiración en BD (redundancia)
        expiracion_bd = token_data.get('expira_en')
        if expiracion_bd:
            ahora = datetime.now(timezone.utc)
            exp_dt = datetime.fromisoformat(expiracion_bd.replace('Z', '+00:00'))
            
            if ahora > exp_dt:
                logger.warning(f"Token expirado según BD: {codigo_usuario}")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error validando token en BD: {e}")
        return False