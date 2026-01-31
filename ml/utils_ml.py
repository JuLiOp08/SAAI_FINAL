# -*- coding: utf-8 -*-
"""
Utilidades ML para SAAI
Funciones compartidas entre EntrenarModelos y PrediccionDemanda
"""

import boto3
import os
import json
import pandas as pd
from datetime import datetime, timedelta
from config import (
    DIAS_ACTIVIDAD_MINIMA,
    VENTAS_MINIMAS_ENTRENAMIENTO,
    DIAS_HISTORICO,
    MIN_REGISTROS_ENTRENAMIENTO,
    S3_BUCKET,
    S3_MODELOS_PREFIX,
    S3_MODELO_FILENAME
)

# Importar utils del proyecto
import sys
sys.path.insert(0, '/var/task')
from utils import (
    query_by_tenant,
    query_by_tenant_with_filter,
    obtener_fecha_hora_peru
)

# Clientes AWS
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
lambda_client = boto3.client('lambda')


def obtener_tiendas_activas():
    """
    Obtiene lista de tenant_ids con estado ACTIVA
    
    Returns:
        list: Lista de códigos de tienda activos
    """
    # Query t_tiendas global (tenant_id = 'SAAI')
    tiendas = query_by_tenant_with_filter(
        't_tiendas',
        'SAAI',
        filter_conditions={'estado': 'ACTIVA'},
        include_inactive=False
    )
    
    return [t['codigo_tienda'] for t in tiendas.get('items', [])]


def filtrar_productos_con_ventas(tenant_id, dias_minimo=30, ventas_minimas=5):
    """
    Filtra productos con ventas recientes
    
    Args:
        tenant_id (str): Código de tienda
        dias_minimo (int): Días hacia atrás para considerar venta reciente
        ventas_minimas (int): Mínimo de ventas para considerar activo
    
    Returns:
        list: Lista de códigos de producto activos
    """
    fecha_limite = datetime.now() - timedelta(days=dias_minimo)
    
    # Query ventas recientes
    ventas_recientes = query_by_tenant_with_filter(
        't_ventas',
        tenant_id,
        filter_conditions={
            'fecha': {'gte': fecha_limite.isoformat()}
        },
        include_inactive=False
    )
    
    # Contar ventas por producto
    productos_contador = {}
    for venta in ventas_recientes.get('items', []):
        for item in venta.get('items', []):
            codigo = item.get('codigo_producto')
            if codigo:
                productos_contador[codigo] = productos_contador.get(codigo, 0) + 1
    
    # Filtrar: solo productos con ventas >= ventas_minimas
    productos_activos = [
        codigo for codigo, count in productos_contador.items()
        if count >= ventas_minimas
    ]
    
    return productos_activos


def obtener_ventas_historicas(tenant_id, codigo_producto, dias=90):
    """
    Obtiene ventas históricas de un producto
    
    Args:
        tenant_id (str): Código de tienda
        codigo_producto (str): Código del producto
        dias (int): Días históricos a consultar
    
    Returns:
        list: Lista de dicts con {fecha, cantidad_vendida}
    """
    fecha_limite = datetime.now() - timedelta(days=dias)
    
    # Query todas las ventas del tenant en el rango
    ventas = query_by_tenant_with_filter(
        't_ventas',
        tenant_id,
        filter_conditions={
            'fecha': {'gte': fecha_limite.isoformat()}
        },
        include_inactive=False
    )
    
    # Extraer datos del producto específico
    datos = []
    for venta in ventas.get('items', []):
        for item in venta.get('items', []):
            if item.get('codigo_producto') == codigo_producto:
                datos.append({
                    'fecha': venta.get('fecha'),
                    'cantidad_vendida': item.get('cantidad', 0)
                })
    
    return datos


