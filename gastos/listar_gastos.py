# gastos/listar_gastos.py
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

GASTOS_TABLE = os.environ.get('GASTOS_TABLE')

def handler(event, context):
    """
    GET /gastos - Listar gastos paginado
    
    Según documento SAAI (ADMIN):
    Query Params: limit, last_evaluated_key, categoria, fecha_inicio, fecha_fin
    
    Response:
    {
        "success": true,
        "data": [
            {
                "codigo_gasto": "G001",
                "descripcion": "Pago proveedor",
                "monto": 150.0,
                "categoria": "proveedores",
                "fecha": "2025-11-08"
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
        
        # Obtener todos los gastos activos
        gastos_response = query_by_tenant(
            GASTOS_TABLE,
            tenant_id,
            filter_expression="attribute_exists(#data) AND #data.estado = :estado",
            expression_attribute_names={"#data": "data"},
            expression_attribute_values={":estado": "ACTIVO"}
        )
        
        gastos = gastos_response.get('Items', [])
        
        # Aplicar filtros opcionales
        categoria = query_params.get('categoria')
        fecha_inicio = query_params.get('fecha_inicio')
        fecha_fin = query_params.get('fecha_fin')
        
        filtered_gastos = []
        for item in gastos:
            gasto_data = item.get('data', {})
            
            # Filtro por categoría
            if categoria and gasto_data.get('categoria', '').lower() != categoria.lower():
                continue
            
            # Filtro por rango de fechas
            if fecha_inicio and gasto_data.get('fecha', '') < fecha_inicio:
                continue
            if fecha_fin and gasto_data.get('fecha', '') > fecha_fin:
                continue
            
            # Convertir Decimal a float para response
            gasto_response = {
                'codigo_gasto': gasto_data.get('codigo_gasto'),
                'descripcion': gasto_data.get('descripcion'),
                'monto': decimal_to_float(gasto_data.get('monto')),
                'categoria': gasto_data.get('categoria'),
                'fecha': gasto_data.get('fecha')
            }
            
            filtered_gastos.append(gasto_response)
        
        # Ordenar por fecha descendente
        filtered_gastos.sort(key=lambda x: x.get('fecha', ''), reverse=True)
        
        # Aplicar paginación
        limit = int(query_params.get('limit', 50))
        last_key = query_params.get('last_evaluated_key')
        
        paginated_response = paginate_results(filtered_gastos, limit, last_key)
        
        logger.info(f"Listados {len(paginated_response['data'])} gastos para tienda {tenant_id}")
        
        return success_response(
            data=paginated_response['data'],
            pagination=paginated_response['pagination']
        )
        
    except Exception as e:
        logger.error(f"Error listando gastos: {str(e)}")
        return error_response("Error interno del servidor", 500)