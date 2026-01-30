# -*- coding: utf-8 -*-
"""
Lambda: PrediccionDemanda
Predice demanda para un producto usando Holt-Winters
Endpoint: POST /predicciones
"""

import boto3
import os
import json
from datetime import datetime, timedelta
from decimal import Decimal
from config import (
    FORECAST_DAYS,
    CACHE_TTL_SEGUNDOS,
    MIN_REGISTROS_ENTRENAMIENTO,
    DIAS_HISTORICO,
    HOLT_WINTERS_CONFIG,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    ALERTA_STOCK_BAJO_MANANA,
    ALERTA_STOCK_BAJO_SEMANA,
    EVENTO_WS_PREDICCION_GENERADA
)
from utils_ml import (
    cargar_modelo_s3,
    obtener_ventas_historicas,
    preparar_dataset_holt_winters,
    entrenar_holt_winters,
    guardar_modelo_s3,
    invocar_emitir_eventos_ws
)

# Importar utils del proyecto
import sys
sys.path.insert(0, '/var/task')
from utils import (
    success_response,
    error_response,
    validation_error_response,
    parse_request_body,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims,
    verificar_rol_permitido,
    get_item_standard,
    put_item_standard,
    obtener_solo_fecha_peru,
    obtener_fecha_hora_peru
)

# Clientes AWS
sns = boto3.client('sns')

# Variables de entorno
ALERTAS_SNS_TOPIC_ARN = os.environ.get('ALERTAS_SNS_TOPIC_ARN')


def handler(event, context):
    """
    Handler principal - Predice demanda de un producto
    
    Request:
        {
            "codigo_producto": "T001P005"
        }
    
    Response (oficial SAAI_oficial.txt):
        {
            "codigo_producto": "T001P005",
            "demanda_manana": 15,
            "demanda_proxima_semana": 95
        }
    """
    try:
        # 1. Verificar rol ADMIN
        tiene_permiso, error = verificar_rol_permitido(event, ['ADMIN'])
        if not tiene_permiso:
            return error
        
        # 2. Extraer datos de la request
        tenant_id = extract_tenant_from_jwt_claims(event)
        body = parse_request_body(event)
        
        # Validar parámetros
        codigo_producto = body.get('codigo_producto')
        if not codigo_producto:
            return validation_error_response({'codigo_producto': 'Campo requerido'})
        
        # 2. Verificar cache (t_predicciones)
        prediccion_cache = verificar_cache(tenant_id, codigo_producto)
        if prediccion_cache:
            print(f"✅ Cache HIT para {codigo_producto}")
            return success_response(data=prediccion_cache)
        
        print(f"⚠️ Cache MISS para {codigo_producto} - Generando predicción...")
        
        # 3. Cargar o entrenar modelo
        modelo = cargar_modelo_s3(tenant_id, codigo_producto)
        
        if not modelo:
            print(f"Modelo no existe en S3 - Entrenando on-demand...")
            modelo = entrenar_modelo_on_demand(tenant_id, codigo_producto)
            
            if not modelo:
                return error_response(
                    mensaje=f"No hay datos suficientes para predecir demanda de {codigo_producto}",
                    detalles={'minimo_registros': MIN_REGISTROS_ENTRENAMIENTO},
                    status_code=400
                )
        
        # 4. Ejecutar predicción (7 días)
        forecast = modelo.forecast(steps=FORECAST_DAYS)
        
        # 5. Calcular métricas
        demanda_manana = int(round(float(forecast[0])))  # Día 1
        demanda_proxima_semana = int(round(float(forecast.sum())))  # Suma 7 días
        
        # Asegurar valores >= 0
        demanda_manana = max(0, demanda_manana)
        demanda_proxima_semana = max(0, demanda_proxima_semana)
        
        # 6. Obtener stock actual
        producto = get_item_standard('t_productos', tenant_id, codigo_producto)
        stock_actual = int(producto.get('stock', 0)) if producto else 0
        
        # 7. Guardar en cache
        prediccion_data = {
            'codigo_producto': codigo_producto,
            'demanda_manana': demanda_manana,
            'demanda_proxima_semana': demanda_proxima_semana,
            'forecast_7_dias': [float(x) for x in forecast.tolist()],
            'stock_actual': stock_actual,
            'fecha_prediccion': obtener_fecha_hora_peru(),
            'estado': 'ACTIVO',
            'ttl': int((datetime.now() + timedelta(seconds=CACHE_TTL_SEGUNDOS)).timestamp())
        }
        
        guardar_cache(tenant_id, codigo_producto, prediccion_data)
        
        # 8. Publicar alertas SNS
        publicar_alertas_prediccion(
            tenant_id=tenant_id,
            codigo_producto=codigo_producto,
            stock_actual=stock_actual,
            demanda_manana=demanda_manana,
            demanda_semana=demanda_proxima_semana
        )
        
        # 9. Emitir evento WebSocket
        invocar_emitir_eventos_ws({
            'tipo': EVENTO_WS_PREDICCION_GENERADA,
            'tenant_id': tenant_id,
            'codigo_producto': codigo_producto,
            'demanda_manana': demanda_manana,
            'timestamp': datetime.now().isoformat()
        })
        
        # 10. Retornar respuesta (oficial SAAI_oficial.txt)
        return success_response(
            mensaje='Predicción generada exitosamente',
            data={
                'codigo_producto': codigo_producto,
                'demanda_manana': int(demanda_manana),
                'demanda_proxima_semana': int(demanda_proxima_semana)
            }
        )
    
    except Exception as e:
        print(f"ERROR en PrediccionDemanda: {str(e)}")
        return error_response(
            mensaje='Error al generar predicción',
            detalles={'error': str(e)},
            status_code=500
        )


