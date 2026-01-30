# ventas/listar_ventas.py
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

VENTAS_TABLE = os.environ.get('VENTAS_TABLE')

def handler(event, context):
    """
    GET /ventas - Listar ventas paginado
    
    Según documento SAAI (TRABAJADOR):
    Query Params: limit, next_token
    
    Response:
    {
        "success": true,
        "data": {
            "ventas": [
                {
                    "codigo_venta": "T002V015",
                    "total": 7.0,
                    "fecha": "2025-11-08T15:30:00-05:00"
                }
            ],
            "next_token": "..."
        }
    }
    """
    try:
        log_request(event)
        
        # Verificar rol TRABAJADOR
        tiene_permiso, error = verificar_rol_permitido(event, ['TRABAJADOR'])
        if not tiene_permiso:
            return error
        
        # Extraer tenant_id del JWT
        tenant_id = extract_tenant_from_jwt_claims(event)
        if not tenant_id:
            return error_response("Token inválido - no se encontró codigo_tienda", 401)
        
        # Extraer parámetros de paginación SAAI 1.6
        pagination = extract_pagination_params(event, default_limit=50, max_limit=100)
        
        # Parse query parameters
        query_params = event.get('queryStringParameters') or {}
        
        # Obtener todas las ventas activas con paginación
        ventas_response = query_by_tenant(
            VENTAS_TABLE,
            tenant_id,
            limit=pagination['limit'],
            last_evaluated_key=pagination.get('exclusive_start_key')
        )
        
        ventas = ventas_response.get('items', [])
        
        # Aplicar filtros opcionales
        fecha_inicio = query_params.get('fecha_inicio')
        fecha_fin = query_params.get('fecha_fin')
        
        filtered_ventas = []
        for venta_data in ventas:
            
            # Filtro por estado (solo ventas COMPLETADAS)
            if venta_data.get('estado') != 'COMPLETADA':
                continue
            
            # Filtro por rango de fechas
            if fecha_inicio and venta_data.get('fecha', '') < fecha_inicio:
                continue
            if fecha_fin and venta_data.get('fecha', '') > fecha_fin:
                continue
            
            # Convertir Decimal a float para response
            venta_response = {
                'codigo_venta': venta_data.get('codigo_venta'),
                'total': decimal_to_float(venta_data.get('total')),
                'fecha': venta_data.get('fecha')
            }
            
            filtered_ventas.append(venta_response)
        
        # Ordenar por fecha descendente (más recientes primero)
        filtered_ventas.sort(key=lambda x: x.get('fecha', ''), reverse=True)
        
        # Preparar response según SAAI oficial
        response_data = {'ventas': filtered_ventas}
        
        # Agregar next_token si hay más páginas
        if ventas_response.get('last_evaluated_key'):
            next_token = create_next_token(ventas_response['last_evaluated_key'])
            if next_token:
                response_data['next_token'] = next_token
        
        logger.info(f"Listadas {len(filtered_ventas)} ventas para tienda {tenant_id}")
        
        return success_response(data=response_data)
        
    except Exception as e:
        logger.error(f"Error listando ventas: {str(e)}")
        return error_response("Error interno del servidor", 500)