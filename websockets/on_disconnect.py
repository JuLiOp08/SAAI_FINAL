# websockets/on_disconnect.py
import os
import json
import logging
from utils import (
    log_request,
    delete_item_standard
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
WS_CONNECTIONS_TABLE = os.environ.get('WS_CONNECTIONS_TABLE')

def handler(event, context):
    """
    WebSocket $disconnect - Limpiar conexión
    
    Según documento SAAI:
    - Se ejecuta cuando el cliente cierra la conexión o esta expira
    - Elimina la conexión en t_ws_connections para evitar envíos fallidos
    - Mantiene el estado de conexiones activo consistente
    
    Tablas: t_ws_connections (DELETE)
    Servicios: API Gateway WebSocket (route: $disconnect)
    """
    try:
        log_request(event)
        
        # Obtener connection_id del contexto WebSocket
        connection_id = event.get('requestContext', {}).get('connectionId')
        if not connection_id:
            logger.error("Connection ID no encontrado en el evento de desconexión")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Connection ID requerido'})
            }
        
        # Para la desconexión, buscamos la conexión usando un GSI
        # entity_id = connection_id según modelo estándar SAAI
        
        # Buscar la conexión en DynamoDB para obtener el tenant_id
        import boto3
        from boto3.dynamodb.conditions import Key
        
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(WS_CONNECTIONS_TABLE)
        
        try:
            # Scan para encontrar tenant_id por connection_id
            # En producción, considera agregar GSI: entity_id-index
            response = table.scan(
                FilterExpression='entity_id = :conn_id',
                ExpressionAttributeValues={
                    ':conn_id': connection_id
                },
                Limit=1
            )
            
            if not response.get('Items'):
                logger.warning(f"Conexión no encontrada para cleanup: {connection_id}")
                return {
                    'statusCode': 200,
                    'body': json.dumps({'message': 'Conexión no encontrada, posiblemente ya eliminada'})
                }
            
            # Obtener la primera (y única) conexión encontrada
            connection_item = response['Items'][0]
            tenant_id = connection_item.get('tenant_id')
            
            if not tenant_id:
                logger.error(f"tenant_id no encontrado para conexión: {connection_id}")
                return {
                    'statusCode': 500,
                    'body': json.dumps({'error': 'Error interno - tenant_id faltante'})
                }
            
            # Eliminar la conexión usando delete_item_standard
            success = delete_item_standard(
                WS_CONNECTIONS_TABLE,
                tenant_id,
                connection_id
            )
            
            if success:
                logger.info(f"Conexión WebSocket eliminada: {connection_id} de tienda {tenant_id}")
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Conexión WebSocket eliminada exitosamente',
                        'connection_id': connection_id
                    })
                }
            else:
                logger.error(f"Error eliminando conexión: {connection_id}")
                return {
                    'statusCode': 500,
                    'body': json.dumps({'error': 'Error eliminando conexión'})
                }
                
        except Exception as scan_error:
            logger.error(f"Error buscando conexión para cleanup: {scan_error}")
            # Aún así returnamos 200 para evitar reintentos del API Gateway
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Error en cleanup pero conexión cerrada'})
            }
        
    except Exception as e:
        logger.error(f"Error en on_disconnect: {str(e)}")
        # Para WebSocket disconnect, siempre retornar 200 para evitar reintentos
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Desconexión procesada'})
        }