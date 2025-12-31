# tiendas/eliminar_tienda.py
import os
import logging
from utils import (
    success_response,
    error_response,
    validation_error_response,
    parse_request_body,
    get_path_parameter,
    log_request,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims,
    get_item_standard,
    put_item_standard,
    obtener_fecha_hora_peru
)
from constants import ESTADO_TIENDA_ELIMINADA

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
TIENDAS_TABLE = os.environ.get('TIENDAS_TABLE')

def handler(event, context):
    """
    DELETE /tiendas/{codigo_tienda} - Eliminar tienda (soft delete)
    
    Según documento SAAI (SAAI):
    Request:
    {
        "body": {
            "motivo": "Cierre definitivo"
        }
    }
    
    Response:
    {
        "success": true,
        "message": "Tienda eliminada",
        "data": {
            "codigo_tienda": "T002"
        }
    }
    """
    try:
        log_request(event)
        
        # Validar que el usuario sea SAAI
        user_info = extract_user_from_jwt_claims(event)
        if not user_info or user_info.get('rol') != 'saai':
            return error_response("Solo usuarios SAAI pueden eliminar tiendas", 403)
        
        # Obtener código de tienda del path
        codigo_tienda = get_path_parameter(event, 'codigo_tienda')
        if not codigo_tienda:
            return validation_error_response("Código de tienda requerido en el path")
        
        # Parse request body para obtener motivo
        body = parse_request_body(event)
        motivo = body.get('motivo', 'Eliminada por administrador SAAI') if body else 'Eliminada por administrador SAAI'
        
        # Verificar que la tienda existe
        tienda_data = get_item_standard(TIENDAS_TABLE, "SAAI", codigo_tienda)
        if not tienda_data:
            return error_response("Tienda no encontrada", 404)
        
        # Verificar que la tienda no esté ya eliminada
        if tienda_data.get('estado') == ESTADO_TIENDA_ELIMINADA:
            return error_response("La tienda ya está eliminada", 400)
        
        # Realizar eliminación lógica (soft delete)
        fecha_actual = obtener_fecha_hora_peru()
        user_info = extract_user_from_jwt_claims(event)
        
        tienda_data['estado'] = ESTADO_TIENDA_ELIMINADA
        tienda_data['motivo_baja'] = str(motivo).strip()
        tienda_data['fecha_baja'] = fecha_actual
        tienda_data['baja_por'] = user_info.get('codigo_usuario', 'SAAI_UNKNOWN')
        tienda_data['updated_at'] = fecha_actual
        
        # Guardar en DynamoDB
        put_item_standard(
            TIENDAS_TABLE,
            tenant_id="SAAI",
            entity_id=codigo_tienda,
            data=tienda_data
        )
        
        logger.info(f"Tienda eliminada (soft delete): {codigo_tienda}")
        
        return success_response(
            message="Tienda eliminada",
            data={"codigo_tienda": codigo_tienda}
        )
        
    except Exception as e:
        logger.error(f"Error eliminando tienda: {str(e)}")
        return error_response("Error interno del servidor", 500)