# tiendas/actualizar_tienda.py
import os
import logging
from utils import (
    success_response,
    error_response,
    validation_error_response,
    parse_request_body,
    log_request,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims,
    get_item_standard,
    put_item_standard,
    obtener_fecha_hora_peru
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
TIENDAS_TABLE = os.environ.get('TIENDAS_TABLE')

def handler(event, context):
    """
    PUT /tiendas/{codigo_tienda} - Actualizar tienda
    
    Según documento SAAI (SAAI):
    Request:
    {
        "body": {
            "nombre_tienda": "Bodega San Juan SAC",
            "estado": "SUSPENDIDA"
        }
    }
    
    Response:
    {
        "success": true,
        "message": "Tienda actualizada",
        "data": {
            "codigo_tienda": "T002",
            "estado": "SUSPENDIDA"
        }
    }
    """
    try:
        log_request(event)
        
        # Obtener código de tienda del path
        codigo_tienda = event.get('pathParameters', {}).get('codigo_tienda')
        if not codigo_tienda:
            return validation_error_response("Código de tienda requerido en el path")
        
        # Parse request body
        body = parse_request_body(event)
        if not body:
            return validation_error_response("Request body requerido")
        
        # Verificar que la tienda existe
        item = get_item_standard(TIENDAS_TABLE, "SAAI", codigo_tienda)
        if not item:
            return error_response("Tienda no encontrada", 404)
        
        tienda_data = item['data']
        
        # Actualizar campos permitidos
        fecha_actual = obtener_fecha_hora_peru()
        
        if 'nombre_tienda' in body:
            tienda_data['nombre_tienda'] = str(body['nombre_tienda']).strip()
        
        if 'estado' in body:
            estado = str(body['estado']).strip().upper()
            if estado not in ['ACTIVA', 'SUSPENDIDA', 'ELIMINADA']:
                return validation_error_response("Estado debe ser ACTIVA, SUSPENDIDA o ELIMINADA")
            tienda_data['estado'] = estado
        
        if 'email_tienda' in body:
            tienda_data['email_tienda'] = str(body['email_tienda']).strip().lower()
        
        if 'telefono' in body:
            tienda_data['telefono'] = str(body['telefono']).strip()
        
        # Actualizar metadatos
        tienda_data['updated_at'] = fecha_actual
        
        # Guardar en DynamoDB
        put_item_standard(
            TIENDAS_TABLE,
            tenant_id="SAAI",
            entity_id=codigo_tienda,
            data=tienda_data
        )
        
        logger.info(f"Tienda actualizada: {codigo_tienda}")
        
        return success_response(
            message="Tienda actualizada",
            data={
                "codigo_tienda": codigo_tienda,
                "estado": tienda_data.get('estado')
            }
        )
        
    except Exception as e:
        logger.error(f"Error actualizando tienda: {str(e)}")
        return error_response("Error interno del servidor", 500)