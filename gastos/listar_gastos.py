# gastos/listar_gastos.py
import os
import logging
from decimal import Decimal
from utils import (
    success_response,
    error_response,
    log_request,
    extract_tenant_from_jwt_claims,
    verificar_rol_permitido,
    query_by_tenant,
    decimal_to_float,
    extract_pagination_params,
    create_next_token
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

GASTOS_TABLE = os.environ.get('GASTOS_TABLE')

def handler(event, context):
    """
    GET /gastos - Listar gastos
    
    Según documento SAAI (ADMIN):
    Response:
    {
        "success": true,
        "data": {
            "gastos": [
                {
                    "codigo_gasto": "T002G001",
                    "descripcion": "Pago proveedor",
                    "monto": 150.0,
                    "fecha": "2025-11-08"
                }
            ]
        },
        "next_token": "..."
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
        
        # Extraer parámetros de paginación según documentación SAAI
        pagination = extract_pagination_params(event, default_limit=50)
        
        # Consultar gastos activos usando utils (filtra INACTIVOS automáticamente)
        gastos_response = query_by_tenant(
            table_name=GASTOS_TABLE,
            tenant_id=tenant_id,
            limit=pagination['limit'],
            last_evaluated_key=pagination.get('exclusive_start_key')
        )
        
        gastos = gastos_response.get('items', [])
        
        # Convertir a formato de respuesta SAAI oficial
        gastos_formateados = []
        for gasto_data in gastos:
            # Remover keys internas agregadas por query_by_tenant
            gasto_data.pop('_tenant_id', None)
            gasto_data.pop('_entity_id', None)
            
            gasto_response = {
                'codigo_gasto': gasto_data.get('codigo_gasto'),
                'descripcion': gasto_data.get('descripcion'),
                'monto': decimal_to_float(gasto_data.get('monto')),
                'categoria': gasto_data.get('categoria'),
                'fecha': gasto_data.get('fecha')
            }
            
            gastos_formateados.append(gasto_response)
        
        # Preparar respuesta según formato oficial SAAI
        response_data = {
            "gastos": gastos_formateados
        }
        
        # Agregar next_token si hay más páginas
        last_evaluated_key = gastos_response.get('last_evaluated_key')
        if last_evaluated_key:
            next_token = create_next_token(last_evaluated_key)
            if next_token:
                response_data['next_token'] = next_token
        
        logger.info(f"Listados {len(gastos_formateados)} gastos para tienda {tenant_id}")
        
        return success_response(data=response_data)
        
    except Exception as e:
        logger.error(f"Error listando gastos: {str(e)}")
        return error_response("Error interno del servidor", 500)