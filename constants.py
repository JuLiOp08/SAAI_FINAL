"""
SAAI - Constantes del Sistema
==============================

Constantes centralizadas para evitar hardcodeo y facilitar mantenimiento.
Todos los Lambdas que necesiten validar roles o mapear roles deben importar desde aquí.
"""

# ============================================
# ROLES DEL SISTEMA
# ============================================

# Roles permitidos para usuarios de tienda (crear/actualizar usuario)
# admin: Administrador de tienda (acceso completo a su tienda)
# worker: Trabajador de tienda (acceso limitado, sin gastos/analytics/reportes)
ALLOWED_ROLES = ['admin', 'worker']

# Roles completos del sistema (incluye SAAI - plataforma)
# saai: Super administrador de la plataforma (acceso a todas las tiendas)
ALL_ROLES = ['admin', 'worker', 'saai']

# Mapeo de roles de DB a roles de JWT/API
# En la base de datos se guardan como TRABAJADOR, ADMIN, SAAI (mayúsculas)
# En el JWT y respuestas API se usan: worker, admin, saai (minúsculas)
ROLE_MAPPING = {
    'TRABAJADOR': 'worker',
    'ADMIN': 'admin',
    'SAAI': 'saai'
}

# Mapeo inverso (de API/JWT a DB)
ROLE_MAPPING_REVERSE = {
    'worker': 'TRABAJADOR',
    'admin': 'ADMIN',
    'saai': 'SAAI'
}

# ============================================
# ESTADOS DEL SISTEMA
# ============================================

# Estados para entidades operativas (productos, usuarios, gastos, etc.)
ESTADO_ACTIVO = 'ACTIVO'
ESTADO_INACTIVO = 'INACTIVO'

# Estados para tiendas (tenants)
ESTADO_TIENDA_ACTIVA = 'ACTIVA'
ESTADO_TIENDA_SUSPENDIDA = 'SUSPENDIDA'
ESTADO_TIENDA_ELIMINADA = 'ELIMINADA'

# ============================================
# VALIDACIONES
# ============================================

# Regex para validación de email RFC 5322 (simplificado pero robusto)
EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

# ============================================
# PAGINACIÓN
# ============================================

# Valores por defecto para paginación SAAI 1.6
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100

# ============================================
# THRESHOLDS ANALÍTICA Y ALERTAS
# ============================================

# Threshold para ganancia diaria baja (en soles)
THRESHOLD_GANANCIA_BAJA = 50

# Threshold para stock bajo de productos (unidades)
THRESHOLD_STOCK_BAJO = 5

# ============================================
# MACHINE LEARNING - PREDICCIÓN DEMANDA
# ============================================

# Tipos de predicción
TIPO_PREDICCION_DIARIA = 'DIARIA'
TIPO_PREDICCION_SEMANAL = 'SEMANAL'

# Tipos de alertas ML
ALERTA_STOCK_BAJO_MANANA = 'stock_bajo_manana'
ALERTA_STOCK_BAJO_SEMANA = 'stock_bajo_semana'
ALERTA_ENTRENAMIENTO_ERROR = 'entrenamiento_errores'

# Configuración modelos
MIN_REGISTROS_ML = 30          # Mínimo de registros para entrenar
DIAS_HISTORICO_ML = 90         # Días históricos para entrenamiento
FORECAST_DIAS_ML = 7           # Días a predecir
DIAS_ACTIVIDAD_MINIMA_ML = 30  # Días de actividad mínima para considerar producto activo
