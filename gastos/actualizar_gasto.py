# gastos/actualizar_gasto.py
import os
import logging
from decimal import Decimal
from utils import (
    success_response,
    error_response,
    validation_error_response,
    parse_request_body,
    log_request,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims,
    get_item_standard,
    update_item_standard,
    obtener_fecha_hora_peru
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

GASTOS_TABLE = os.environ.get('GASTOS_TABLE')

def handler(event, context):
    """
    PUT /gastos/{codigo_gasto} - Actualizar gasto
    
    Según documento SAAI (ADMIN):
    Request:
    {
        "body": {
            "descripcion": "Pago proveedor actualizado",
            "monto": 200.0,
            "categoria": "proveedores",
            "fecha": "2025-11-09"
        }
    }
    
    Response:
    {
        "success": true,
        "message": "Gasto actualizado",
        "data": {
            "codigo_gasto": "T002G001"
        }
    }
    """
    try:
        log_request(event)
        
        # Verificar rol ADMIN
        tiene_permiso, error = verificar_rol_permitido(event, ['ADMIN'])
        if not tiene_permiso:
            return error
        
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
        
        # Verificar que el gasto existe
        existing_gasto = get_item_standard(GASTOS_TABLE, tenant_id, codigo_gasto)
        if not existing_gasto or existing_gasto.get('estado') != 'ACTIVO':
            return error_response("Gasto no encontrado", 404)
        
        # Parse request body
        body = parse_request_body(event)
        if not body:
            return validation_error_response("Request body requerido")
        
        # Validar campos (todos opcionales para actualización)
        updates = {}
        
        if 'descripcion' in body:
            if not body['descripcion']:
                return validation_error_response("Descripcion no puede estar vacía")
            updates['descripcion'] = str(body['descripcion']).strip()
        
        if 'monto' in body:
            try:
                monto = float(body['monto'])
                if monto <= 0:
                    return validation_error_response("El monto debe ser mayor a 0")
                updates['monto'] = Decimal(str(monto))
            except (ValueError, TypeError):
                return validation_error_response("Monto debe ser un número válido")
        
        if 'categoria' in body:
            if not body['categoria']:
                return validation_error_response("Categoria no puede estar vacía")
            updates['categoria'] = str(body['categoria']).strip()
        
        if 'fecha' in body:
            if not body['fecha']:
                return validation_error_response("Fecha no puede estar vacía")
            updates['fecha'] = str(body['fecha']).strip()
        
        # Agregar metadatos de auditoría
        if codigo_usuario:
            updates['updated_by'] = codigo_usuario
        
        # Actualizar usando utils
        success = update_item_standard(
            table_name=GASTOS_TABLE,
            tenant_id=tenant_id,
            entity_id=codigo_gasto,
            data_updates=updates
        )
        
        if not success:
            return error_response("Error actualizando gasto", 500)
        
        logger.info(f"Gasto actualizado: {codigo_gasto} en tienda {tenant_id}")
        
        return success_response(
            mensaje="Gasto actualizado",
            data={"codigo_gasto": codigo_gasto}
        )
        
    except Exception as e:
        logger.error(f"Error actualizando gasto: {str(e)}")
        return error_response("Error interno del servidor", 500)