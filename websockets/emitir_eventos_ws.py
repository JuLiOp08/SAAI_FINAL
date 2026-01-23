# websockets/emitir_eventos_ws.py
import os
import json
import logging
import boto3
from datetime import datetime
from boto3.dynamodb.conditions import Key
from utils import (
    log_request,
    obtener_fecha_hora_peru,
    delete_item_standard
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
WS_CONNECTIONS_TABLE = os.environ.get('WS_CONNECTIONS_TABLE')
# Variables de entorno para WebSocket
WS_API_ENDPOINT = os.environ.get('WS_API_ENDPOINT')
REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')

def handler(event, context):
    """
    Emitir Eventos WebSocket - Broadcasting en tiempo real
    
    Según documento SAAI:
    - Recibe evento interno con tenant_id y tipo
    - Consulta conexiones activas del tenant_id en t_ws_connections
    - Envía payload a cada connectionId usando API Gateway Management API
    - Elimina conexiones inválidas automáticamente
    
    Input esperado:
    {
        "tenant_id": "TIENDA001",
        "event_type": "venta_registrada|analitica_actualizada|prediccion_generada",
        "payload": { ... datos específicos del evento ... },
        "exclude_connection_id": "opcional_para_excluir_emisor"
    }
    
    Tablas: t_ws_connections (QUERY por tenant_id; DELETE de inválidas)
    Servicios: DynamoDB, API Gateway Management API (postToConnection)
    """
    try:
        log_request(event)
        
        # Validar que venga el tenant_id y event_type
        if isinstance(event, str):
            event_data = json.loads(event)
        else:
            event_data = event
        
        tenant_id = event_data.get('tenant_id')
        event_type = event_data.get('event_type')
        payload = event_data.get('payload', {})
        exclude_connection_id = event_data.get('exclude_connection_id')
        
        if not tenant_id or not event_type:
            error_msg = "tenant_id y event_type son requeridos"
            logger.error(error_msg)
            return {
                'statusCode': 400,
                'body': json.dumps({'error': error_msg})
            }
        
        # Validar tipos de evento permitidos
        allowed_events = ['venta_registrada', 'analitica_actualizada', 'prediccion_generada']
        if event_type not in allowed_events:
            error_msg = f"Tipo de evento no válido: {event_type}. Permitidos: {allowed_events}"
            logger.error(error_msg)
            return {
                'statusCode': 400,
                'body': json.dumps({'error': error_msg})
            }
        
        # Conectar a DynamoDB para obtener conexiones activas
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        table = dynamodb.Table(WS_CONNECTIONS_TABLE)
        
        # Query conexiones por tenant_id
        try:
            response = table.query(
                KeyConditionExpression=Key('tenant_id').eq(tenant_id)
            )
            connections = response.get('Items', [])
            
        except Exception as query_error:
            logger.error(f"Error consultando conexiones para {tenant_id}: {query_error}")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Error consultando conexiones activas'})
            }
        
        if not connections:
            logger.info(f"No hay conexiones activas para tenant {tenant_id}")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Evento procesado - no hay conexiones activas',
                    'tenant_id': tenant_id,
                    'event_type': event_type,
                    'connections_sent': 0
                })
            }
        
        # Preparar cliente para envío de mensajes WebSocket
        if not WS_API_ENDPOINT:
            logger.error("WS_API_ENDPOINT no configurado")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'WebSocket endpoint no configurado'})
            }
        
        apigateway_management = boto3.client(
            'apigatewaymanagementapi',
            endpoint_url=WS_API_ENDPOINT,
            region_name=REGION
        )
        
        # Preparar mensaje a enviar
        timestamp_lima = obtener_fecha_hora_peru()
        ws_message = {
            'event_type': event_type,
            'tenant_id': tenant_id,
            'timestamp': timestamp_lima,
            'data': payload
        }
        message_data = json.dumps(ws_message).encode('utf-8')
        
        # Enviar a todas las conexiones activas
        connections_sent = 0
        connections_cleaned = 0
        
        for connection in connections:
            connection_id = connection.get('entity_id')
            
            # Excluir conexión específica si se solicita (ej: quien generó el evento)
            if exclude_connection_id and connection_id == exclude_connection_id:
                continue
            
            try:
                # Enviar mensaje a la conexión
                apigateway_management.post_to_connection(
                    ConnectionId=connection_id,
                    Data=message_data
                )
                connections_sent += 1
                logger.info(f"Mensaje enviado a conexión {connection_id}")
                
            except Exception as send_error:
                # Si la conexión está muerta, limpiarla
                error_code = getattr(send_error, 'response', {}).get('Error', {}).get('Code')
                
                if error_code in ['GoneException', 'ForbiddenException']:
                    logger.warning(f"Conexión inválida, eliminando: {connection_id}")
                    
                    # Eliminar conexión inválida (hard delete - conexiones WS no usan soft delete)
                    delete_success = delete_item_standard(
                        WS_CONNECTIONS_TABLE,
                        tenant_id,
                        connection_id,
                        soft_delete=False  # Hard delete para conexiones WebSocket
                    )
                    
                    if delete_success:
                        connections_cleaned += 1
                        logger.info(f"Conexión inválida eliminada: {connection_id}")
                else:
                    logger.error(f"Error enviando a {connection_id}: {send_error}")
        
        logger.info(f"Evento {event_type} enviado a {connections_sent} conexiones de {tenant_id}")
        if connections_cleaned > 0:
            logger.info(f"Se limpiaron {connections_cleaned} conexiones inválidas")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Evento WebSocket enviado exitosamente',
                'tenant_id': tenant_id,
                'event_type': event_type,
                'connections_sent': connections_sent,
                'connections_cleaned': connections_cleaned,
                'timestamp': timestamp_lima
            })
        }
        
    except Exception as e:
        logger.error(f"Error en emitir_eventos_ws: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Error interno emitiendo eventos',
                'details': str(e)
            })
        }