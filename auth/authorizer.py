# auth/authorizer.py
import json
import logging
import os
from utils import (
    verificar_token_jwt, 
    generar_claims_authorizer,
    validar_token_en_base_datos
)

# Configurar logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas de tokens por rol
TOKENS_TRABAJADORES_TABLE = os.environ.get('TOKENS_TRABAJADORES_TABLE')
TOKENS_ADMINISTRADORES_TABLE = os.environ.get('TOKENS_ADMINISTRADORES_TABLE')
TOKENS_SAAI_TABLE = os.environ.get('TOKENS_SAAI_TABLE')

def handler(event, context):
    """
    Lambda Authorizer para validación JWT en todas las rutas privadas
    
    CRÍTICO: Esta función es el punto de entrada para TODA la seguridad multi-tenant
    - Valida JWT y extrae claims (codigo_usuario, tenant_id, rol)
    - Verifica token activo en tabla correspondiente por rol
    - Pasa claims al requestContext para aislamiento de datos
    - Genera policy IAM con contexto de autorización
    
    Args:
        event: Evento del API Gateway con token en authorizationToken
        context: Contexto de Lambda
        
    Returns:
        dict: Policy IAM + authorizer context con claims
    """
    try:
        logger.info(f"Authorizer invocado - Request ID: {context.aws_request_id}")
        
        # Extraer token del evento
        token = event.get('authorizationToken')
        if not token:
            logger.error("Token de autorización no encontrado en el evento")
            raise Exception('Unauthorized')
        
        # Limpiar token (remover 'Bearer ' si existe)
        if token.startswith('Bearer '):
            token = token[7:]
        
        logger.info(f"Token extraído, longitud: {len(token)}")
        
        # Verificar y decodificar JWT
        payload = verificar_token_jwt(token)
        if not payload:
            logger.error("Token JWT inválido o expirado")
            raise Exception('Unauthorized')
        
        # Extraer datos críticos del payload
        codigo_usuario = payload.get('codigo_usuario')
        tenant_id = payload.get('tenant_id')
        rol = payload.get('rol')
        
        # Validaciones de seguridad obligatorias
        if not codigo_usuario or not tenant_id or not rol:
            logger.error(f"Claims obligatorios faltantes: user={codigo_usuario}, tenant={tenant_id}, rol={rol}")
            raise Exception('Unauthorized')
        
        # Validar rol válido (aceptar mayúsculas y minúsculas)
        roles_validos = ['TRABAJADOR', 'ADMIN', 'SAAI', 'worker', 'admin', 'saai']
        if rol not in roles_validos:
            logger.error(f"Rol inválido en token: {rol}")
            raise Exception('Unauthorized')
        
        # Determinar tabla de tokens según el rol
        tabla_tokens = obtener_tabla_tokens_por_rol(rol)
        if not tabla_tokens:
            logger.error(f"Tabla de tokens no configurada para rol: {rol}")
            raise Exception('Unauthorized')
        
        # Validar token activo en base de datos
        token_valido_bd = validar_token_en_base_datos(
            token, tabla_tokens, tenant_id, codigo_usuario
        )
        
        if not token_valido_bd:
            logger.error(f"Token no encontrado o inactivo en BD: {codigo_usuario}")
            raise Exception('Unauthorized')
        
        # Generar ARN del recurso
        method_arn = event['methodArn']
        
        # Validar restricciones adicionales por rol (rutas permitidas/prohibidas)
        if not validar_restricciones_adicionales(payload, method_arn):
            logger.warning(f"Restricciones adicionales fallaron para rol={rol} en {method_arn}")
            raise Exception('Unauthorized')
        
        # Extraer información del ARN para policy
        arn_parts = method_arn.split(':')
        api_gateway_arn = ':'.join(arn_parts[:4]) + ':' + arn_parts[4]
        
        # Generar claims para el context
        authorizer_context = generar_claims_authorizer(payload)
        
        # Crear policy IAM de autorización
        policy = generar_policy_iam('Allow', method_arn, authorizer_context)
        
        logger.info(f"Autorización exitosa: usuario={codigo_usuario}, tenant={tenant_id}, rol={rol}")
        
        return policy
        
    except Exception as e:
        logger.error(f"Error en autorización: {e}")
        # Retornar policy de denegación
        return generar_policy_iam('Deny', event.get('methodArn', '*'))

