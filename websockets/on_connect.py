# websockets/on_connect.py
import os
import json
import logging
from utils import (
    success_response,
    error_response,
    log_request,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims,
    put_item_standard,
    obtener_fecha_hora_peru,
    verificar_token_jwt
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
WS_CONNECTIONS_TABLE = os.environ.get('WS_CONNECTIONS_TABLE')

def handler(event, context):
    """
    WebSocket $connect - Registrar nueva conexión
    
    Según documento SAAI:
    - Se ejecuta cuando el cliente abre una conexión WebSocket
    - Registra la conexión en t_ws_connections asociándola al tenant_id y usuario
    - Permite emitir eventos únicamente a conexiones de esa tienda
    
    Tablas: t_ws_connections (INSERT/PUT)
    Servicios: API Gateway WebSocket (route: $connect)
    
    Estructura data:
    {
        "connection_id": "...",
        "codigo_usuario": "U001", 
        "role": "admin|worker",
        "connected_at": "...",
        "estado": "ACTIVO",
        "ttl": 1730000000
    }
    """
    try:
        log_request(event)
        
        # Obtener connection_id del contexto WebSocket
        connection_id = event.get('requestContext', {}).get('connectionId')
        if not connection_id:
            logger.error("Connection ID no encontrado en el evento WebSocket")
            return error_response("Connection ID requerido", 400)
        
        # Extraer datos del JWT desde query parameters o headers
        # En WebSocket, el token puede venir en queryStringParameters
        query_params = event.get('queryStringParameters') or {}
        headers = event.get('headers') or {}
        
        # Buscar token en query params o headers
        token = query_params.get('token') or headers.get('authorization') or headers.get('Authorization')
        
        if not token:
            logger.error("Token JWT no encontrado en la conexión WebSocket")
            return {
                'statusCode': 401,
                'body': json.dumps({'error': 'Token requerido'})
            }
        
        # Simular event structure para extract functions
        jwt_event = {
            'requestContext': {
                'authorizer': {
                    'tenant_id': None,
                    'codigo_usuario': None,
                    'rol': None
                }
            }
        }
        
        # Para WebSocket, necesitamos decodificar el JWT manualmente
        payload = verificar_token_jwt(token)
        if not payload:
            logger.error("Token JWT inválido en conexión WebSocket")
            return {
                'statusCode': 401,
                'body': json.dumps({'error': 'Token inválido'})
            }
        
        # Extraer datos del payload JWT
        tenant_id = payload.get('tenant_id')
        codigo_usuario = payload.get('codigo_usuario')
        rol = payload.get('rol')
        
        if not tenant_id or not codigo_usuario or not rol:
            logger.error(f"Claims JWT incompletos: tenant={tenant_id}, user={codigo_usuario}, rol={rol}")
            return {
                'statusCode': 401,
                'body': json.dumps({'error': 'Claims JWT incompletos'})
            }
        
        # Calcular TTL para 24 horas (mismo que JWT)
        import time
        ttl_seconds = int(time.time()) + (24 * 60 * 60)
        
        # Datos de la conexión WebSocket
        connection_data = {
            'connection_id': connection_id,
            'codigo_usuario': codigo_usuario,
            'rol': rol,
            'connected_at': obtener_fecha_hora_peru(),
            'estado': 'ACTIVO',
            'ttl': ttl_seconds
        }
        
        # Guardar conexión en DynamoDB
        success = put_item_standard(
            WS_CONNECTIONS_TABLE,
            tenant_id,
            connection_id,
            connection_data
        )
        
        if not success:
            logger.error(f"Error guardando conexión WebSocket: {connection_id}")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Error interno guardando conexión'})
            }
        
        logger.info(f"Conexión WebSocket registrada: {connection_id} para tienda {tenant_id}, usuario {codigo_usuario}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Conexión WebSocket establecida',
                'connection_id': connection_id,
                'tenant_id': tenant_id
            })
        }
        
    except Exception as e:
        logger.error(f"Error en on_connect: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Error interno del servidor'})
        }