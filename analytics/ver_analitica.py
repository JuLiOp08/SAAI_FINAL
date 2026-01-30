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
from utils.datetime_utils import PERU_TIMEZONE

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    """
    GET /analitica?periodo=semana
    
    Devuelve métricas analíticas previamente calculadas.
    NO recalcula, solo consulta t_analitica.
    
    Este endpoint es la ÚNICA FUENTE DE VERDAD para datos analíticos.
    El frontend debe hacer refetch a este endpoint cuando reciba
    notificaciones WebSocket de tipo 'analitica_actualizada'.
    
    Query params: ?periodo=semana (valores: dia, semana, mes. Default: semana)
    
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
        periodo = query_params.get('periodo', 'semana')  # dia, semana, mes
        
        # Validar periodo
        if periodo not in ['dia', 'semana', 'mes']:
            return error_response("Periodo inválido. Use: dia, semana, mes", 400)
        
        # El entity_id es el nombre del periodo
        entity_id = periodo
        
        logger.info(f"📊 Consultando analítica: {tenant_id} - periodo: {periodo}")
        
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
                logger.info(f"✅ Analítica encontrada: {periodo}")
                return success_response(data=analitica_data)
            
        except Exception as e:
            logger.error(f"Error consultando analítica: {str(e)}")
        
        # =================================================================
        # SI NO HAY ANALÍTICA, DEVOLVER ESTRUCTURA VACÍA CON SUGERENCIA
        # =================================================================
        
        logger.warning(f"⚠️ No se encontró analítica '{periodo}' para {tenant_id}")
        
        # Calcular fechas para estructura vacía - usar hora de Perú
        fecha_calc = datetime.now(PERU_TIMEZONE)
        if periodo == 'dia':
            fecha_inicio = fecha_calc
            dias = 1
        elif periodo == 'semana':
            fecha_inicio = fecha_calc - timedelta(days=6)
            dias = 7
        else:  # mes
            fecha_inicio = fecha_calc - timedelta(days=29)
            dias = 30
        
        analitica_vacia = {
            "periodo": {
                "tipo": periodo,
                "fecha_inicio": fecha_inicio.strftime('%Y-%m-%d'),
                "fecha_fin": fecha_calc.strftime('%Y-%m-%d'),
                "dias": dias
            },
            "ventas": {
                "total_ventas": 0,
                "total_ingresos": 0.0
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
            "ventas_diarias": generar_ventas_diarias_vacias(fecha_inicio, fecha_calc),
            "ventas_por_trabajador": [],
            "alertas_detectadas": [
                {
                    "tipo": "sinDatos",
                    "severidad": "INFO",
                    "mensaje": f"No hay analítica calculada para '{periodo}'. Ejecute 'Actualizar Analítica' primero."
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