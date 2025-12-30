# utils/pagination_utils.py
import json
import base64
import logging
from urllib.parse import quote, unquote

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def crear_cursor_paginacion(last_evaluated_key):
    """
    Crea un cursor de paginación codificado desde LastEvaluatedKey de DynamoDB
    
    Args:
        last_evaluated_key (dict): LastEvaluatedKey de DynamoDB
        
    Returns:
        str: Cursor codificado en base64
    """
    try:
        if not last_evaluated_key:
            return None
        
        # Convertir a JSON y codificar en base64
        json_str = json.dumps(last_evaluated_key, default=str, sort_keys=True)
        cursor = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
        
        logger.debug(f"Cursor creado: {cursor[:50]}...")
        return cursor
        
    except Exception as e:
        logger.error(f"Error creando cursor: {e}")
        return None

def decodificar_cursor_paginacion(cursor):
    """
    Decodifica un cursor de paginación a LastEvaluatedKey
    
    Args:
        cursor (str): Cursor codificado
        
    Returns:
        dict: LastEvaluatedKey decodificado o None
    """
    try:
        if not cursor:
            return None
        
        # Decodificar base64 y parsear JSON
        json_str = base64.b64decode(cursor.encode('utf-8')).decode('utf-8')
        last_evaluated_key = json.loads(json_str)
        
        logger.debug(f"Cursor decodificado exitosamente")
        return last_evaluated_key
        
    except Exception as e:
        logger.error(f"Error decodificando cursor: {e}")
        return None

def extraer_parametros_paginacion(event, limit_default=20, limit_max=100):
    """
    Extrae parámetros de paginación de la request
    
    Args:
        event (dict): Evento de Lambda
        limit_default (int): Límite por defecto
        limit_max (int): Límite máximo permitido
        
    Returns:
        dict: {'limit': int, 'cursor': str, 'last_evaluated_key': dict}
    """
    try:
        query_params = event.get('queryStringParameters') or {}
        
        # Extraer limit
        limit_str = query_params.get('limit', str(limit_default))
        try:
            limit = int(limit_str)
            # Aplicar límites
            if limit < 1:
                limit = limit_default
            elif limit > limit_max:
                limit = limit_max
        except ValueError:
            limit = limit_default
        
        # Extraer cursor
        cursor = query_params.get('cursor')
        last_evaluated_key = None
        
        if cursor:
            last_evaluated_key = decodificar_cursor_paginacion(cursor)
            if not last_evaluated_key:
                logger.warning("Cursor inválido proporcionado")
        
        return {
            'limit': limit,
            'cursor': cursor,
            'last_evaluated_key': last_evaluated_key
        }
        
    except Exception as e:
        logger.error(f"Error extrayendo parámetros de paginación: {e}")
        return {
            'limit': limit_default,
            'cursor': None,
            'last_evaluated_key': None
        }

def crear_respuesta_paginada(items, count, last_evaluated_key=None, pagina_actual=None, total_estimado=None):
    """
    Crea una respuesta paginada siguiendo el formato SAAI
    
    Args:
        items (list): Lista de items de la página actual
        count (int): Cantidad de items en la página actual
        last_evaluated_key (dict, optional): LastEvaluatedKey de DynamoDB
        pagina_actual (int, optional): Número de página actual
        total_estimado (int, optional): Total estimado de items
        
    Returns:
        dict: Respuesta paginada formateada
    """
    try:
        respuesta = {
            'items': items,
            'pagination': {
                'count': count,
                'has_more': last_evaluated_key is not None,
            }
        }
        
        # Agregar cursor para siguiente página si existe
        if last_evaluated_key:
            cursor = crear_cursor_paginacion(last_evaluated_key)
            if cursor:
                respuesta['pagination']['next_cursor'] = cursor
        
        # Agregar información adicional si está disponible
        if pagina_actual is not None:
            respuesta['pagination']['current_page'] = pagina_actual
        
        if total_estimado is not None:
            respuesta['pagination']['total_estimated'] = total_estimado
        
        logger.info(f"Respuesta paginada creada: {count} items, has_more={respuesta['pagination']['has_more']}")
        return respuesta
        
    except Exception as e:
        logger.error(f"Error creando respuesta paginada: {e}")
        return {
            'items': items or [],
            'pagination': {
                'count': len(items or []),
                'has_more': False
            }
        }

