# auth/__init__.py
"""
SAAI Backend - Módulo de Autenticación y Autorización

Este módulo maneja toda la seguridad del sistema SAAI:
- Lambda Authorizer para validación JWT en rutas privadas
- Login multi-rol (TRABAJADOR, ADMIN, SAAI)
- Validación de credenciales por tipo de usuario
- Gestión de tokens activos en base de datos
- Aislamiento multi-tenant estricto

Componentes principales:
1. authorizer.py - Lambda Authorizer crítico para toda la seguridad
2. login.py - Endpoint público de autenticación multi-rol
3. credentials_validator.py - Validación de usuario/password según rol
4. token_manager.py - Gestión CRUD de tokens activos por rol

Seguridad multi-tenant:
- Todos los JWT contienen claims obligatorios: codigo_usuario, tenant_id, rol
- Authorizer valida token en tabla específica por rol
- Aislamiento estricto: imposible acceder a datos de otro tenant
- Soft invalidation: tokens marcados como INACTIVO vs hard delete

Flujo de autenticación:
1. Cliente → POST /login (público)
2. login.py valida credenciales según tipo (TRABAJADOR/ADMIN vs SAAI)
3. Genera JWT con claims multi-tenant + guarda token activo en BD
4. Cliente usa token en header Authorization: Bearer xxx
5. authorizer.py valida JWT + verifica token activo en BD
6. Authorizer pasa claims al requestContext para funciones de negocio
7. Funciones usan extract_tenant_from_jwt_claims() para aislamiento

Tablas de tokens:
- t_tokens_trabajadores: Tokens de rol TRABAJADOR
- t_tokens_administradores: Tokens de rol ADMIN  
- t_tokens_saai: Tokens de rol SAAI (plataforma)

Modelo estándar: tenant_id + entity_id (codigo_usuario) + data (info del token)
"""

from .login import handler as login_handler
from .authorizer import handler as authorizer_handler
from .credentials_validator import (
    validar_credenciales,
    validar_credenciales_usuario,
    validar_credenciales_saai,
    determinar_tipo_usuario,
    hashear_password,
    verificar_password,
    verificar_tienda_activa,
    actualizar_ultimo_login
)
from .token_manager import (
    guardar_token_activo,
    obtener_token_activo,
    actualizar_ultimo_uso_token,
    invalidar_token,
    invalidar_todos_los_tokens_usuario,
    limpiar_tokens_expirados,
    token_expirado,
    renovar_token,
    validar_token_formato,
    generar_estadisticas_tokens
)

# Configuración del módulo
MODULO_VERSION = "1.0.0"
ROLES_VALIDOS = ['TRABAJADOR', 'ADMIN', 'SAAI']

# Mensajes estándar
MENSAJES = {
    'LOGIN_EXITOSO': 'Autenticación exitosa',
    'LOGIN_FALLIDO': 'Usuario o contraseña incorrectos',
    'TOKEN_INVALIDO': 'Token inválido o expirado',
    'TOKEN_EXPIRADO': 'Su sesión ha expirado, por favor inicie sesión nuevamente',
    'TIENDA_INACTIVA': 'La tienda no está disponible actualmente',
    'ACCESO_DENEGADO': 'No tiene permisos para acceder a este recurso',
    'ERROR_INTERNO': 'Error interno del servidor'
}

# Configuración de seguridad
CONFIGURACION_SEGURIDAD = {
    'JWT_EXPIRES_IN_SECONDS': 86400,  # 24 horas
    'PASSWORD_MIN_LENGTH': 4,
    'PASSWORD_MAX_LENGTH': 50,
    'USERNAME_MIN_LENGTH': 3,
    'USERNAME_MAX_LENGTH': 20,
    'TOKEN_MIN_LENGTH': 50
}

def validar_configuracion_auth():
    """
    Valida que las variables de entorno necesarias estén configuradas
    
    Returns:
        list: Lista de errores de configuración o lista vacía si todo está bien
    """
    import os
    
    errores = []
    
    # Variables obligatorias
    variables_obligatorias = [
        'JWT_SECRET',
        'TOKENS_TRABAJADORES_TABLE',
        'TOKENS_ADMINISTRADORES_TABLE', 
        'TOKENS_SAAI_TABLE',
        'USUARIOS_TABLE',
        'TIENDAS_TABLE'
    ]
    
    for variable in variables_obligatorias:
        if not os.environ.get(variable):
            errores.append(f"Variable de entorno faltante: {variable}")
    
    return errores

def obtener_info_modulo():
    """
    Obtiene información del módulo de autenticación
    
    Returns:
        dict: Información del módulo
    """
    return {
        'nombre': 'SAAI Auth Module',
        'version': MODULO_VERSION,
        'descripcion': 'Módulo de autenticación y autorización multi-tenant',
        'roles_soportados': ROLES_VALIDOS,
        'endpoints': [
            'POST /login (público)',
            'authorizer (interno - todas las rutas privadas)'
        ],
        'configuracion': CONFIGURACION_SEGURIDAD
    }