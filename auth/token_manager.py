# auth/token_manager.py
import logging
import os
from datetime import datetime, timedelta, timezone
from utils import (
    put_item_standard,
    get_item_standard,
    update_item_standard,
    delete_item_standard,
    obtener_fecha_hora_peru,
    obtener_timestamp_peru
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas de tokens por rol
TOKENS_TRABAJADORES_TABLE = os.environ.get('TOKENS_TRABAJADORES_TABLE')
TOKENS_ADMINISTRADORES_TABLE = os.environ.get('TOKENS_ADMINISTRADORES_TABLE')
TOKENS_SAAI_TABLE = os.environ.get('TOKENS_SAAI_TABLE')

# Configuración de expiración
JWT_EXPIRES_IN = int(os.environ.get('JWT_EXPIRES_IN', 86400))  # 24 horas

def guardar_token_activo(token, usuario_info):
    """
    Guarda un token JWT como activo en la tabla correspondiente por rol
    
    Args:
        token (str): Token JWT generado
        usuario_info (dict): Información del usuario validado
        
    Returns:
        bool: True si se guardó exitosamente
    """
    try:
        codigo_usuario = usuario_info['codigo_usuario']
        tenant_id = usuario_info['tenant_id']
        rol = usuario_info['rol']
        
        # Determinar tabla según el rol
        tabla_tokens = obtener_tabla_tokens_por_rol(rol)
        if not tabla_tokens:
            logger.error(f"Tabla de tokens no configurada para rol: {rol}")
            return False
        
        # Calcular fecha de expiración
        ahora_utc = datetime.now(timezone.utc)
        expiracion_utc = ahora_utc + timedelta(seconds=JWT_EXPIRES_IN)
        
        # Datos del token
        token_data = {
            'token': token,
            'codigo_usuario': codigo_usuario,
            'tenant_id': tenant_id,
            'rol': rol,
            'estado': 'ACTIVO',
            'generado_en': obtener_fecha_hora_peru(),
            'expira_en': expiracion_utc.isoformat(),
            'ultimo_uso': obtener_fecha_hora_peru(),
            'dispositivo': 'WEB',  # Por defecto
            'ip_address': '0.0.0.0',  # TODO: Extraer de request
            'user_agent': 'SAAI-Frontend',
            # Metadata adicional
            'nombre_usuario': usuario_info.get('nombre', ''),
            'email_usuario': usuario_info.get('email', ''),
            'permisos': usuario_info.get('permisos', [])
        }
        
        # Guardar en DynamoDB
        exito = put_item_standard(tabla_tokens, tenant_id, codigo_usuario, token_data)
        
        if exito:
            logger.info(f"Token guardado exitosamente: usuario={codigo_usuario}, rol={rol}")
            return True
        else:
            logger.error(f"Error guardando token para usuario: {codigo_usuario}")
            return False
        
    except Exception as e:
        logger.error(f"Error guardando token activo: {e}")
        return False

def obtener_token_activo(tenant_id, codigo_usuario, rol):
    """
    Obtiene el token activo de un usuario
    
    Args:
        tenant_id (str): ID del tenant
        codigo_usuario (str): Código del usuario
        rol (str): Rol del usuario
        
    Returns:
        dict: Datos del token activo o None si no existe
    """
    try:
        tabla_tokens = obtener_tabla_tokens_por_rol(rol)
        if not tabla_tokens:
            return None
        
        token_data = get_item_standard(tabla_tokens, tenant_id, codigo_usuario)
        
        if not token_data:
            return None
        
        # Verificar estado activo
        if token_data.get('estado') != 'ACTIVO':
            return None
        
        # Verificar si no ha expirado
        if token_expirado(token_data.get('expira_en')):
            # Marcar como expirado automáticamente
            invalidar_token(tenant_id, codigo_usuario, rol, motivo='TOKEN_EXPIRADO')
            return None
        
        return token_data
        
    except Exception as e:
        logger.error(f"Error obteniendo token activo: {e}")
        return None

def actualizar_ultimo_uso_token(tenant_id, codigo_usuario, rol):
    """
    Actualiza la fecha del último uso del token
    
    Args:
        tenant_id (str): ID del tenant
        codigo_usuario (str): Código del usuario
        rol (str): Rol del usuario
        
    Returns:
        bool: True si se actualizó exitosamente
    """
    try:
        tabla_tokens = obtener_tabla_tokens_por_rol(rol)
        if not tabla_tokens:
            return False
        
        return update_item_standard(
            tabla_tokens, 
            tenant_id, 
            codigo_usuario,
            {
                'ultimo_uso': obtener_fecha_hora_peru(),
                'usos_total': 'INCREMENT'  # TODO: Implementar contador
            }
        )
        
    except Exception as e:
        logger.error(f"Error actualizando último uso de token: {e}")
        return False

def invalidar_token(tenant_id, codigo_usuario, rol, motivo='LOGOUT_MANUAL'):
    """
    Invalida un token activo (soft delete)
    
    Args:
        tenant_id (str): ID del tenant
        codigo_usuario (str): Código del usuario
        rol (str): Rol del usuario
        motivo (str): Motivo de invalidación
        
    Returns:
        bool: True si se invalidó exitosamente
    """
    try:
        tabla_tokens = obtener_tabla_tokens_por_rol(rol)
        if not tabla_tokens:
            return False
        
        return update_item_standard(
            tabla_tokens,
            tenant_id,
            codigo_usuario,
            {
                'estado': 'INACTIVO',
                'fecha_invalidacion': obtener_fecha_hora_peru(),
                'motivo_invalidacion': motivo
            }
        )
        
    except Exception as e:
        logger.error(f"Error invalidando token: {e}")
        return False

def invalidar_todos_los_tokens_usuario(tenant_id, codigo_usuario, rol):
    """
    Invalida todos los tokens de un usuario (útil para logout global)
    
    Args:
        tenant_id (str): ID del tenant
        codigo_usuario (str): Código del usuario
        rol (str): Rol del usuario
        
    Returns:
        bool: True si se invalidaron exitosamente
    """
    try:
        return invalidar_token(tenant_id, codigo_usuario, rol, 'LOGOUT_GLOBAL')
        
    except Exception as e:
        logger.error(f"Error invalidando todos los tokens: {e}")
        return False

def limpiar_tokens_expirados(rol, limite_limpieza=100):
    """
    Limpia tokens expirados de una tabla (ejecutar periódicamente)
    
    Args:
        rol (str): Rol para determinar tabla
        limite_limpieza (int): Máximo número de tokens a limpiar
        
    Returns:
        int: Número de tokens limpiados
    """
    try:
        tabla_tokens = obtener_tabla_tokens_por_rol(rol)
        if not tabla_tokens:
            return 0
        
        # TODO: Implementar scan para encontrar tokens expirados
        # Por ahora, log para implementación futura
        logger.info(f"Limpieza de tokens programada para tabla: {tabla_tokens}")
        return 0
        
    except Exception as e:
        logger.error(f"Error limpiando tokens expirados: {e}")
        return 0

def obtener_tabla_tokens_por_rol(rol):
    """
    Obtiene el nombre de la tabla de tokens según el rol
    
    Args:
        rol (str): Rol del usuario
        
    Returns:
        str: Nombre de la tabla o None
    """
    tablas_por_rol = {
        'TRABAJADOR': TOKENS_TRABAJADORES_TABLE,
        'ADMIN': TOKENS_ADMINISTRADORES_TABLE,
        'SAAI': TOKENS_SAAI_TABLE
    }
    
    return tablas_por_rol.get(rol)

def token_expirado(fecha_expiracion_iso):
    """
    Verifica si un token ha expirado
    
    Args:
        fecha_expiracion_iso (str): Fecha de expiración en formato ISO
        
    Returns:
        bool: True si ha expirado
    """
    try:
        if not fecha_expiracion_iso:
            return True
        
        ahora_utc = datetime.now(timezone.utc)
        expiracion_dt = datetime.fromisoformat(fecha_expiracion_iso.replace('Z', '+00:00'))
        
        return ahora_utc > expiracion_dt
        
    except Exception as e:
        logger.error(f"Error verificando expiración de token: {e}")
        return True

def generar_estadisticas_tokens(tenant_id):
    """
    Genera estadísticas de tokens activos para una tienda
    
    Args:
        tenant_id (str): ID del tenant
        
    Returns:
        dict: Estadísticas de uso de tokens
    """
    try:
        estadisticas = {
            'tokens_trabajadores': 0,
            'tokens_administradores': 0,
            'total_activos': 0,
            'generado_en': obtener_fecha_hora_peru()
        }
        
        # Contar tokens por rol
        for rol, tabla in [
            ('TRABAJADOR', TOKENS_TRABAJADORES_TABLE),
            ('ADMIN', TOKENS_ADMINISTRADORES_TABLE)
        ]:
            if tabla and tenant_id != 'SAAI':
                token_data = get_item_standard(tabla, tenant_id, f"STATS_{rol}")
                # TODO: Implementar conteo real
                pass
        
        return estadisticas
        
    except Exception as e:
        logger.error(f"Error generando estadísticas de tokens: {e}")
        return {}

def renovar_token(tenant_id, codigo_usuario, rol, nuevo_token):
    """
    Renueva un token existente con uno nuevo
    
    Args:
        tenant_id (str): ID del tenant
        codigo_usuario (str): Código del usuario
        rol (str): Rol del usuario
        nuevo_token (str): Nuevo token JWT
        
    Returns:
        bool: True si se renovó exitosamente
    """
    try:
        tabla_tokens = obtener_tabla_tokens_por_rol(rol)
        if not tabla_tokens:
            return False
        
        # Calcular nueva fecha de expiración
        ahora_utc = datetime.now(timezone.utc)
        nueva_expiracion = ahora_utc + timedelta(seconds=JWT_EXPIRES_IN)
        
        return update_item_standard(
            tabla_tokens,
            tenant_id,
            codigo_usuario,
            {
                'token': nuevo_token,
                'renovado_en': obtener_fecha_hora_peru(),
                'expira_en': nueva_expiracion.isoformat(),
                'ultimo_uso': obtener_fecha_hora_peru()
            }
        )
        
    except Exception as e:
        logger.error(f"Error renovando token: {e}")
        return False

def validar_token_formato(token):
    """
    Validaciones básicas del formato del token
    
    Args:
        token (str): Token a validar
        
    Returns:
        bool: True si el formato es válido
    """
    try:
        if not token or len(token) < 50:
            return False
        
        # JWT debe tener 3 partes separadas por puntos
        partes = token.split('.')
        if len(partes) != 3:
            return False
        
        # Cada parte debe tener contenido
        if not all(parte for parte in partes):
            return False
        
        return True
        
    except Exception:
        return False