def preparar_dataset_holt_winters(ventas):
    """
    Prepara dataset para Holt-Winters
    Solo fecha + cantidad (sin features externas)
    
    Args:
        ventas (list): Lista de ventas [{fecha, cantidad_vendida}]
    
    Returns:
        pd.Series: Serie temporal indexada por fecha
    """
    if not ventas or len(ventas) == 0:
        return None
    
    # Crear DataFrame
    df = pd.DataFrame(ventas)
    df['fecha'] = pd.to_datetime(df['fecha'])
    df = df.sort_values('fecha')
    
    # Agrupar por fecha (sumar ventas del mismo día)
    df_agrupado = df.groupby('fecha')['cantidad_vendida'].sum()
    
    # Rellenar fechas faltantes con 0 (importante para series temporales)
    fecha_inicio = df_agrupado.index.min()
    fecha_fin = df_agrupado.index.max()
    rango_fechas = pd.date_range(start=fecha_inicio, end=fecha_fin, freq='D')
    
    serie = df_agrupado.reindex(rango_fechas, fill_value=0)
    
    return serie


def entrenar_holt_winters(serie, seasonal_periods=7, trend='add', seasonal='add'):
    """
    Entrena modelo Holt-Winters (Triple Exponential Smoothing)
    
    Args:
        serie (pd.Series): Serie temporal
        seasonal_periods (int): Período estacional (7 para semana)
        trend (str): Tipo de tendencia ('add', 'mul', None)
        seasonal (str): Tipo de estacionalidad ('add', 'mul', None)
    
    Returns:
        ExponentialSmoothing fitted model
    """
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    
    # Entrenar modelo
    modelo = ExponentialSmoothing(
        serie,
        seasonal_periods=seasonal_periods,
        trend=trend,
        seasonal=seasonal,
        initialization_method='estimated'
    ).fit(
        optimized=True,
        use_brute=False  # Más rápido
    )
    
    return modelo


def guardar_modelo_s3(tenant_id, codigo_producto, modelo):
    """
    Serializa y guarda modelo en S3
    
    Args:
        tenant_id (str): Código de tienda
        codigo_producto (str): Código del producto
        modelo: Modelo entrenado (Holt-Winters)
    
    Returns:
        str: S3 key del modelo guardado
    """
    import joblib
    
    # Serializar modelo
    modelo_bytes = joblib.dumps(modelo)
    
    # Generar S3 key
    s3_key = S3_MODELOS_PREFIX.format(tenant_id=tenant_id) + S3_MODELO_FILENAME.format(codigo_producto=codigo_producto)
    
    # Guardar en S3
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=s3_key,
        Body=modelo_bytes,
        Metadata={
            'tenant_id': tenant_id,
            'codigo_producto': codigo_producto,
            'fecha_entrenamiento': obtener_fecha_hora_peru(),
            'algoritmo': 'holt-winters'
        }
    )
    
    return s3_key


def cargar_modelo_s3(tenant_id, codigo_producto):
    """
    Carga modelo desde S3
    
    Args:
        tenant_id (str): Código de tienda
        codigo_producto (str): Código del producto
    
    Returns:
        model: Modelo deserializado o None si no existe
    """
    import joblib
    
    try:
        # Generar S3 key
        s3_key = S3_MODELOS_PREFIX.format(tenant_id=tenant_id) + S3_MODELO_FILENAME.format(codigo_producto=codigo_producto)
        
        # Descargar de S3
        response = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
        modelo_bytes = response['Body'].read()
        
        # Deserializar
        modelo = joblib.loads(modelo_bytes)
        
        return modelo
    except s3.exceptions.NoSuchKey:
        return None
    except Exception as e:
        print(f"Error cargando modelo: {str(e)}")
        return None


def invocar_emitir_eventos_ws(evento):
    """
    Invoca Lambda EmitirEventosWs de forma asíncrona
    
    Args:
        evento (dict): Evento a emitir
    """
    try:
        lambda_client.invoke(
            FunctionName=os.environ.get('EMITIR_EVENTOS_WS_FUNCTION_NAME'),
            InvocationType='Event',  # Asíncrono
            Payload=json.dumps(evento)
        )
    except Exception as e:
        print(f"Error invocando EmitirEventosWs: {str(e)}")
        # No fallar si WebSocket falla (no crítico)
  
  
 
