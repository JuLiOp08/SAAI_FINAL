# -*- coding: utf-8 -*-
"""
Configuración de modelos ML para SAAI
Holt-Winters (Triple Exponential Smoothing)
"""

# ============================================
# HOLT-WINTERS CONFIGURATION
# ============================================

HOLT_WINTERS_CONFIG = {
    'seasonal_periods': 7,              # Estacionalidad semanal
    'trend': 'add',                     # Tendencia aditiva
    'seasonal': 'add',                  # Estacionalidad aditiva
    'initialization_method': 'estimated',
    'use_brute': False,                 # Optimización rápida (1-2s por modelo)
    'optimized': True
}

# ============================================
# ENTRENAMIENTO
# ============================================

# Filtro productos activos
DIAS_ACTIVIDAD_MINIMA = 30              # Productos con ventas en últimos 30 días
VENTAS_MINIMAS_ENTRENAMIENTO = 5        # Mínimo 5 ventas para considerar activo

# Dataset
MIN_REGISTROS_ENTRENAMIENTO = 30        # Mínimo 30 registros históricos
DIAS_HISTORICO = 90                     # Consultar últimos 90 días
FORECAST_DAYS = 7                       # Predecir 7 días adelante

# ============================================
# CACHE
# ============================================

CACHE_TTL_HORAS = 24                    # TTL predicciones en DynamoDB (24h)
CACHE_TTL_SEGUNDOS = 24 * 60 * 60       # 86400 segundos

# ============================================
# S3
# ============================================

S3_BUCKET = 'saai-tiendas'
S3_MODELOS_PREFIX = '{tenant_id}/modelos/'
S3_MODELO_FILENAME = '{codigo_producto}.pkl'

# ============================================
# ALERTAS
# ============================================

# Severidades
SEVERITY_CRITICAL = 'CRITICAL'          # stock < demanda_manana → Email
SEVERITY_WARNING = 'WARNING'            # stock < demanda_semana → Solo t_noti
SEVERITY_INFO = 'INFO'                  # Informativo

# Tipos de alerta ML (oficial SAAI_oficial.txt)
ALERTA_STOCK_BAJO_MANANA = 'stockBajoManana'
ALERTA_STOCK_BAJO_SEMANA = 'stockBajoProximaSemana'
ALERTA_ENTRENAMIENTO_ERROR = 'entrenamientoErrores'

# ============================================
# WEBSOCKET
# ============================================

EVENTO_WS_MODELOS_ACTUALIZADOS = 'modelos_actualizados'
EVENTO_WS_PREDICCION_GENERADA = 'prediccion_generada'

# ============================================
# PREDICCIONES MASIVAS (BATCH)
# ============================================

PREDICCIONES_TTL_HORAS = 36
MIN_VENTAS_HOLT_WINTERS = 30  # >= 30 ventas → IA, < 30 → Fórmula
EVENTBRIDGE_CRON_PREDICCIONES_UTC = "cron(0 7 * * ? *)"  # 02:00 AM Lima (UTC-5)

# SQS
PREDICCIONES_QUEUE_NAME = 'saai-predicciones-queue'
