# utils/__init__.py
"""
SAAI Backend - Utilidades Comunes

Este módulo contiene utilidades compartidas por todas las funciones Lambda:
- Manejo de fechas/horas en zona horaria de Perú
- Formateo de respuestas HTTP estándar
- Operaciones DynamoDB con modelo estándar (tenant_id + entity_id + data)
- Generación de códigos únicos para entidades
- Manejo de tokens JWT y autenticación
- Paginación para APIs REST

Importaciones rápidas:
from utils import success_response, error_response
from utils import obtener_fecha_hora_peru, formatear_fecha_legible  
from utils import put_item_standard, get_item_standard, query_by_tenant
from utils import generar_codigo_producto, validar_formato_codigo_tienda
from utils import generar_token_jwt, verificar_token_jwt
from utils import extraer_parametros_paginacion, crear_respuesta_paginada
"""

# Importaciones principales para fácil acceso
from .datetime_utils import (
    obtener_fecha_hora_peru,
    obtener_solo_fecha_peru, 
    obtener_timestamp_peru,
    formatear_fecha_legible,
    es_fecha_valida,
    obtener_inicio_dia_peru,
    obtener_fin_dia_peru,
    calcular_diferencia_dias,
    obtener_rango_semana_actual,
    obtener_rango_mes_actual,
    validar_formato_fecha
)

from .response_utils import (
    success_response,
    error_response,
    validation_error_response,
    unauthorized_response,
    forbidden_response,
    not_found_response,
    conflict_response,
    parse_request_body,
    get_path_parameter,
    get_query_parameter,
    get_header,
    options_response,
    log_request,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims
)

from .dynamodb_utils import (
    put_item_standard,
    get_item_standard,
    update_item_standard,
    delete_item_standard,
    query_by_tenant,
    query_by_tenant_with_filter,
    increment_counter,
    batch_write_items,
    get_table
)

from .code_generator import (
    generar_codigo_tienda,
    generar_codigo_usuario,
    generar_codigo_producto,
    generar_codigo_venta,
    generar_codigo_gasto,
    generar_codigo_reporte,
    generar_codigo_notificacion,
    generar_codigo_analitica,
    generar_codigo_prediccion,
    generar_password_temporal,
    generar_token_recuperacion,
    validar_formato_codigo_tienda,
    validar_formato_codigo_usuario,
    extraer_codigo_tienda_de_entidad,
    generar_codigo_siguiente
)

from .jwt_utils import (
    generar_token_jwt,
    verificar_token_jwt,
    obtener_scope_por_rol,
    validar_scope_requerido,
    extraer_token_de_header,
    generar_claims_authorizer,
    token_expira_pronto,
    renovar_token_si_es_necesario,
    validar_token_en_base_datos
)

from .pagination_utils import (
    extraer_parametros_paginacion,
    crear_respuesta_paginada,
    crear_cursor_paginacion,
    decodificar_cursor_paginacion,
    calcular_offset_y_pagina,
    validar_parametros_busqueda,
    crear_filtros_dynamodb_desde_busqueda,
    ordenar_items_en_memoria
)

# Versión del módulo
__version__ = "1.0.0"

# Configuraciones globales
TIMEZONE_PERU = "America/Lima"
JWT_ALGORITHM = "HS256"
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Códigos de estado estándar
STATUS_CODES = {
    'SUCCESS': 200,
    'CREATED': 201,
    'BAD_REQUEST': 400,
    'UNAUTHORIZED': 401,
    'FORBIDDEN': 403,
    'NOT_FOUND': 404,
    'CONFLICT': 409,
    'INTERNAL_ERROR': 500
}

# Roles válidos del sistema
ROLES_VALIDOS = ['TRABAJADOR', 'ADMIN', 'SAAI']

# Estados válidos para entidades
ESTADOS_ENTIDAD = ['ACTIVO', 'INACTIVO']

# Tipos de reporte válidos
TIPOS_REPORTE = ['INV', 'VEN', 'GAS', 'GEN']

# Métodos de pago válidos
METODOS_PAGO = ['EFECTIVO', 'TARJETA', 'YAPE', 'PLIN', 'TRANSFERENCIA']

# Categorías de gasto válidas
CATEGORIAS_GASTO = [
    'SERVICIOS',
    'SUMINISTROS', 
    'EQUIPAMIENTO',
    'MANTENIMIENTO',
    'MARKETING',
    'PERSONAL',
    'OTROS'
]

# Categorías de producto válidas
CATEGORIAS_PRODUCTO = [
    'ALIMENTOS',
    'BEBIDAS',
    'LIMPIEZA',
    'HIGIENE',
    'ELECTRODOMESTICOS',
    'TECNOLOGIA',
    'ROPA',
    'OTROS'
]

def validar_rol(rol):
    """Valida si un rol es válido en el sistema"""
    return rol in ROLES_VALIDOS

def validar_estado(estado):
    """Valida si un estado es válido"""
    return estado in ESTADOS_ENTIDAD

def validar_metodo_pago(metodo):
    """Valida si un método de pago es válido"""
    return metodo in METODOS_PAGO

def validar_categoria_gasto(categoria):
    """Valida si una categoría de gasto es válida"""
    return categoria in CATEGORIAS_GASTO

def validar_categoria_producto(categoria):
    """Valida si una categoría de producto es válida"""
    return categoria in CATEGORIAS_PRODUCTO