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
        password_hash = usuario_data.get('password') or usuario_data.get('password_hash')
        salt = usuario_data.get('salt')
        
        if not password_hash:
            logger.error(f"Usuario sin contraseña configurada: {usuario}")
            return None
        
        if not salt:
            logger.error(f"Usuario sin salt configurado: {usuario}")
            return None
        
        if not verificar_password(password, password_hash, salt):
            logger.warning(f"Contraseña incorrecta para usuario: {usuario}")
            return None
        
        # Verificar que tenga rol válido
        rol = usuario_data.get('rol') or usuario_data.get('role')
        if rol not in ['TRABAJADOR', 'ADMIN', 'worker', 'admin']:
            logger.error(f"Rol inválido para usuario: {usuario}, rol: {rol}")
            return None
        
        # Normalizar rol a mayúscula para consistencia
        rol_normalizado = rol.upper() if rol in ['worker', 'admin'] else rol
        if rol_normalizado == 'WORKER':
            rol_normalizado = 'TRABAJADOR'
        
        # Retornar información del usuario validado
        return {
            'codigo_usuario': usuario,
            'tenant_id': tenant_id,
            'rol': rol_normalizado,
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

def buscar_y_validar_credenciales_por_email(email, password):
    """
    Busca un usuario por email en TODAS las tiendas y valida sus credenciales
    
    Args:
        email (str): Email del usuario
        password (str): Contraseña en texto plano
        
    Returns:
        dict: Información del usuario si es válido, None si no es válido
    """
    try:
        logger.info(f"Buscando usuario por email en todas las tiendas: {email}")
        
        # CASO ESPECIAL: Usuario SAAI (super admin de la plataforma)
        # El usuario SAAI no es una tienda, está en tenant_id="SAAI"
        if email.lower() == 'saai@saai.com':
            logger.info("Detectado login de usuario SAAI (super admin)")
            return validar_credenciales_por_email('SAAI', email, password)
        
        # FLUJO NORMAL: Buscar en tiendas registradas
        # Primero obtener lista de todas las tiendas usando utils centralizadas
        from utils import query_by_tenant
        
        # Query tiendas activas desde tabla t_tiendas 
        tiendas_result = query_by_tenant(TIENDAS_TABLE, 'SAAI')  # Las tiendas están bajo tenant SAAI
        
        for tienda in tiendas_result.get('items', []):
            tenant_id = tienda.get('codigo_tienda') or tienda.get('_entity_id')
            if not tenant_id:
                continue
                
            # Buscar usuario por email en esta tienda
            usuario_data = buscar_usuario_por_email(tenant_id, email)
            
            if usuario_data:
                # Encontramos el usuario, ahora validar credenciales
                logger.info(f"Usuario encontrado en tienda {tenant_id}")
                
                # Usar la función existente de validación
                return validar_credenciales_por_email(tenant_id, email, password)
        
        logger.warning(f"Usuario no encontrado en ninguna tienda con email: {email}")
        return None
        
    except Exception as e:
        logger.error(f"Error buscando usuario por email en todas las tiendas: {e}")
        return None

def buscar_usuario_por_email(tenant_id, email):
    """
    Busca un usuario por email en un tenant específico
    
    Args:
        tenant_id (str): ID del tenant (codigo_tienda)  
        email (str): Email a buscar
        
    Returns:
        dict: Datos del usuario si lo encuentra, None si no existe
    """
    try:
        logger.info(f"Buscando usuario por email en tenant {tenant_id}: {email}")
        
        # Query todos los usuarios del tenant usando utils centralizadas
        from utils import query_by_tenant
        resultado = query_by_tenant(USUARIOS_TABLE, tenant_id)
        
        # Filtrar por email
        for usuario in resultado.get('items', []):
            if usuario.get('email') and usuario['email'].lower() == email.lower():
                logger.info(f"Usuario encontrado por email: {usuario.get('codigo_usuario')}")
                return usuario
        
        logger.warning(f"Usuario no encontrado con email: {email}")
        return None
        
    except Exception as e:
        logger.error(f"Error buscando usuario por email: {e}")
        return None

def validar_credenciales_por_email(tenant_id, email, password):
    """
    Valida credenciales usando email en lugar de código de usuario
    
    Args:
        tenant_id (str): ID del tenant (código de tienda)
        email (str): Email del usuario
        password (str): Contraseña en texto plano
        
    Returns:
        dict: Información del usuario si es válido, None si no es válido
    """
    try:
        logger.info(f"Validando credenciales por email: {email}")
        
        # Validar formato del código de tienda
        if not validar_formato_codigo_tienda(tenant_id):
            logger.warning(f"Código de tienda inválido: {tenant_id}")
            return None
        
        # Buscar usuario por email
        usuario_data = buscar_usuario_por_email(tenant_id, email)
        
        if not usuario_data:
            logger.warning(f"Usuario no encontrado con email: {email}")
            return None
        
        # Verificar estado activo
        if usuario_data.get('estado') != 'ACTIVO':
            logger.warning(f"Usuario inactivo: {email}")
            return None
        
        # Validar contraseña
        password_hash = usuario_data.get('password') or usuario_data.get('password_hash')
        salt = usuario_data.get('salt')
        
        if not password_hash:
            logger.error(f"Usuario sin contraseña configurada: {email}")
            return None
        
        if not salt:
            logger.error(f"Usuario sin salt configurado: {email}")
            return None
        
        if not verificar_password(password, password_hash, salt):
            logger.warning(f"Contraseña incorrecta para usuario: {email}")
            return None
        
        # Verificar que tenga rol válido
        # Permitir: TRABAJADOR, ADMIN, saai (super admin)
        rol = usuario_data.get('rol') or usuario_data.get('role')  # Compatibilidad con ambos nombres
        if rol not in ['TRABAJADOR', 'ADMIN', 'saai', 'worker', 'admin', 'SAAI']:
            logger.error(f"Rol inválido para usuario: {email}, rol: {rol}")
            return None
        
        # Normalizar rol a mayúscula para consistencia
        rol_normalizado = rol.upper() if rol in ['saai', 'worker', 'admin'] else rol
        if rol_normalizado == 'WORKER':
            rol_normalizado = 'TRABAJADOR'
        
        # Extraer código_usuario de la entity_id
        codigo_usuario = usuario_data.get('codigo_usuario') or usuario_data.get('_entity_id')
        
        # Retornar información del usuario validado
        return {
            'codigo_usuario': codigo_usuario,
            'tenant_id': tenant_id,
            'rol': rol_normalizado,
            'nombre': usuario_data.get('nombre', ''),
            'email': usuario_data.get('email', ''),
            'estado': usuario_data.get('estado'),
            'telefono': usuario_data.get('telefono', ''),
            'ultimo_login': usuario_data.get('ultimo_login'),
            'created_at': usuario_data.get('created_at'),
            'updated_at': usuario_data.get('updated_at')
        }
        
    except Exception as e:
        logger.error(f"Error validando credenciales por email: {e}")
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
        
        # Buscar usuario SAAI en tabla usando utils centralizadas
        usuario_data = get_item_standard(USUARIOS_TABLE, 'SAAI', usuario)
        
        if not usuario_data:
            logger.warning(f"Usuario SAAI no encontrado: {usuario}")
            return None
        
        # Verificar estado activo
        if usuario_data.get('estado') != 'ACTIVO':
            logger.warning(f"Usuario SAAI inactivo: {usuario}")
            return None
        
        # Validar contraseña usando función centralizada
        password_hasheado = usuario_data.get('password')
        if not password_hasheado:
            logger.error(f"Usuario SAAI sin contraseña configurada: {usuario}")
            return None
        
        if not verificar_password(password, password_hasheado):
            logger.warning(f"Contraseña incorrecta para usuario SAAI: {usuario}")
            return None
        
        # Retornar información del usuario SAAI usando datos de BD
        return {
            'codigo_usuario': usuario,
            'tenant_id': 'SAAI',  # Tenant especial para plataforma
            'rol': 'SAAI',
            'nombre': usuario_data.get('nombre', ''),
            'email': usuario_data.get('email', ''),
            'estado': usuario_data.get('estado'),
            'permisos': usuario_data.get('permisos', [])
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
    Hashea una contraseña usando PBKDF2-HMAC-SHA256 con salt aleatorio
    
    Args:
        password (str): Contraseña en texto plano
        
    Returns:
        tuple: (password_hash_hex, salt_hex)
    """
    try:
        # Generar salt aleatorio de 32 bytes
        salt = os.urandom(32)
        
        # Hash PBKDF2 con 100,000 iteraciones
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        
        return password_hash.hex(), salt.hex()
        
    except Exception as e:
        logger.error(f"Error hasheando password: {e}")
        return None, None

def verificar_password(password_texto, password_hash_hex, salt_hex):
    """
    Verifica si una contraseña coincide con el hash usando PBKDF2
    
    Args:
        password_texto (str): Contraseña en texto plano
        password_hash_hex (str): Hash almacenado en formato hex
        salt_hex (str): Salt almacenado en formato hex
        
    Returns:
        bool: True si coincide, False en caso contrario
    """
    try:
        # Convertir salt de hex a bytes
        salt = bytes.fromhex(salt_hex)
        
        # Calcular hash con el mismo salt
        hash_calculado = hashlib.pbkdf2_hmac('sha256', password_texto.encode(), salt, 100000)
        
        # Comparar hashes
        return hash_calculado.hex() == password_hash_hex
        
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
        if estado != 'ACTIVO' and estado != 'ACTIVA':
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
        from utils import get_item_standard, put_item_standard, obtener_fecha_hora_peru
        
        if tenant_id != 'SAAI':  # Solo para usuarios normales
            # Obtener datos actuales del usuario
            usuario_actual = get_item_standard(USUARIOS_TABLE, tenant_id, codigo_usuario)
            if usuario_actual:
                # Actualizar último login usando put_item_standard (sobrescribir)
                usuario_actual['ultimo_login'] = obtener_fecha_hora_peru()
                put_item_standard(USUARIOS_TABLE, tenant_id, codigo_usuario, usuario_actual)
                logger.info(f"Último login actualizado: {codigo_usuario}")
        
    except Exception as e:
        logger.error(f"Error actualizando último login: {e}")