# =============================================================================  
# PREDICCIONES BATCH - FUNCIONES COMPARTIDAS  
# ============================================================================= 
def calcular_prediccion_simple(ventas_historicas, dias_forecast=7):
    """
    Weighted Average con decaimiento exponencial y ajuste estacionalidad
    
    Args:
        ventas_historicas: list[dict] con keys 'cantidad_vendida' y 'fecha_venta'
        dias_forecast: días a predecir (default 7)
    
    Returns:
        dict con:
            - demanda_manana (int)
            - demanda_proxima_semana (int)
            - confianza (float 0-1)
            - metodo (str: 'WEIGHTED_AVERAGE')
    
    Raises:
        ValueError: Si ventas_historicas vacío o mal formado
    """
    from datetime import datetime, timedelta
    from collections import defaultdict
    
    # Validaciones
    if not ventas_historicas:
        raise ValueError("ventas_historicas no puede estar vacío")
    
    if not all('cantidad_vendida' in v and 'fecha_venta' in v for v in ventas_historicas):
        raise ValueError("ventas_historicas debe contener 'cantidad_vendida' y 'fecha_venta'")
    
    # Ordenar por fecha DESC (más reciente primero para pesos)
    ventas_ordenadas = sorted(
        ventas_historicas,
        key=lambda x: datetime.fromisoformat(x['fecha_venta'].replace('Z', '+00:00')),
        reverse=True
    )
    
    # 1. DEMANDA BASE con decaimiento exponencial
    pesos = [0.9 ** i for i in range(len(ventas_ordenadas))]
    suma_ponderada = sum(v['cantidad_vendida'] * w for v, w in zip(ventas_ordenadas, pesos))
    suma_pesos = sum(pesos)
    
    demanda_base = suma_ponderada / suma_pesos if suma_pesos > 0 else 0
    
    # 2. ESTACIONALIDAD por día de semana
    ventas_por_dia = defaultdict(list)
    for venta in ventas_ordenadas:
        fecha = datetime.fromisoformat(venta['fecha_venta'].replace('Z', '+00:00'))
        dia_semana = fecha.weekday()  # 0=Lunes, 6=Domingo
        ventas_por_dia[dia_semana].append(venta['cantidad_vendida'])
    
    # Factor estacionalidad: promedio_dia / demanda_base
    factor_dia = {}
    for dia in range(7):
        if dia in ventas_por_dia and ventas_por_dia[dia]:
            promedio_dia = sum(ventas_por_dia[dia]) / len(ventas_por_dia[dia])
            factor_dia[dia] = promedio_dia / demanda_base if demanda_base > 0 else 1.0
        else:
            factor_dia[dia] = 1.0  # Sin datos, asumir promedio
    
    # 3. PREDICCIÓN con ajuste estacionalidad
    fecha_manana = datetime.now() + timedelta(days=1)
    dia_manana = fecha_manana.weekday()
    demanda_manana = demanda_base * factor_dia[dia_manana]
    
    demanda_semana = 0
    for i in range(1, 8):
        fecha_futura = datetime.now() + timedelta(days=i)
        dia_futuro = fecha_futura.weekday()
        demanda_semana += demanda_base * factor_dia[dia_futuro]
    
    # 4. CONFIANZA proporcional a datos
    confianza = min(len(ventas_ordenadas) / 30, 1.0)
    
    return {
        'demanda_manana': max(0, int(round(demanda_manana))),
        'demanda_proxima_semana': max(0, int(round(demanda_semana))),
        'confianza': round(confianza, 2),
        'metodo': 'WEIGHTED_AVERAGE'
    }


def calcular_alerta(stock_actual, demanda_manana, demanda_semana):
    """
    Calcula alerta según stock vs demanda
    
    Args:
        stock_actual (int): Stock disponible actual
        demanda_manana (int): Demanda predicha para mañana
        demanda_semana (int): Demanda predicha para próxima semana
    
    Returns:
        str: 'STOCK_CRITICO_MANANA' | 'STOCK_BAJO_SEMANA' | 'STOCK_SUFICIENTE'
    """
    if stock_actual < demanda_manana:
        return 'STOCK_CRITICO_MANANA'
    elif stock_actual < demanda_semana:
        return 'STOCK_BAJO_SEMANA'
    else:
        return 'STOCK_SUFICIENTE'