def obtener_tabla_tokens_por_rol(rol):
    """
    Obtiene la tabla de tokens correspondiente según el rol
    
    Args:
        rol (str): Rol del usuario (TRABAJADOR, ADMIN, SAAI)
        
    Returns:
        str: Nombre de la tabla de tokens
    """
    tablas_por_rol = {
        'TRABAJADOR': TOKENS_TRABAJADORES_TABLE,
        'ADMIN': TOKENS_ADMINISTRADORES_TABLE,
        'SAAI': TOKENS_SAAI_TABLE,
        'worker': TOKENS_TRABAJADORES_TABLE,
        'admin': TOKENS_ADMINISTRADORES_TABLE,
        'saai': TOKENS_SAAI_TABLE
    }
    
    return tablas_por_rol.get(rol)

def generar_policy_iam(effect, resource, context=None):
    """
    Genera una policy IAM para el API Gateway
    
    Args:
        effect (str): 'Allow' o 'Deny'
        resource (str): ARN del recurso
        context (dict, optional): Contexto del authorizer
        
    Returns:
        dict: Policy IAM formateada
    """
    policy = {
        'principalId': 'user',
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': 'execute-api:Invoke',
                    'Effect': effect,
                    'Resource': resource
                }
            ]
        }
    }
    
    # Agregar context si se proporciona (solo para Allow)
    if context and effect == 'Allow':
        policy['context'] = context
    
    return policy

def validar_restricciones_adicionales(payload, method_arn):
    """
    Validaciones adicionales de seguridad basadas en el contexto
    
    Args:
        payload (dict): Payload del JWT
        method_arn (str): ARN del método invocado
        
    Returns:
        bool: True si pasa las validaciones adicionales
    """
    try:
        rol = payload.get('rol')
        
        # Normalizar rol a mayúsculas para comparación
        rol_upper = rol.upper() if rol else ''
        
        # Extraer path del ARN
        arn_parts = method_arn.split('/')
        path = '/' + '/'.join(arn_parts[3:]) if len(arn_parts) > 3 else ''
        
        # Restricciones por rol
        if rol_upper == 'TRABAJADOR':
            # TRABAJADOR solo puede acceder a productos y ventas (rutas restringidas desde env var)
            restricted_paths_str = os.environ.get('RESTRICTED_PATHS_WORKER', '/gastos,/analytics,/reportes')
            restricted_paths = [p.strip() for p in restricted_paths_str.split(',') if p.strip()]
            
            # Verificar si intenta acceder a ruta restringida
            if any(path.startswith(ruta) for ruta in restricted_paths):
                logger.warning(f"TRABAJADOR intenta acceder a ruta restringida: {path}")
                return False
        
        elif rol_upper == 'ADMIN':
            # ADMIN puede acceder a todo excepto gestión de tiendas
            rutas_prohibidas = ['/tiendas']
            if any(path.startswith(ruta) for ruta in rutas_prohibidas):
                logger.warning(f"ADMIN intenta acceder a ruta prohibida: {path}")
                return False
        
        elif rol_upper == 'SAAI':
            # SAAI solo puede gestionar tiendas y ver notificaciones
            rutas_permitidas = ['/tiendas', '/notificacion']
            if not any(path.startswith(ruta) for ruta in rutas_permitidas):
                logger.warning(f"SAAI intenta acceder a ruta no permitida: {path}")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error validando restricciones adicionales: {e}")
        return False

def log_evento_autorizacion(payload, method_arn, resultado):
    """
    Registra evento de autorización para auditoría
    
    Args:
        payload (dict): Payload del JWT
        method_arn (str): ARN del método
        resultado (str): 'ALLOW' o 'DENY'
    """
    try:
        log_data = {
            'tipo': 'AUTORIZACION',
            'resultado': resultado,
            'usuario': payload.get('codigo_usuario'),
            'tenant': payload.get('tenant_id'),
            'rol': payload.get('rol'),
            'recurso': method_arn,
            'timestamp': payload.get('generated_at')
        }
        
        logger.info(f"AUDIT: {json.dumps(log_data)}")
        
    except Exception as e:
        logger.error(f"Error logging evento de autorización: {e}")

# Versión del authorizer para cache invalidation
AUTHORIZER_VERSION = "1.0.0"