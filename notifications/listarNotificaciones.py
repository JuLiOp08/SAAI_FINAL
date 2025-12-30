# notifications/listar_notificaciones.py
import os
import logging
from utils import (
    success_response,
    error_response,
    log_request,
    extract_tenant_from_jwt_claims,
    query_by_tenant,
    paginate_results
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

NOTIFICACIONES_TABLE = os.environ.get('NOTIFICACIONES_TABLE')

def handler(event, context):
    """
    GET /notificaciones - Listar notificaciones paginado
    
    Según documento SAAI (TRABAJADOR/ADMIN):
    Query Params: limit, last_evaluated_key, severidad, tipo, fecha_inicio, fecha_fin
    
    Response:
    {
        "success": true,
        "data": {
            "notificaciones": [
                {
                    "codigo_notificacion": "N001",
                    "tipo": "bajoStock",
                    "titulo": "Stock bajo",
                    "mensaje": "Coca Cola tiene solo 3 unidades",
                    "fecha": "2025-11-08T15:31:00-05:00",
                    "severidad": "INFO",
                    "origen": "registrarVenta"
                }
            ],
            "next_token": null
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
        
        # Obtener todas las notificaciones activas
        notificaciones_response = query_by_tenant(
            NOTIFICACIONES_TABLE,
            tenant_id,
            filter_expression="attribute_exists(#data) AND #data.estado = :estado",
            expression_attribute_names={"#data": "data"},
            expression_attribute_values={":estado": "ACTIVO"}
        )
        
        notificaciones = notificaciones_response.get('Items', [])
        
        # Aplicar filtros opcionales
        severidad = query_params.get('severidad')
        tipo = query_params.get('tipo')
        fecha_inicio = query_params.get('fecha_inicio')
        fecha_fin = query_params.get('fecha_fin')
        
        filtered_notificaciones = []
        for item in notificaciones:
            notificacion_data = item.get('data', {})
            
            # Filtro por severidad
            if severidad and notificacion_data.get('severidad', '').upper() != severidad.upper():
                continue
            
            # Filtro por tipo
            if tipo and notificacion_data.get('tipo', '') != tipo:
                continue
            
            # Filtro por rango de fechas (comparar solo fecha YYYY-MM-DD)
            fecha_notif = notificacion_data.get('fecha', '')[:10]  # Solo fecha
            if fecha_inicio and fecha_notif < fecha_inicio:
                continue
            if fecha_fin and fecha_notif > fecha_fin:
                continue
            
            # Preparar respuesta de notificación
            notificacion_response = {
                'codigo_notificacion': notificacion_data.get('codigo_notificacion'),
                'tipo': notificacion_data.get('tipo'),
                'titulo': notificacion_data.get('titulo'),
                'mensaje': notificacion_data.get('mensaje'),
                'fecha': notificacion_data.get('fecha'),
                'severidad': notificacion_data.get('severidad'),
                'origen': notificacion_data.get('origen')
            }
            
            filtered_notificaciones.append(notificacion_response)
        
        # Ordenar por fecha descendente (más recientes primero)
        filtered_notificaciones.sort(
            key=lambda x: x.get('fecha', ''), 
            reverse=True
        )
        
        # Aplicar paginación
        limit = int(query_params.get('limit', 50))
        last_key = query_params.get('last_evaluated_key')
        
        paginated_response = paginate_results(filtered_notificaciones, limit, last_key)
        
        logger.info(f"Listadas {len(paginated_response['data'])} notificaciones para tienda {tenant_id}")
        
        return success_response(
            data={
                "notificaciones": paginated_response['data'],
                "next_token": paginated_response['pagination']['last_evaluated_key']
            }
        )
        
    except Exception as e:
        logger.error(f"Error listando notificaciones: {str(e)}")
        return error_response("Error interno del servidor", 500)