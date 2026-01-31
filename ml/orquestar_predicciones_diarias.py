"""
Lambda: OrquestarPrediccionesDiarias
Trigger: EventBridge schedule cron(0 7 * * ? *)
Responsabilidad: Listar tiendas activas y enviar 1 mensaje SQS por tienda
"""

import boto3
import os
import json
from utils import query_by_tenant
from utils.response_helpers import success_response, error_response

sqs = boto3.client('sqs')
QUEUE_URL = os.environ.get('PREDICCIONES_QUEUE_URL')

def handler(event, context):
    """
    Orquestador simple - NO hace ML
    Lista tiendas activas y encola 1 mensaje SQS por tienda
    """
    try:
        # 1. Listar tiendas activas
        tiendas_activas = obtener_tiendas_activas()
        
        if not tiendas_activas:
            print("⚠️ No hay tiendas activas para procesar")
            return success_response(
                mensaje="No hay tiendas activas",
                data={'tiendas_encoladas': 0}
            )
        
        # 2. Enviar 1 mensaje SQS por tienda
        for tenant_id in tiendas_activas:
            sqs.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=json.dumps({'tenant_id': tenant_id})
            )
            print(f"✅ Encolada tienda: {tenant_id}")
        
        print(f"✅ Proceso completado: {len(tiendas_activas)} tiendas encoladas")
        
        return success_response(
            mensaje=f"Predicciones iniciadas para {len(tiendas_activas)} tiendas",
            data={'tiendas_encoladas': len(tiendas_activas)}
        )
    
    except Exception as e:
        print(f"❌ Error en orquestador: {str(e)}")
        return error_response(f"Error al orquestar predicciones: {str(e)}", 500)


def obtener_tiendas_activas():
    """
    Obtiene lista de tenant_id de tiendas activas
    
    Según SAAI_oficial.txt:
    - t_tiendas usa tenant_id = "SAAI" (partición global sistema)
    - entity_id = codigo_tienda (ej: T001, T002)
    - estado = 'ACTIVA' | 'SUSPENDIDA' | 'ELIMINADA'
    
    Returns:
        list[str]: Lista de codigo_tienda activos
    """
    # Query t_tiendas con tenant_id global "SAAI"
    response = query_by_tenant(
        't_tiendas',
        'SAAI',
        include_inactive=False
    )
    
    # Filtrar solo tiendas con estado = ACTIVA
    tiendas_activas = [
        item['entity_id']  # entity_id = codigo_tienda (ej: T001, T002)
        for item in response.get('items', [])
        if item.get('estado') == 'ACTIVA'
    ]
    
    return tiendas_activas
