# notifications/guardar_notificacion.py
import os
import json
import logging
from decimal import Decimal
from utils import (
    success_response,
    error_response,
    log_request,
    put_item_standard,
    generar_codigo_notificacion,
    obtener_fecha_hora_peru
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
NOTIFICACIONES_TABLE = os.environ.get('NOTIFICACIONES_TABLE')

def handler(event, context):
    """
    SNS → Lambda: Guardar notificación en t_notificaciones
    
    Según documento SAAI:
    - Consumidor de AlertasSAAI
    - Guarda TODAS las alertas (INFO + CRITICAL)
    - MessageAttributes obligatorios: tenant_id, tipo, severidad, origen, ts
    - Genera codigo_notificacion automático por tienda
    
    Event estructura:
    {
        "Records": [
            {
                "EventSource": "aws:sns",
                "Sns": {
                    "Message": "{\"titulo\": \"...\", \"mensaje\": \"...\", \"detalle\": {...}}",
                    "MessageAttributes": {
                        "tenant_id": {"Type": "String", "Value": "T002"},
                        "tipo": {"Type": "String", "Value": "sinStock"},
                        "severidad": {"Type": "String", "Value": "CRITICAL"},
                        "origen": {"Type": "String", "Value": "registrarVenta"},
                        "ts": {"Type": "String", "Value": "2025-11-08T15:30:00-05:00"}
                    }
                }
            }
        ]
    }
    """
    try:
        log_request(event)
        
        # Procesar todos los records SNS
        for record in event.get('Records', []):
            if record.get('EventSource') != 'aws:sns':
                continue
                
            sns_data = record.get('Sns', {})
            message_attrs = sns_data.get('MessageAttributes', {})
            message_body = sns_data.get('Message', '{}')
            
            # Extraer MessageAttributes obligatorios
            tenant_id = message_attrs.get('tenant_id', {}).get('Value')
            tipo = message_attrs.get('tipo', {}).get('Value')
            severidad = message_attrs.get('severidad', {}).get('Value')
            origen = message_attrs.get('origen', {}).get('Value')
            ts = message_attrs.get('ts', {}).get('Value')
            
            if not all([tenant_id, tipo, severidad, origen, ts]):
                logger.error(f"MessageAttributes incompletos: tenant_id={tenant_id}, tipo={tipo}, severidad={severidad}, origen={origen}, ts={ts}")
                continue
            
            # Parse del mensaje
            try:
                message_data = json.loads(message_body)
            except json.JSONDecodeError:
                logger.error(f"Error parseando mensaje SNS: {message_body}")
                continue
            
            titulo = message_data.get('titulo', 'Sin título')
            mensaje = message_data.get('mensaje', 'Sin mensaje')
            detalle = message_data.get('detalle', {})
            
            # Generar código de notificación usando función centralizada
            codigo_notificacion = generar_codigo_notificacion(tenant_id)
            if not codigo_notificacion:
                logger.error(f"Error generando código de notificación para tenant {tenant_id}")
                continue
            
            # Crear entidad notificación
            fecha_actual = obtener_fecha_hora_peru()
            
            notificacion_data = {
                'codigo_notificacion': codigo_notificacion,
                'tipo': tipo,
                'titulo': titulo,
                'mensaje': mensaje,
                'origen': origen,
                'severidad': severidad,
                'fecha': ts,  # Usar timestamp del evento original
                'detalle': detalle,
                'estado': 'ACTIVO',
                'created_at': fecha_actual,
                'updated_at': fecha_actual
            }
            
            # Guardar en DynamoDB
            put_item_standard(
                NOTIFICACIONES_TABLE,
                tenant_id=tenant_id,
                entity_id=codigo_notificacion,
                data=notificacion_data
            )
            
            logger.info(f"Notificación guardada: {codigo_notificacion} en tienda {tenant_id}, tipo: {tipo}, severidad: {severidad}")
        
        return success_response(message="Notificaciones procesadas")
        
    except Exception as e:
        logger.error(f"Error guardando notificaciones: {str(e)}")
        return error_response("Error interno del servidor", 500)