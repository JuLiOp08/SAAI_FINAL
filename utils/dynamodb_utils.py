# utils/dynamodb_utils.py
import boto3
import json
import logging
from botocore.exceptions import ClientError
from datetime import datetime
from .datetime_utils import obtener_fecha_hora_peru

# Configurar logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Cliente DynamoDB
dynamodb = boto3.resource('dynamodb')

def get_table(table_name):
    """
    Obtiene una tabla DynamoDB
    
    Args:
        table_name (str): Nombre de la tabla
        
    Returns:
        Table: Instancia de la tabla DynamoDB
    """
    return dynamodb.Table(table_name)

def put_item_standard(table_name, tenant_id, entity_id, data):
    """
    Inserta un item usando el modelo estándar SAAI: tenant_id + entity_id + data
    
    Args:
        table_name (str): Nombre de la tabla
        tenant_id (str): ID del tenant (codigo_tienda)
        entity_id (str): ID de la entidad
        data (dict): Datos completos de la entidad
        
    Returns:
        bool: True si fue exitoso, False en caso contrario
    """
    try:
        table = get_table(table_name)
        
        # Asegurar que data tenga campos básicos
        if 'created_at' not in data:
            data['created_at'] = obtener_fecha_hora_peru()
        
        data['updated_at'] = obtener_fecha_hora_peru()
        
        item = {
            'tenant_id': tenant_id,
            'entity_id': entity_id,
            'data': data
        }
        
        table.put_item(Item=item)
        logger.info(f"Item insertado: tabla={table_name}, tenant={tenant_id}, entity={entity_id}")
        return True
        
    except ClientError as e:
        logger.error(f"Error insertando item en {table_name}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error inesperado insertando item: {e}")
        return False

def get_item_standard(table_name, tenant_id, entity_id):
    """
    Obtiene un item usando el modelo estándar SAAI
    
    Args:
        table_name (str): Nombre de la tabla
        tenant_id (str): ID del tenant
        entity_id (str): ID de la entidad
        
    Returns:
        dict: Data del item o None si no existe
    """
    try:
        table = get_table(table_name)
        
        response = table.get_item(
            Key={
                'tenant_id': tenant_id,
                'entity_id': entity_id
            }
        )
        
        item = response.get('Item')
        if item:
            # Retornar solo la data, no las keys
            data = item.get('data', {})
            logger.info(f"Item encontrado: tabla={table_name}, tenant={tenant_id}, entity={entity_id}")
            return data
        else:
            logger.info(f"Item no encontrado: tabla={table_name}, tenant={tenant_id}, entity={entity_id}")
            return None
            
    except ClientError as e:
        logger.error(f"Error obteniendo item de {table_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error inesperado obteniendo item: {e}")
        return None

def update_item_standard(table_name, tenant_id, entity_id, data_updates):
    """
    Actualiza un item usando el modelo estándar SAAI
    
    Args:
        table_name (str): Nombre de la tabla
        tenant_id (str): ID del tenant
        entity_id (str): ID de la entidad
        data_updates (dict): Campos a actualizar en data
        
    Returns:
        bool: True si fue exitoso, False en caso contrario
    """
    try:
        table = get_table(table_name)
        
        # Obtener item actual
        current_data = get_item_standard(table_name, tenant_id, entity_id)
        if current_data is None:
            logger.warning(f"Intento de actualizar item inexistente: {table_name}, {tenant_id}, {entity_id}")
            return False
        
        # Mergear datos actuales con updates
        updated_data = {**current_data, **data_updates}
        updated_data['updated_at'] = obtener_fecha_hora_peru()
        
        # Actualizar item completo
        table.update_item(
            Key={
                'tenant_id': tenant_id,
                'entity_id': entity_id
            },
            UpdateExpression='SET #data = :data',
            ExpressionAttributeNames={
                '#data': 'data'
            },
            ExpressionAttributeValues={
                ':data': updated_data
            }
        )
        
        logger.info(f"Item actualizado: tabla={table_name}, tenant={tenant_id}, entity={entity_id}")
        return True
        
    except ClientError as e:
        logger.error(f"Error actualizando item en {table_name}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error inesperado actualizando item: {e}")
        return False

