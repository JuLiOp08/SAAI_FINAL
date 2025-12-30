# gastos/eliminar_gasto.py
import os
import logging
from utils import (
    success_response,
    error_response,
    validation_error_response,
    log_request,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims,
    get_item_standard,
    put_item_standard,
    obtener_fecha_hora_peru
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

GASTOS_TABLE = os.environ.get('GASTOS_TABLE')

def handler(event, context):
    """
    DELETE /gastos/{codigo_gasto} - Eliminar gasto (soft delete)
    
    Según documento SAAI (ADMIN):
    Response:
    {
        "success": true,
        "message": "Gasto eliminado"
    }
    """
    try:
        log_request(event)
        
        # Extraer tenant_id del JWT
        tenant_id = extract_tenant_from_jwt_claims(event)
        if not tenant_id:
            return error_response("Token inválido - no se encontró codigo_tienda", 401)
        
        # Extraer usuario para auditoría
        user_data = extract_user_from_jwt_claims(event)
        codigo_usuario = user_data.get('codigo_usuario') if user_data else None
        
        # Extraer codigo_gasto del path
        path_params = event.get('pathParameters') or {}
        codigo_gasto = path_params.get('codigo_gasto')
        
        if not codigo_gasto:
            return validation_error_response("codigo_gasto es requerido en el path")
        
        # Verificar que el gasto existe y está activo
        existing_gasto = get_item_standard(GASTOS_TABLE, tenant_id, codigo_gasto)
        if not existing_gasto:
            return error_response("Gasto no encontrado", 404)
        
        if existing_gasto.get('estado') == 'ELIMINADO':
            return error_response("Gasto ya eliminado", 400)
        
        # Soft delete - marcar como eliminado
        updated_data = existing_gasto.copy()
        updated_data['estado'] = 'ELIMINADO'
        updated_data['deleted_at'] = obtener_fecha_hora_peru()
        updated_data['updated_at'] = obtener_fecha_hora_peru()
        
        if codigo_usuario:
            updated_data['deleted_by'] = codigo_usuario
            updated_data['updated_by'] = codigo_usuario
        
        # Guardar cambios
        put_item_standard(
            GASTOS_TABLE,
            tenant_id=tenant_id,
            entity_id=codigo_gasto,
            data=updated_data
        )
        
        logger.info(f"Gasto eliminado: {codigo_gasto} en tienda {tenant_id}")
        
        return success_response(message="Gasto eliminado")
        
    except Exception as e:
        logger.error(f"Error eliminando gasto: {str(e)}")
        return error_response("Error interno del servidor", 500)