def calcular_offset_y_pagina(cursor, limit):
    """
    Calcula el offset aproximado y número de página basado en cursor y limit
    
    Args:
        cursor (str): Cursor de paginación
        limit (int): Límite por página
        
    Returns:
        dict: {'offset_estimado': int, 'pagina_estimada': int}
    """
    try:
        if not cursor:
            return {'offset_estimado': 0, 'pagina_estimada': 1}
        
        # Esto es una aproximación ya que DynamoDB no maneja offset tradicional
        # En un escenario real, podrías almacenar metadata adicional en el cursor
        
        # Por ahora, basamos en el length del cursor (heurística simple)
        cursor_complexity = len(cursor)
        offset_estimado = (cursor_complexity // 10) * limit  # Muy aproximado
        pagina_estimada = max(1, offset_estimado // limit + 1)
        
        return {
            'offset_estimado': offset_estimado,
            'pagina_estimada': pagina_estimada
        }
        
    except Exception as e:
        logger.error(f"Error calculando offset: {e}")
        return {'offset_estimado': 0, 'pagina_estimada': 1}

def validar_parametros_busqueda(event, campos_permitidos):
    """
    Valida y extrae parámetros de búsqueda de la request
    
    Args:
        event (dict): Evento de Lambda
        campos_permitidos (list): Lista de campos permitidos para búsqueda
        
    Returns:
        dict: Parámetros de búsqueda validados
    """
    try:
        from .response_utils import parse_request_body
        
        body = parse_request_body(event)
        
        # Extraer query de búsqueda
        query = body.get('query', '').strip()
        
        # Extraer filtros
        filtros = body.get('filtros', {})
        filtros_validados = {}
        
        # Validar que solo se usen campos permitidos
        for campo, valor in filtros.items():
            if campo in campos_permitidos and valor is not None:
                # Normalizar valor
                if isinstance(valor, str):
                    valor = valor.strip()
                    if valor:  # Solo agregar si no está vacío
                        filtros_validados[campo] = valor
                else:
                    filtros_validados[campo] = valor
        
        # Extraer parámetros de ordenamiento
        orden_campo = body.get('orden_campo')
        orden_direccion = body.get('orden_direccion', 'asc').lower()
        
        if orden_campo and orden_campo not in campos_permitidos:
            logger.warning(f"Campo de orden no permitido: {orden_campo}")
            orden_campo = None
        
        if orden_direccion not in ['asc', 'desc']:
            orden_direccion = 'asc'
        
        return {
            'query': query,
            'filtros': filtros_validados,
            'orden_campo': orden_campo,
            'orden_direccion': orden_direccion,
            'tiene_filtros': len(filtros_validados) > 0 or bool(query)
        }
        
    except Exception as e:
        logger.error(f"Error validando parámetros de búsqueda: {e}")
        return {
            'query': '',
            'filtros': {},
            'orden_campo': None,
            'orden_direccion': 'asc',
            'tiene_filtros': False
        }

def crear_filtros_dynamodb_desde_busqueda(parametros_busqueda, mapeo_campos):
    """
    Convierte parámetros de búsqueda a filtros de DynamoDB
    
    Args:
        parametros_busqueda (dict): Parámetros extraídos de validar_parametros_busqueda
        mapeo_campos (dict): Mapeo de nombres frontend a nombres en data
        
    Returns:
        dict: Filtros para dynamodb_utils.query_by_tenant_with_filter
    """
    try:
        filtros_db = {}
        
        query = parametros_busqueda.get('query', '')
        filtros = parametros_busqueda.get('filtros', {})
        
        # Procesar filtros específicos
        for campo_frontend, valor in filtros.items():
            campo_db = mapeo_campos.get(campo_frontend, campo_frontend)
            
            if isinstance(valor, str) and valor:
                # Para strings, usar contains (búsqueda parcial)
                filtros_db[campo_db] = {'contains': valor.lower()}
            elif isinstance(valor, (int, float)):
                # Para números, igualdad exacta
                filtros_db[campo_db] = valor
            elif isinstance(valor, dict):
                # Para rangos u operadores específicos
                filtros_db[campo_db] = valor
        
        # Procesar query general (búsqueda en múltiples campos)
        if query:
            # Para DynamoDB, necesitaríamos hacer múltiples queries o usar scan con filtro
            # Por simplicidad, agregar como filtro en el campo principal
            campo_principal = list(mapeo_campos.values())[0] if mapeo_campos else 'nombre'
            if campo_principal not in filtros_db:
                filtros_db[campo_principal] = {'contains': query.lower()}
        
        logger.debug(f"Filtros DynamoDB generados: {filtros_db}")
        return filtros_db
        
    except Exception as e:
        logger.error(f"Error creando filtros DynamoDB: {e}")
        return {}

def ordenar_items_en_memoria(items, orden_campo, orden_direccion):
    """
    Ordena una lista de items en memoria (para cuando DynamoDB no puede ordenar)
    
    Args:
        items (list): Lista de items a ordenar
        orden_campo (str): Campo por el cual ordenar
        orden_direccion (str): 'asc' o 'desc'
        
    Returns:
        list: Items ordenados
    """
    try:
        if not items or not orden_campo:
            return items
        
        reverse = orden_direccion == 'desc'
        
        def get_sort_key(item):
            valor = item.get(orden_campo)
            # Manejar valores None o vacíos
            if valor is None:
                return '' if isinstance(valor, str) else 0
            if isinstance(valor, str):
                return valor.lower()  # Ordenar case-insensitive
            return valor
        
        items_ordenados = sorted(items, key=get_sort_key, reverse=reverse)
        
        logger.debug(f"Items ordenados por {orden_campo} ({orden_direccion}): {len(items_ordenados)} items")
        return items_ordenados
        
    except Exception as e:
        logger.error(f"Error ordenando items: {e}")
        return items