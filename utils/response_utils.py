# utils/response_utils.py
import json
import logging

# Configurar logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def success_response(data=None, mensaje="Operación exitosa", status_code=200):
    """
    Genera una respuesta HTTP exitosa siguiendo el formato SAAI
    
    Args:
        data (dict, optional): Datos a retornar
        mensaje (str): Mensaje de éxito
        status_code (int): Código HTTP de respuesta
        
    Returns:
        dict: Respuesta HTTP formatada
    """
    response_body = {
        "success": True,
        "message": mensaje
    }
    
    if data is not None:
        response_body["data"] = data
    
    response = {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS"
        },
        "body": json.dumps(response_body, ensure_ascii=False, default=str)
    }
    
    # Log de respuesta exitosa
    logger.info(f"Respuesta exitosa: {status_code} - {mensaje}")
    
    return response

def error_response(mensaje="Error interno del servidor", detalles=None, status_code=500):
    """
    Genera una respuesta HTTP de error siguiendo el formato SAAI
    
    Args:
        mensaje (str): Mensaje de error principal
        detalles (dict, optional): Detalles adicionales del error
        status_code (int): Código HTTP de error
        
    Returns:
        dict: Respuesta HTTP de error formatada
    """
    response_body = {
        "success": False,
        "message": mensaje
    }
    
    if detalles is not None:
        response_body["data"] = detalles
    
    response = {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS"
        },
        "body": json.dumps(response_body, ensure_ascii=False, default=str)
    }
    
    # Log de error
    logger.error(f"Respuesta de error: {status_code} - {mensaje}")
    if detalles:
        logger.error(f"Detalles: {detalles}")
    
    return response

def validation_error_response(errores_validacion):
    """
    Genera una respuesta HTTP para errores de validación
    
    Args:
        errores_validacion (dict): Diccionario con errores de validación
        
    Returns:
        dict: Respuesta HTTP de error de validación
    """
    return error_response(
        mensaje="Errores de validación encontrados",
        detalles=errores_validacion,
        status_code=400
    )

def unauthorized_response(mensaje="Token inválido o expirado"):
    """
    Genera una respuesta HTTP para errores de autenticación
    
    Args:
        mensaje (str): Mensaje de error de autenticación
        
    Returns:
        dict: Respuesta HTTP 401
    """
    return error_response(
        mensaje=mensaje,
        status_code=401
    )

def forbidden_response(mensaje="No tienes permisos para realizar esta acción"):
    """
    Genera una respuesta HTTP para errores de autorización
    
    Args:
        mensaje (str): Mensaje de error de autorización
        
    Returns:
        dict: Respuesta HTTP 403
    """
    return error_response(
        mensaje=mensaje,
        status_code=403
    )

def not_found_response(mensaje="Recurso no encontrado"):
    """
    Genera una respuesta HTTP para recursos no encontrados
    
    Args:
        mensaje (str): Mensaje de error
        
    Returns:
        dict: Respuesta HTTP 404
    """
    return error_response(
        mensaje=mensaje,
        status_code=404
    )

def conflict_response(mensaje="Conflicto con el estado actual del recurso"):
    """
    Genera una respuesta HTTP para conflictos
    
    Args:
        mensaje (str): Mensaje de error de conflicto
        
    Returns:
        dict: Respuesta HTTP 409
    """
    return error_response(
        mensaje=mensaje,
        status_code=409
    )

def parse_request_body(event):
    """
    Parsea el body de una request HTTP
    
    Args:
        event (dict): Evento de Lambda
        
    Returns:
        dict: Body parseado o diccionario vacío
    """
    try:
        if event.get('body'):
            if isinstance(event['body'], str):
                return json.loads(event['body'])
            return event['body']
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing request body: {e}")
        return {}

def get_path_parameter(event, parameter_name):
    """
    Extrae un parámetro de la ruta
    
    Args:
        event (dict): Evento de Lambda
        parameter_name (str): Nombre del parámetro
        
    Returns:
        str: Valor del parámetro o None
    """
    path_params = event.get('pathParameters', {})
    if path_params:
        return path_params.get(parameter_name)
    return None

