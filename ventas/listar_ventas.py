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
    paginate_results
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
        
        # Parse query parameters
        query_params = event.get('queryStringParameters') or {}
        
        # Obtener todas las ventas activas
        ventas_response = query_by_tenant(
            VENTAS_TABLE,
            tenant_id,
            filter_expression="attribute_exists(#data) AND #data.estado = :estado",
            expression_attribute_names={"#data": "data"},
            expression_attribute_values={":estado": "COMPLETADA"}
        )
        
        ventas = ventas_response.get('Items', [])
        
        # Aplicar filtros opcionales
        fecha_inicio = query_params.get('fecha_inicio')
        fecha_fin = query_params.get('fecha_fin')
        cliente_filter = query_params.get('cliente')
        
        filtered_ventas = []
        for item in ventas:
            venta_data = item.get('data', {})
            
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
        
        # Aplicar paginación
        limit = int(query_params.get('limit', 50))
        last_key = query_params.get('last_evaluated_key')
        
        paginated_response = paginate_results(filtered_ventas, limit, last_key)
        
        logger.info(f"Listadas {len(paginated_response['data'])} ventas para tienda {tenant_id}")
        
        return success_response(
            data=paginated_response['data'],
            pagination=paginated_response['pagination']
        )
        
    except Exception as e:
        logger.error(f"Error listando ventas: {str(e)}")
        return error_response("Error interno del servidor", 500)