# ventas/listar_ventas.py
import os
import logging
from decimal import Decimal
from utils import (
    success_response,
    error_response,
    log_request,
    extract_tenant_from_jwt_claims,
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
    Query Params: limit, last_evaluated_key, fecha_inicio, fecha_fin, cliente
    
    Response:
    {
        "success": true,
        "data": [
            {
                "codigo_venta": "V001",
                "cliente": "Juan Pérez",
                "total": 148.09,
                "fecha": "2025-11-08",
                "metodo_pago": "efectivo"
            }
        ],
        "pagination": {
            "total": 1,
            "limit": 50,
            "last_evaluated_key": null
        }
    }
    """
    try:
        log_request(event)
        
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
        cliente_filter = query_params.get('cliente')
        
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
            
            # Filtro por cliente
            if cliente_filter and cliente_filter.lower() not in venta_data.get('cliente', '').lower():
                continue
            
            # Convertir Decimal a float para response
            venta_response = {
                'codigo_venta': venta_data.get('codigo_venta'),
                'cliente': venta_data.get('cliente'),
                'total': decimal_to_float(venta_data.get('total')),
                'fecha': venta_data.get('fecha'),
                'metodo_pago': venta_data.get('metodo_pago')
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