def delete_item_standard(table_name, tenant_id, entity_id, soft_delete=True):
    """
    Elimina un item. Por defecto usa soft delete (estado=INACTIVO)
    
    Args:
        table_name (str): Nombre de la tabla
        tenant_id (str): ID del tenant
        entity_id (str): ID de la entidad
        soft_delete (bool): True para soft delete, False para hard delete
        
    Returns:
        bool: True si fue exitoso, False en caso contrario
    """
    try:
        table = get_table(table_name)
        
        if soft_delete:
            # Soft delete: actualizar estado
            return update_item_standard(table_name, tenant_id, entity_id, {
                'estado': 'INACTIVO',
                'fecha_eliminacion': obtener_fecha_hora_peru()
            })
        else:
            # Hard delete: eliminar físicamente
            table.delete_item(
                Key={
                    'tenant_id': tenant_id,
                    'entity_id': entity_id
                }
            )
            
            logger.info(f"Item eliminado (hard): tabla={table_name}, tenant={tenant_id}, entity={entity_id}")
            return True
        
    except ClientError as e:
        logger.error(f"Error eliminando item de {table_name}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error inesperado eliminando item: {e}")
        return False

def query_by_tenant(table_name, tenant_id, filter_expression=None, limit=None, last_evaluated_key=None, include_inactive=False):
    """
    Consulta todos los items de un tenant con paginación
    
    Args:
        table_name (str): Nombre de la tabla
        tenant_id (str): ID del tenant
        filter_expression: Expresión de filtro opcional
        limit (int): Límite de items por página
        last_evaluated_key: Clave para paginación
        include_inactive (bool): True para incluir registros INACTIVOS
        
    Returns:
        dict: {'items': [...], 'last_evaluated_key': ..., 'count': ...}
    """
    try:
        table = get_table(table_name)
        
        query_params = {
            'KeyConditionExpression': boto3.dynamodb.conditions.Key('tenant_id').eq(tenant_id)
        }
        
        # Filtrar INACTIVOS por defecto según especificación SAAI
        if not include_inactive:
            from boto3.dynamodb.conditions import Attr
            estado_filter = Attr('data.estado').ne('INACTIVO')
            
            if filter_expression:
                combined_filter = filter_expression & estado_filter
                query_params['FilterExpression'] = combined_filter
            else:
                query_params['FilterExpression'] = estado_filter
        elif filter_expression:
            query_params['FilterExpression'] = filter_expression
        
        if limit:
            query_params['Limit'] = limit
        
        if last_evaluated_key:
            query_params['ExclusiveStartKey'] = last_evaluated_key
        
        response = table.query(**query_params)
        
        # Extraer solo la data de cada item
        items = []
        for item in response.get('Items', []):
            data = item.get('data', {})
            # Agregar las keys para identificación
            data['_tenant_id'] = item['tenant_id']
            data['_entity_id'] = item['entity_id']
            items.append(data)
        
        result = {
            'items': items,
            'count': len(items),
            'scanned_count': response.get('ScannedCount', 0)
        }
        
        if 'LastEvaluatedKey' in response:
            result['last_evaluated_key'] = response['LastEvaluatedKey']
        
        logger.info(f"Query exitosa: tabla={table_name}, tenant={tenant_id}, items={len(items)}")
        return result
        
    except ClientError as e:
        logger.error(f"Error consultando tabla {table_name}: {e}")
        return {'items': [], 'count': 0, 'scanned_count': 0}
    except Exception as e:
        logger.error(f"Error inesperado consultando tabla: {e}")
        return {'items': [], 'count': 0, 'scanned_count': 0}