def verificar_cache(tenant_id, codigo_producto):
    """
    Verifica si existe predicción en cache (t_predicciones)
    
    Args:
        tenant_id (str): Código de tienda
        codigo_producto (str): Código del producto
    
    Returns:
        dict: Predicción desde cache o None
    """
    fecha_hoy = obtener_solo_fecha_peru()
    cache_key = f"{codigo_producto}#{fecha_hoy}"
    
    cache = get_item_standard('t_predicciones', tenant_id, cache_key)
    
    # Retornar solo campos oficiales (SAAI_oficial.txt)
    if cache and cache.get('estado') == 'ACTIVO':
        return {
            'codigo_producto': cache.get('codigo_producto'),
            'demanda_manana': int(cache.get('demanda_manana', 0)),
            'demanda_proxima_semana': int(cache.get('demanda_proxima_semana', 0))
        }
    
    return None


def guardar_cache(tenant_id, codigo_producto, prediccion_data):
    """
    Guarda predicción en cache (t_predicciones con TTL)
    
    Args:
        tenant_id (str): Código de tienda
        codigo_producto (str): Código del producto
        prediccion_data (dict): Datos de la predicción
    """
    fecha_hoy = obtener_solo_fecha_peru()
    cache_key = f"{codigo_producto}#{fecha_hoy}"
    
    put_item_standard('t_predicciones', tenant_id, cache_key, prediccion_data)


def entrenar_modelo_on_demand(tenant_id, codigo_producto):
    """
    Entrena modelo on-demand si no existe en S3
    
    Args:
        tenant_id (str): Código de tienda
        codigo_producto (str): Código del producto
    
    Returns:
        model: Modelo entrenado o None si no hay datos
    """
    # 1. Obtener ventas históricas
    ventas = obtener_ventas_historicas(tenant_id, codigo_producto, DIAS_HISTORICO)
    
    # 2. Validar datos suficientes
    if len(ventas) < MIN_REGISTROS_ENTRENAMIENTO:
        print(f"Datos insuficientes: {len(ventas)} registros (mínimo {MIN_REGISTROS_ENTRENAMIENTO})")
        return None
    
    # 3. Preparar dataset
    serie = preparar_dataset_holt_winters(ventas)
    
    if serie is None or len(serie) < MIN_REGISTROS_ENTRENAMIENTO:
        print("Error al preparar dataset")
        return None
    
    # 4. Entrenar modelo
    modelo = entrenar_holt_winters(
        serie,
        seasonal_periods=HOLT_WINTERS_CONFIG['seasonal_periods'],
        trend=HOLT_WINTERS_CONFIG['trend'],
        seasonal=HOLT_WINTERS_CONFIG['seasonal']
    )
    
    # 5. Guardar en S3 para futuros usos
    guardar_modelo_s3(tenant_id, codigo_producto, modelo)
    
    print(f"✅ Modelo entrenado on-demand para {codigo_producto}")
    
    return modelo


def publicar_alertas_prediccion(tenant_id, codigo_producto, stock_actual, demanda_manana, demanda_semana):
    """
    Publica alertas en SNS según stock vs demanda
    
    Args:
        tenant_id (str): Código de tienda
        codigo_producto (str): Código del producto
        stock_actual (int): Stock actual
        demanda_manana (int): Demanda predicha para mañana
        demanda_semana (int): Demanda predicha para próxima semana
    """
    try:
        # CASO 1: Stock insuficiente para MAÑANA (CRITICAL → Email)
        if stock_actual < demanda_manana:
            sns.publish(
                TopicArn=ALERTAS_SNS_TOPIC_ARN,
                Message=json.dumps({
                    'tipo': ALERTA_STOCK_BAJO_MANANA,
                    'tenant_id': tenant_id,
                    'codigo_producto': codigo_producto,
                    'stock_actual': stock_actual,
                    'demanda_manana': demanda_manana,
                    'diferencia': demanda_manana - stock_actual,
                    'mensaje': f'⚠️ Stock crítico: {codigo_producto} - Stock: {stock_actual}, Demanda mañana: {demanda_manana}',
                    'fecha': obtener_fecha_hora_peru()
                }),
                MessageAttributes={
                    'tipo': {'DataType': 'String', 'StringValue': ALERTA_STOCK_BAJO_MANANA},
                    'severity': {'DataType': 'String', 'StringValue': SEVERITY_CRITICAL},
                    'tenant_id': {'DataType': 'String', 'StringValue': tenant_id}
                }
            )
            print(f"🚨 Alerta CRITICAL publicada: stock < demanda_manana")
        
        # CASO 2: Stock insuficiente para PRÓXIMA SEMANA (WARNING → Solo t_noti)
        elif stock_actual < demanda_semana:
            sns.publish(
                TopicArn=ALERTAS_SNS_TOPIC_ARN,
                Message=json.dumps({
                    'tipo': ALERTA_STOCK_BAJO_SEMANA,
                    'tenant_id': tenant_id,
                    'codigo_producto': codigo_producto,
                    'stock_actual': stock_actual,
                    'demanda_semana': demanda_semana,
                    'diferencia': demanda_semana - stock_actual,
                    'mensaje': f'Stock insuficiente para próxima semana: {codigo_producto}',
                    'fecha': obtener_fecha_hora_peru()
                }),
                MessageAttributes={
                    'tipo': {'DataType': 'String', 'StringValue': ALERTA_STOCK_BAJO_SEMANA},
                    'severity': {'DataType': 'String', 'StringValue': SEVERITY_WARNING},
                    'tenant_id': {'DataType': 'String', 'StringValue': tenant_id}
                }
            )
            print(f"⚠️ Alerta WARNING publicada: stock < demanda_semana")
    
    except Exception as e:
        print(f"Error publicando alertas SNS: {str(e)}")
        # No fallar por error en alertas
