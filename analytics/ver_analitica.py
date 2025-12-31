# analytics/ver_analitica.py
import os
import logging
from datetime import datetime, timedelta, timezone
from utils import (
    success_response,
    error_response,
    extract_tenant_from_jwt_claims,
    obtener_fecha_hora_peru,
    get_item_standard,
    query_by_tenant
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    """
    GET /analitica
    
    Devuelve métricas analíticas previamente calculadas.
    NO recalcula, solo consulta t_analitica.
    
    Este endpoint es la ÚNICA FUENTE DE VERDAD para datos analíticos.
    El frontend debe hacer refetch a este endpoint cuando reciba
    notificaciones WebSocket de tipo 'analitica_actualizada'.
    
    Query params: ?periodo=7 (días)
    
    Response: {
      "success": true,
      "data": {
        "periodo": {...},
        "ventas": {...},
        "gastos": {...},
        "inventario": {...},
        "usuarios": {...},
        "productos_top": [...],
        "ventas_diarias": [...],
        "alertas_detectadas": [...]
      }
    }
    """
    try:
        # JWT validation + tenant
        tenant_id = extract_tenant_from_jwt_claims(event)
        if not tenant_id:
            return error_response("Token inválido - tenant_id faltante", 401)
        
        # Query params
        query_params = event.get('queryStringParameters') or {}
        periodo_dias = int(query_params.get('periodo', 7))
        
        # Calcular rango de fechas
        lima_now = datetime.now(timezone.utc)  # Usar UTC para cálculos
        fecha_fin = lima_now
        fecha_inicio = lima_now - timedelta(days=periodo_dias - 1)
        
        entity_id = f"{fecha_inicio.strftime('%Y-%m-%d')}_{fecha_fin.strftime('%Y-%m-%d')}"
        
        logger.info(f"📊 Consultando analítica: {tenant_id} - {entity_id}")
        
        # =================================================================
        # CONSULTAR t_analitica usando utils
        # =================================================================
        
        try:
            analitica_data = get_item_standard(
                table_name=os.environ['ANALITICA_TABLE'],
                tenant_id=tenant_id,
                entity_id=entity_id
            )
            
            if analitica_data:
                logger.info(f"✅ Analítica encontrada: {entity_id}")
                return success_response(data=analitica_data)
            
        except Exception as e:
            logger.error(f"Error consultando analítica específica: {str(e)}")
        
        # =================================================================
        # SI NO EXISTE EL PERÍODO EXACTO, BUSCAR EL MÁS RECIENTE usando utils
        # =================================================================
        
        try:
            # Query analíticas de esta tienda usando utils
            result = query_by_tenant(
                table_name=os.environ['ANALITICA_TABLE'],
                tenant_id=tenant_id,
                limit=1
            )
            
            items = result.get('items', [])
            if items:
                # Tomar la más reciente (primera en la lista)
                analitica_data = items[0]
                # Remover las keys internas agregadas por query_by_tenant
                analitica_data.pop('_tenant_id', None)
                analitica_data.pop('_entity_id', None)
                
                logger.info(f"📊 Analítica más reciente encontrada")
                return success_response(data=analitica_data)
            
        except Exception as e:
            logger.error(f"Error buscando analítica más reciente: {str(e)}")
        
        # =================================================================
        # SI NO HAY ANALÍTICA PREVIA, DEVOLVER ESTRUCTURA VACÍA
        # =================================================================
        
        logger.warning(f"⚠️ No se encontró analítica para {tenant_id}")
        
        analitica_vacia = {
            "periodo": {
                "fecha_inicio": fecha_inicio.strftime('%Y-%m-%d'),
                "fecha_fin": fecha_fin.strftime('%Y-%m-%d'),
                "dias": periodo_dias
            },
            "ventas": {
                "total_ventas": 0,
                "total_ingresos": 0.0,
                "promedio_diario": 0.0
            },
            "gastos": {
                "total_gastos": 0,
                "total_egresos": 0.0,
                "balance": 0.0
            },
            "inventario": {
                "total_productos": 0,
                "productos_sin_stock": 0,
                "productos_bajo_stock": 0,
                "valor_total": 0.0
            },
            "usuarios": {
                "administradores": 0,
                "trabajadores": 0
            },
            "productos_top": [],
            "ventas_diarias": generar_ventas_diarias_vacias(fecha_inicio, fecha_fin),
            "alertas_detectadas": [
                {
                    "tipo": "sinDatos",
                    "severidad": "INFO",
                    "mensaje": "No hay analítica calculada. Ejecute 'Actualizar Analítica' primero."
                }
            ]
        }
        
        return success_response(data=analitica_vacia)
        
    except Exception as e:
        logger.error(f"Error consultando analítica: {str(e)}")
        return error_response("Error interno del servidor", 500)

def generar_ventas_diarias_vacias(fecha_inicio, fecha_fin):
    """Genera estructura de ventas diarias vacía para el período"""
    ventas_diarias = []
    fecha_actual = fecha_inicio
    
    while fecha_actual <= fecha_fin:
        ventas_diarias.append({
            'fecha': fecha_actual.strftime('%Y-%m-%d'),
            'cantidad': 0,
            'ingresos': 0.0
        })
        fecha_actual += timedelta(days=1)
    
    return ventas_diarias