def query_by_tenant_with_filter(table_name, tenant_id, filter_conditions, limit=None, last_evaluated_key=None, include_inactive=False):
    """
    Consulta items de un tenant con filtros específicos en la data
    
    Args:
        table_name (str): Nombre de la tabla
        tenant_id (str): ID del tenant
        filter_conditions (dict): Condiciones de filtro sobre campos de data
        limit (int): Límite de items
        last_evaluated_key: Clave para paginación
        include_inactive (bool): True para incluir registros INACTIVOS
        
    Returns:
        dict: Resultado con items filtrados
    """
    try:
        # Construir FilterExpression dinámicamente
        from boto3.dynamodb.conditions import Attr, And
        
        filter_expressions = []
        
        for field, value in filter_conditions.items():
            if isinstance(value, dict):
                # Operadores especiales
                if 'contains' in value:
                    filter_expressions.append(Attr(f'data.{field}').contains(value['contains']))
                elif 'begins_with' in value:
                    filter_expressions.append(Attr(f'data.{field}').begins_with(value['begins_with']))
                elif 'between' in value:
                    filter_expressions.append(Attr(f'data.{field}').between(value['between'][0], value['between'][1]))
                elif 'gt' in value:
                    filter_expressions.append(Attr(f'data.{field}').gt(value['gt']))
                elif 'gte' in value:
                    filter_expressions.append(Attr(f'data.{field}').gte(value['gte']))
                elif 'lt' in value:
                    filter_expressions.append(Attr(f'data.{field}').lt(value['lt']))
                elif 'lte' in value:
                    filter_expressions.append(Attr(f'data.{field}').lte(value['lte']))
            else:
                # Igualdad simple
                filter_expressions.append(Attr(f'data.{field}').eq(value))
        
        # Combinar filtros con AND
        combined_filter = None
        if len(filter_expressions) == 1:
            combined_filter = filter_expressions[0]
        elif len(filter_expressions) > 1:
            combined_filter = filter_expressions[0]
            for expr in filter_expressions[1:]:
                combined_filter = combined_filter & expr
        
        return query_by_tenant(table_name, tenant_id, combined_filter, limit, last_evaluated_key, include_inactive)
        
    except Exception as e:
        logger.error(f"Error construyendo filtros: {e}")
        return {'items': [], 'count': 0, 'scanned_count': 0}

def increment_counter(table_name, tenant_id, counter_name, increment=1):
    """
    Incrementa un contador atómicamente
    
    Args:
        table_name (str): Tabla de contadores
        tenant_id (str): ID del tenant
        counter_name (str): Nombre del contador
        increment (int): Cantidad a incrementar
        
    Returns:
        int: Nuevo valor del contador
    """
    try:
        table = get_table(table_name)
        
        response = table.update_item(
            Key={
                'tenant_id': tenant_id,
                'entity_id': counter_name
            },
            UpdateExpression='SET #data.#value = if_not_exists(#data.#value, :zero) + :inc',
            ExpressionAttributeNames={
                '#data': 'data',
                '#value': 'value'
            },
            ExpressionAttributeValues={
                ':zero': 0,
                ':inc': increment
            },
            ReturnValues='UPDATED_NEW'
        )
        
        new_value = response['Attributes']['data']['value']
        logger.info(f"Counter incrementado: {counter_name} = {new_value}")
        return new_value
        
    except ClientError as e:
        logger.error(f"Error incrementando counter: {e}")
        return None
    except Exception as e:
        logger.error(f"Error inesperado incrementando counter: {e}")
        return None

def batch_write_items(table_name, items):
    """
    Inserta múltiples items en batch
    
    Args:
        table_name (str): Nombre de la tabla
        items (list): Lista de items a insertar
        
    Returns:
        bool: True si todos fueron insertados exitosamente
    """
    try:
        table = get_table(table_name)
        
        # DynamoDB batch_writer maneja automáticamente las batches de 25 items
        with table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)
        
        logger.info(f"Batch write exitoso: {len(items)} items insertados en {table_name}")
        return True
        
    except ClientError as e:
        logger.error(f"Error en batch write: {e}")
        return False
    except Exception as e:
        logger.error(f"Error inesperado en batch write: {e}")
        return False

def decimal_to_float(value):
    """
    Convierte valores Decimal de DynamoDB a float para JSON serialization
    Necesario porque DynamoDB retorna números como Decimal, pero JSON no los soporta
    
    Args:
        value: Valor a convertir (puede ser Decimal, int, float, None)
        
    Returns:
        float: Valor convertido o 0.0 si es None
    """
    from decimal import Decimal
    
    if value is None:
        return 0.0
    
    if isinstance(value, Decimal):
        return float(value)
    
    if isinstance(value, (int, float)):
        return float(value)
    
    # Si es string, intentar convertir
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            logger.warning(f"No se pudo convertir '{value}' a float, retornando 0.0")
            return 0.0
    
    logger.warning(f"Tipo no soportado para decimal_to_float: {type(value)}, retornando 0.0")
    return 0.0