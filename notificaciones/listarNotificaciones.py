# notifications/listar_notificaciones.py
import os
import logging
from utils import (
    success_response,
    error_response,
    log_request,
    extract_tenant_from_jwt_claims,
    query_by_tenant,
    extract_pagination_params,
    create_next_token
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
        
        # Extraer parámetros de paginación según SAAI oficial 1.6
        pagination = extract_pagination_params(event, default_limit=50)
        
        # Parse query parameters para filtros opcionales
        query_params = event.get('queryStringParameters') or {}
        severidad = query_params.get('severidad')  # INFO, CRITICAL
        tipo = query_params.get('tipo')  # sinStock, bajoStock, etc.
        fecha_inicio = query_params.get('fecha_inicio')  # YYYY-MM-DD
        fecha_fin = query_params.get('fecha_fin')  # YYYY-MM-DD
        
        # Usar query_by_tenant optimizada que filtra INACTIVOS automáticamente
        result = query_by_tenant(
            table_name=NOTIFICACIONES_TABLE,
            tenant_id=tenant_id,
            limit=pagination['limit'],
            last_evaluated_key=pagination['exclusive_start_key']
        )
        
        notificaciones = result.get('items', [])
        
        # Aplicar filtros opcionales en memoria
        filtered_notificaciones = []
        for notificacion_data in notificaciones:
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
            
            # Preparar respuesta según formato SAAI oficial
            notificacion_response = {
                'codigo_notificacion': notificacion_data.get('codigo_notificacion'),
                'tipo': notificacion_data.get('tipo'),
                'titulo': notificacion_data.get('titulo'),
                'mensaje': notificacion_data.get('mensaje'),
                'fecha': notificacion_data.get('fecha'),
                'severidad': notificacion_data.get('severidad'),
                'origen': notificacion_data.get('origen')
            }
            
            # Solo incluir detalle si existe
            if notificacion_data.get('detalle'):
                notificacion_response['detalle'] = notificacion_data['detalle']
            
            filtered_notificaciones.append(notificacion_response)
        
        # Ordenar por fecha descendente (más recientes primero)
        filtered_notificaciones.sort(
            key=lambda x: x.get('fecha', ''), 
            reverse=True
        )
        
        # Preparar respuesta según formato SAAI oficial
        response_data = {
            "notificaciones": filtered_notificaciones
        }
        
        # Agregar next_token según SAAI oficial 1.6 si hay más páginas
        last_evaluated_key = result.get('last_evaluated_key')
        if last_evaluated_key:
            next_token = create_next_token(last_evaluated_key)
            if next_token:
                response_data["next_token"] = next_token
        
        logger.info(f"Listadas {len(filtered_notificaciones)} notificaciones para tienda {tenant_id}")
        
        return success_response(data=response_data)
        
    except Exception as e:
        logger.error(f"Error listando notificaciones: {str(e)}")
        return error_response("Error interno del servidor", 500)