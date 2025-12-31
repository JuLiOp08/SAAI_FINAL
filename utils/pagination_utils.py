# utils/pagination_utils.py
import json
import base64
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def create_next_token(last_evaluated_key):
    """
    Crea un next_token desde LastEvaluatedKey de DynamoDB
    Según documentación SAAI: usar next_token para paginación
    
    Args:
        last_evaluated_key (dict): LastEvaluatedKey de DynamoDB
        
    Returns:
        str: next_token codificado en base64 o None
    """
    try:
        if not last_evaluated_key:
            return None
        
        json_str = json.dumps(last_evaluated_key, default=str, sort_keys=True)
        next_token = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
        
        return next_token
        
    except Exception as e:
        logger.error(f"Error creando next_token: {e}")
        return None

def decode_next_token(next_token):
    """
    Decodifica un next_token a LastEvaluatedKey para DynamoDB
    
    Args:
        next_token (str): Token codificado
        
    Returns:
        dict: LastEvaluatedKey decodificado o None
    """
    try:
        if not next_token:
            return None
        
        json_str = base64.b64decode(next_token.encode('utf-8')).decode('utf-8')
        last_evaluated_key = json.loads(json_str)
        
        return last_evaluated_key
        
    except Exception as e:
        logger.error(f"Error decodificando next_token: {e}")
        return None

def extract_pagination_params(event, default_limit=50, max_limit=100):
    """
    Extrae parámetros de paginación según documentación SAAI oficial:
    - limit (querystring)
    - next_token (querystring)
    
    Args:
        event (dict): Evento de Lambda
        default_limit (int): Límite por defecto
        max_limit (int): Límite máximo
        
    Returns:
        dict: {'limit': int, 'exclusive_start_key': dict}
    """
    try:
        query_params = event.get('queryStringParameters') or {}
        
        # Extraer limit
        limit_str = query_params.get('limit', str(default_limit))
        try:
            limit = int(limit_str)
            if limit < 1:
                limit = default_limit
            elif limit > max_limit:
                limit = max_limit
        except ValueError:
            limit = default_limit
        
        # Extraer next_token y convertir a ExclusiveStartKey
        next_token = query_params.get('next_token')
        exclusive_start_key = decode_next_token(next_token) if next_token else None
        
        return {
            'limit': limit,
            'exclusive_start_key': exclusive_start_key
        }
        
    except Exception as e:
        logger.error(f"Error extrayendo parámetros de paginación: {e}")
        return {
            'limit': default_limit,
            'exclusive_start_key': None
        }