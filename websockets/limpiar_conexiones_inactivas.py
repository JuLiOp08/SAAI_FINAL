# websockets/limpiar_conexiones_inactivas.py
import os
import logging
import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

WS_CONNECTIONS_TABLE = os.environ.get('WS_CONNECTIONS_TABLE')

def handler(event, context):
    """
    Lambda de mantenimiento - Limpia conexiones INACTIVAS de la tabla
    
    Esta lambda se ejecuta manualmente o via EventBridge para limpiar
    conexiones WebSocket que quedaron marcadas como INACTIVAS.
    
    Las conexiones WebSocket deben eliminarse completamente (hard delete),
    no usar soft delete como otras entidades del sistema.
    """
    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(WS_CONNECTIONS_TABLE)
        
        # Scan para encontrar todas las conexiones INACTIVAS
        response = table.scan(
            FilterExpression=Attr('estado').eq('INACTIVO')
        )
        
        inactive_connections = response.get('Items', [])
        deleted_count = 0
        
        logger.info(f"Encontradas {len(inactive_connections)} conexiones INACTIVAS")
        
        # Eliminar cada conexión inactiva (hard delete)
        for connection in inactive_connections:
            tenant_id = connection.get('tenant_id')
            entity_id = connection.get('entity_id')
            
            if tenant_id and entity_id:
                try:
                    table.delete_item(
                        Key={
                            'tenant_id': tenant_id,
                            'entity_id': entity_id
                        }
                    )
                    deleted_count += 1
                    logger.info(f"Conexión eliminada: {entity_id} de tienda {tenant_id}")
                except Exception as delete_error:
                    logger.error(f"Error eliminando {entity_id}: {delete_error}")
        
        logger.info(f"Limpieza completada: {deleted_count} conexiones eliminadas")
        
        return {
            'statusCode': 200,
            'body': {
                'message': 'Limpieza exitosa',
                'inactive_found': len(inactive_connections),
                'deleted': deleted_count
            }
        }
        
    except Exception as e:
        logger.error(f"Error en limpieza de conexiones: {str(e)}")
        return {
            'statusCode': 500,
            'body': {'error': str(e)}
        }
