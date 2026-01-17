# -*- coding: utf-8 -*-
"""
Lambda: EntrenarModelos
Entrena modelos Holt-Winters para productos activos
Ejecutado por EventBridge cada 3 días
"""

import boto3
import os
import json
from datetime import datetime
from config import (
    HOLT_WINTERS_CONFIG,
    DIAS_ACTIVIDAD_MINIMA,
    VENTAS_MINIMAS_ENTRENAMIENTO,
    DIAS_HISTORICO,
    MIN_REGISTROS_ENTRENAMIENTO,
    SEVERITY_WARNING,
    ALERTA_ENTRENAMIENTO_ERROR,
    EVENTO_WS_MODELOS_ACTUALIZADOS
)
from utils_ml import (
    obtener_tiendas_activas,
    filtrar_productos_con_ventas,
    obtener_ventas_historicas,
    preparar_dataset_holt_winters,
    entrenar_holt_winters,
    guardar_modelo_s3,
    invocar_emitir_eventos_ws
)

# Clientes AWS
sns = boto3.client('sns')

# Variables de entorno
ALERTAS_SNS_TOPIC_ARN = os.environ.get('ALERTAS_SNS_TOPIC_ARN')


def handler(event, context):
    """
    Handler principal - Entrena modelos para productos activos
    
    Estrategia:
    1. Filtrar productos con ventas recientes (últimos 30 días)
    2. Entrenar solo esos productos (evita timeout)
    3. Productos sin modelo → se entrenan on-demand en PrediccionDemanda
    
    Returns:
        dict: Resultado con estadísticas de entrenamiento
    """
    print("=== INICIO ENTRENAMIENTO MODELOS ===")
    
    modelos_entrenados = 0
    modelos_fallidos = 0
    errores = []
    
    try:
        # 1. Obtener tiendas activas
        tenant_ids = obtener_tiendas_activas()
        print(f"Tiendas activas encontradas: {len(tenant_ids)}")
        
        # 2. Iterar por cada tienda
        for tenant_id in tenant_ids:
            print(f"\n--- Procesando tienda: {tenant_id} ---")
            
            # 3. Filtrar productos con ventas recientes
            productos_activos = filtrar_productos_con_ventas(
                tenant_id,
                dias_minimo=DIAS_ACTIVIDAD_MINIMA,
                ventas_minimas=VENTAS_MINIMAS_ENTRENAMIENTO
            )
            
            print(f"Productos activos (últimos {DIAS_ACTIVIDAD_MINIMA} días): {len(productos_activos)}")
            
            # 4. Entrenar cada producto activo
            for codigo_producto in productos_activos:
                try:
                    resultado = entrenar_producto(tenant_id, codigo_producto)
                    
                    if resultado['exito']:
                        modelos_entrenados += 1
                        print(f"✅ Modelo entrenado: {codigo_producto}")
                    else:
                        modelos_fallidos += 1
                        errores.append({
                            'tenant_id': tenant_id,
                            'codigo_producto': codigo_producto,
                            'error': resultado['error']
                        })
                        print(f"⚠️ Error: {codigo_producto} - {resultado['error']}")
                
                except Exception as e:
                    modelos_fallidos += 1
                    errores.append({
                        'tenant_id': tenant_id,
                        'codigo_producto': codigo_producto,
                        'error': str(e)
                    })
                    print(f"❌ Excepción: {codigo_producto} - {str(e)}")
        
        # 5. Publicar alertas si hay errores significativos
        if modelos_fallidos > 0:
            publicar_alerta_errores(modelos_fallidos, errores[:10])  # Primeros 10 errores
        
        # 6. Emitir evento WebSocket
        invocar_emitir_eventos_ws({
            'tipo': EVENTO_WS_MODELOS_ACTUALIZADOS,
            'total_modelos_entrenados': modelos_entrenados,
            'total_errores': modelos_fallidos,
            'timestamp': datetime.now().isoformat()
        })
        
        # 7. Retornar resultado
        resultado_final = {
            'statusCode': 200,
            'body': {
                'mensaje': 'Entrenamiento completado',
                'modelos_entrenados': modelos_entrenados,
                'modelos_fallidos': modelos_fallidos,
                'tiendas_procesadas': len(tenant_ids)
            }
        }
        
        print(f"\n=== RESUMEN ===")
        print(f"Modelos entrenados: {modelos_entrenados}")
        print(f"Modelos fallidos: {modelos_fallidos}")
        print(f"Tiendas procesadas: {len(tenant_ids)}")
        
        return resultado_final
    
    except Exception as e:
        print(f"ERROR CRÍTICO en EntrenarModelos: {str(e)}")
        return {
            'statusCode': 500,
            'body': {
                'error': str(e)
            }
        }


def entrenar_producto(tenant_id, codigo_producto):
    """
    Entrena modelo para un producto específico
    
    Args:
        tenant_id (str): Código de tienda
        codigo_producto (str): Código del producto
    
    Returns:
        dict: {exito: bool, error: str}
    """
    # 1. Obtener ventas históricas
    ventas = obtener_ventas_historicas(tenant_id, codigo_producto, DIAS_HISTORICO)
    
    # 2. Validar datos suficientes
    if len(ventas) < MIN_REGISTROS_ENTRENAMIENTO:
        return {
            'exito': False,
            'error': f'Datos insuficientes: {len(ventas)} registros (mínimo {MIN_REGISTROS_ENTRENAMIENTO})'
        }
    
    # 3. Preparar dataset (serie temporal)
    serie = preparar_dataset_holt_winters(ventas)
    
    if serie is None or len(serie) < MIN_REGISTROS_ENTRENAMIENTO:
        return {
            'exito': False,
            'error': 'Error al preparar dataset'
        }
    
    # 4. Entrenar modelo Holt-Winters
    modelo = entrenar_holt_winters(
        serie,
        seasonal_periods=HOLT_WINTERS_CONFIG['seasonal_periods'],
        trend=HOLT_WINTERS_CONFIG['trend'],
        seasonal=HOLT_WINTERS_CONFIG['seasonal']
    )
    
    # 5. Guardar modelo en S3
    s3_key = guardar_modelo_s3(tenant_id, codigo_producto, modelo)
    
    return {
        'exito': True,
        'error': None,
        's3_key': s3_key
    }


def publicar_alerta_errores(total_errores, lista_errores):
    """
    Publica alerta en SNS si hay errores de entrenamiento
    
    Args:
        total_errores (int): Total de errores
        lista_errores (list): Lista de errores
    """
    try:
        sns.publish(
            TopicArn=ALERTAS_SNS_TOPIC_ARN,
            Message=json.dumps({
                'tipo': ALERTA_ENTRENAMIENTO_ERROR,
                'total_errores': total_errores,
                'detalles': lista_errores,
                'mensaje': f'Se encontraron {total_errores} errores durante el entrenamiento de modelos',
                'fecha': datetime.now().isoformat()
            }),
            MessageAttributes={
                'tipo': {'DataType': 'String', 'StringValue': ALERTA_ENTRENAMIENTO_ERROR},
                'severity': {'DataType': 'String', 'StringValue': SEVERITY_WARNING}
            }
        )
    except Exception as e:
        print(f"Error publicando alerta SNS: {str(e)}")
