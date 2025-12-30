# analytics/ver_analitica.py
import os
import json
import logging
import boto3
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Key
from utils import (
    success_response,
    error_response,
    log_request,
    get_lima_datetime,
    get_tenant_id_from_jwt
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB
dynamodb = boto3.resource('dynamodb')
analitica_table = dynamodb.Table(os.environ['ANALITICA_TABLE'])

def handler(event, context):
    """
    GET /analitica
    
    Devuelve métricas analíticas previamente calculadas.
    NO recalcula, solo consulta t_analitica.
    
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
        log_request(event)
        
        # JWT validation + tenant
        tenant_id = get_tenant_id_from_jwt(event)
        
        # Query params
        query_params = event.get('queryStringParameters') or {}
        periodo_dias = int(query_params.get('periodo', 7))
        
        # Calcular rango de fechas
        lima_now = get_lima_datetime()
        fecha_fin = lima_now
        fecha_inicio = lima_now - timedelta(days=periodo_dias - 1)
        
        entity_id = f"{fecha_inicio.strftime('%Y-%m-%d')}_{fecha_fin.strftime('%Y-%m-%d')}"
        
        logger.info(f"📊 Consultando analítica: {tenant_id} - {entity_id}")
        
        # =================================================================
        # CONSULTAR t_analitica
        # =================================================================
        
        try:
            response = analitica_table.get_item(
                Key={
                    'tenant_id': tenant_id,
                    'entity_id': entity_id
                }
            )
            
            if 'Item' in response:
                analitica_data = response['Item']['data']
                logger.info(f"✅ Analítica encontrada: {entity_id}")
                return success_response(data=analitica_data)
            
        except Exception as e:
            logger.error(f"Error consultando analítica específica: {str(e)}")
        
        # =================================================================
        # SI NO EXISTE EL PERÍODO EXACTO, BUSCAR EL MÁS RECIENTE
        # =================================================================
        
        try:
            # Query analíticas de esta tienda, ordenadas por entity_id (fecha)
            response = analitica_table.query(
                KeyConditionExpression=Key('tenant_id').eq(tenant_id),
                ScanIndexForward=False,  # Orden descendente (más reciente primero)
                Limit=1
            )
            
            items = response.get('Items', [])
            if items:
                analitica_data = items[0]['data']
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