def get_query_parameter(event, parameter_name, default_value=None):
    """
    Extrae un parámetro de query string
    
    Args:
        event (dict): Evento de Lambda
        parameter_name (str): Nombre del parámetro
        default_value: Valor por defecto si no existe
        
    Returns:
        str: Valor del parámetro o valor por defecto
    """
    query_params = event.get('queryStringParameters', {})
    if query_params:
        return query_params.get(parameter_name, default_value)
    return default_value

def get_header(event, header_name):
    """
    Extrae un header de la request
    
    Args:
        event (dict): Evento de Lambda
        header_name (str): Nombre del header
        
    Returns:
        str: Valor del header o None
    """
    headers = event.get('headers', {})
    # Los headers pueden venir en minúsculas
    for key, value in headers.items():
        if key.lower() == header_name.lower():
            return value
    return None

def options_response():
    """
    Genera una respuesta para preflight CORS (OPTIONS)
    
    Returns:
        dict: Respuesta HTTP OPTIONS
    """
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
            "Access-Control-Max-Age": "86400"
        },
        "body": ""
    }

def log_request(event, context=None):
    """
    Registra información de la request para debugging
    
    Args:
        event (dict): Evento de Lambda
        context (optional): Contexto de Lambda (opcional para compatibilidad)
    """
    if context:
        logger.info(f"Request ID: {context.aws_request_id}")
        logger.info(f"Function: {context.function_name}")
    
    logger.info(f"Method: {event.get('httpMethod', 'UNKNOWN')}")
    logger.info(f"Path: {event.get('path', 'UNKNOWN')}")
    
    # No logear el body completo por seguridad (puede contener passwords)
    if event.get('body'):
        logger.info("Body present in request")
    
    # Logear query parameters
    query_params = event.get('queryStringParameters')
    if query_params:
        logger.info(f"Query params: {query_params}")

def extract_tenant_from_jwt_claims(event):
    """
    Extrae el tenant_id de los claims JWT (agregados por el authorizer)
    
    Args:
        event (dict): Evento de Lambda con requestContext
        
    Returns:
        str: tenant_id (codigo_tienda) o None
    """
    try:
        authorizer = event.get('requestContext', {}).get('authorizer', {})
        return authorizer.get('tenant_id')
    except Exception as e:
        logger.error(f"Error extracting tenant from JWT: {e}")
        return None

def extract_user_from_jwt_claims(event):
    """
    Extrae información del usuario de los claims JWT
    
    Args:
        event (dict): Evento de Lambda con requestContext
        
    Returns:
        dict: Información del usuario o None
    """
    try:
        authorizer = event.get('requestContext', {}).get('authorizer', {})
        return {
            'codigo_usuario': authorizer.get('codigo_usuario'),
            'rol': authorizer.get('rol'),
            'tenant_id': authorizer.get('tenant_id')
        }
    except Exception as e:
        logger.error(f"Error extracting user from JWT: {e}")
        return None

def verificar_rol_permitido(event, roles_permitidos):
    """
    Verifica si el usuario tiene uno de los roles permitidos para el endpoint
    
    Args:
        event (dict): Evento de Lambda con requestContext
        roles_permitidos (list): Lista de roles permitidos (ej: ['ADMIN'], ['TRABAJADOR', 'ADMIN'])
        
    Returns:
        tuple: (bool, dict|None) - (tiene_permiso, error_response|None)
        
    Ejemplo:
        tiene_permiso, error = verificar_rol_permitido(event, ['ADMIN'])
        if not tiene_permiso:
            return error
    """
    try:
        user_info = extract_user_from_jwt_claims(event)
        
        if not user_info or not user_info.get('rol'):
            return False, error_response("No autorizado - información de usuario inválida", 401)
        
        rol_usuario = user_info.get('rol', '').upper()
        
        # Normalizar roles permitidos a mayúsculas
        roles_normalizados = [r.upper() for r in roles_permitidos]
        
        if rol_usuario not in roles_normalizados:
            roles_str = ', '.join(roles_permitidos)
            return False, forbidden_response(f"Acceso denegado. Roles permitidos: {roles_str}")
        
        return True, None
        
    except Exception as e:
        logger.error(f"Error verificando rol: {e}")
        return False, error_response("Error verificando permisos", 500)