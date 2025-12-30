# auth/credentials_validator.py
import hashlib
import logging
import os
from utils import (
    get_item_standard,
    validar_formato_codigo_usuario,
    validar_formato_codigo_tienda
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas del sistema
USUARIOS_TABLE = os.environ.get('USUARIOS_TABLE')
TIENDAS_TABLE = os.environ.get('TIENDAS_TABLE')

def validar_credenciales_usuario(usuario, password):
    """
    Valida credenciales de usuario (TRABAJADOR o ADMIN)
    
    Según documento SAAI:
    - TRABAJADOR y ADMIN se buscan en t_usuarios
    - Se valida codigo_usuario + password hasheado
    - Se verifica estado ACTIVO
    - Se retorna info completa del usuario incluyendo tenant_id
    
    Args:
        usuario (str): Código de usuario (ej: T001U001)
        password (str): Contraseña en texto plano
        
    Returns:
        dict: Información del usuario si es válido, None si no es válido
        {
            'codigo_usuario': 'T001U001',
            'tenant_id': 'T001', 
            'rol': 'TRABAJADOR|ADMIN',
            'nombre': '...',
            'email': '...',
            'estado': 'ACTIVO'
        }
    """
    try:
        logger.info(f"Validando credenciales para usuario: {usuario}")
        
        # Validar formato del código de usuario
        if not validar_formato_codigo_usuario(usuario):
            logger.warning(f"Formato de código de usuario inválido: {usuario}")
            return None
        
        # Extraer tenant_id del código de usuario (primeros 4 caracteres)
        tenant_id = usuario[:4]
        
        if not validar_formato_codigo_tienda(tenant_id):
            logger.warning(f"Código de tienda inválido extraído: {tenant_id}")
            return None
        
        # Buscar usuario en DynamoDB
        usuario_data = get_item_standard(USUARIOS_TABLE, tenant_id, usuario)
        
        if not usuario_data:
            logger.warning(f"Usuario no encontrado: {usuario}")
            return None
        
        # Verificar estado activo
        if usuario_data.get('estado') != 'ACTIVO':
            logger.warning(f"Usuario inactivo: {usuario}")
            return None
        
        # Validar contraseña
        password_hasheado = usuario_data.get('password')
        if not password_hasheado:
            logger.error(f"Usuario sin contraseña configurada: {usuario}")
            return None
        
        if not verificar_password(password, password_hasheado):
            logger.warning(f"Contraseña incorrecta para usuario: {usuario}")
            return None
        
        # Verificar que tenga rol válido
        rol = usuario_data.get('rol')
        if rol not in ['TRABAJADOR', 'ADMIN']:
            logger.error(f"Rol inválido para usuario: {usuario}, rol: {rol}")
            return None
        
        # Retornar información del usuario validado
        return {
            'codigo_usuario': usuario,
            'tenant_id': tenant_id,
            'rol': rol,
            'nombre': usuario_data.get('nombre', ''),
            'email': usuario_data.get('email', ''),
            'estado': usuario_data.get('estado'),
            'telefono': usuario_data.get('telefono', ''),
            'ultimo_login': usuario_data.get('ultimo_login'),
            'created_at': usuario_data.get('created_at'),
            'updated_at': usuario_data.get('updated_at')
        }
        
    except Exception as e:
        logger.error(f"Error validando credenciales de usuario: {e}")
        return None

def validar_credenciales_saai(usuario, password):
    """
    Valida credenciales de usuario SAAI (plataforma)
    
    Según documento SAAI:
    - Usuarios SAAI son especiales y se manejan en tabla separada
    - Por ahora, usar credenciales hardcodeadas hasta implementar tabla SAAI
    - tenant_id = 'SAAI' para usuarios de plataforma
    
    Args:
        usuario (str): Código de usuario SAAI
        password (str): Contraseña
        
    Returns:
        dict: Información del usuario SAAI si es válido, None si no es válido
    """
    try:
        logger.info(f"Validando credenciales SAAI para usuario: {usuario}")
        
        # Por ahora, credenciales hardcodeadas para usuarios SAAI
        # En producción, esto debería estar en una tabla específica
        usuarios_saai_validos = {
            'SAAI001': {
                'password': hashear_password('admin123'),
                'nombre': 'Administrador SAAI',
                'email': 'admin@saai.com',
                'permisos': ['tiendas:all', 'sistema:admin']
            },
            'SAAI002': {
                'password': hashear_password('support123'),
                'nombre': 'Soporte SAAI',
                'email': 'soporte@saai.com',
                'permisos': ['tiendas:read', 'sistema:support']
            }
        }
        
        usuario_saai = usuarios_saai_validos.get(usuario)
        if not usuario_saai:
            logger.warning(f"Usuario SAAI no encontrado: {usuario}")
            return None
        
        # Validar contraseña
        if not verificar_password(password, usuario_saai['password']):
            logger.warning(f"Contraseña incorrecta para usuario SAAI: {usuario}")
            return None
        
        # Retornar información del usuario SAAI
        return {
            'codigo_usuario': usuario,
            'tenant_id': 'SAAI',  # Tenant especial para plataforma
            'rol': 'SAAI',
            'nombre': usuario_saai['nombre'],
            'email': usuario_saai['email'],
            'estado': 'ACTIVO',
            'permisos': usuario_saai['permisos']
        }
        
    except Exception as e:
        logger.error(f"Error validando credenciales SAAI: {e}")
        return None

def determinar_tipo_usuario(usuario):
    """
    Determina el tipo de usuario basado en el formato del código
    
    Args:
        usuario (str): Código de usuario
        
    Returns:
        str: 'USUARIO' para T###U###, 'SAAI' para SAAI###, None si formato inválido
    """
    try:
        if not usuario:
            return None
        
        # Usuario normal: T###U### (ej: T001U001)
        if validar_formato_codigo_usuario(usuario):
            return 'USUARIO'
        
        # Usuario SAAI: SAAI### (ej: SAAI001)
        if usuario.startswith('SAAI') and len(usuario) >= 7:
            return 'SAAI'
        
        return None
        
    except Exception as e:
        logger.error(f"Error determinando tipo de usuario: {e}")
        return None

def hashear_password(password):
    """
    Hashea una contraseña usando SHA-256 con salt
    
    Args:
        password (str): Contraseña en texto plano
        
    Returns:
        str: Password hasheado
    """
    try:
        # Salt fijo para simplicidad (en producción usar salt aleatorio por usuario)
        salt = "SAAI_SALT_2025"
        password_con_salt = password + salt
        
        # Hash SHA-256
        hash_object = hashlib.sha256(password_con_salt.encode('utf-8'))
        return hash_object.hexdigest()
        
    except Exception as e:
        logger.error(f"Error hasheando password: {e}")
        return None

def verificar_password(password_texto, password_hasheado):
    """
    Verifica si una contraseña coincide con el hash
    
    Args:
        password_texto (str): Contraseña en texto plano
        password_hasheado (str): Hash almacenado
        
    Returns:
        bool: True si coincide, False en caso contrario
    """
    try:
        hash_calculado = hashear_password(password_texto)
        return hash_calculado == password_hasheado
        
    except Exception as e:
        logger.error(f"Error verificando password: {e}")
        return False

def validar_credenciales(usuario, password):
    """
    Función principal para validar credenciales de cualquier tipo de usuario
    
    Args:
        usuario (str): Código de usuario
        password (str): Contraseña
        
    Returns:
        dict: Información del usuario validado o None
    """
    try:
        logger.info(f"Iniciando validación de credenciales para: {usuario}")
        
        # Determinar tipo de usuario
        tipo_usuario = determinar_tipo_usuario(usuario)
        
        if tipo_usuario == 'USUARIO':
            # Usuario normal (TRABAJADOR o ADMIN)
            return validar_credenciales_usuario(usuario, password)
        
        elif tipo_usuario == 'SAAI':
            # Usuario de plataforma SAAI
            return validar_credenciales_saai(usuario, password)
        
        else:
            logger.warning(f"Tipo de usuario no reconocido: {usuario}")
            return None
        
    except Exception as e:
        logger.error(f"Error general validando credenciales: {e}")
        return None

def verificar_tienda_activa(tenant_id):
    """
    Verifica que la tienda esté activa antes de permitir login
    
    Args:
        tenant_id (str): Código de la tienda
        
    Returns:
        bool: True si la tienda está activa
    """
    try:
        if tenant_id == 'SAAI':
            # Los usuarios SAAI siempre pueden acceder
            return True
        
        # Buscar tienda en DynamoDB
        tienda_data = get_item_standard(TIENDAS_TABLE, 'SAAI', tenant_id)
        
        if not tienda_data:
            logger.warning(f"Tienda no encontrada: {tenant_id}")
            return False
        
        estado = tienda_data.get('estado')
        if estado != 'ACTIVO':
            logger.warning(f"Tienda inactiva: {tenant_id}, estado: {estado}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error verificando estado de tienda: {e}")
        return False

def actualizar_ultimo_login(tenant_id, codigo_usuario):
    """
    Actualiza la fecha del último login del usuario
    
    Args:
        tenant_id (str): ID del tenant
        codigo_usuario (str): Código del usuario
    """
    try:
        from utils import update_item_standard, obtener_fecha_hora_peru
        
        if tenant_id != 'SAAI':  # Solo para usuarios normales
            update_item_standard(
                USUARIOS_TABLE, 
                tenant_id, 
                codigo_usuario, 
                {'ultimo_login': obtener_fecha_hora_peru()}
            )
            logger.info(f"Último login actualizado: {codigo_usuario}")
        
    except Exception as e:
        logger.error(f"Error actualizando último login: {e}")