# utils/code_generator.py
import random
import string
from datetime import datetime
from .datetime_utils import obtener_fecha_hora_peru

def generar_codigo_tienda():
    """
    Genera un código único para tienda en formato T### (T001, T002, etc.)
    
    Returns:
        str: Código de tienda generado
    """
    from .dynamodb_utils import increment_counter
    import os
    
    try:
        # Usar tabla de contadores SAAI para generar código secuencial
        counters_table = os.environ.get('COUNTERS_TABLE')
        if counters_table:
            siguiente_numero = increment_counter(counters_table, 'SAAI', 'TIENDAS')
            if siguiente_numero:
                return f"T{siguiente_numero:03d}"
        
        # Fallback si no hay tabla configurada (desarrollo)
        numero = random.randint(1, 999)
        return f"T{numero:03d}"
        
    except Exception as e:
        # Fallback en caso de error
        numero = random.randint(1, 999)
        return f"T{numero:03d}"

def generar_codigo_usuario(codigo_tienda):
    """
    Genera un código único para usuario en formato {codigo_tienda}U### (T001U001, T002U015, etc.)
    
    Args:
        codigo_tienda (str): Código de la tienda
        
    Returns:
        str: Código de usuario generado
    """
    from .dynamodb_utils import increment_counter
    import os
    
    try:
        # Usar tabla de contadores por tienda para código secuencial
        counters_table = os.environ.get('COUNTERS_TABLE')
        if counters_table:
            siguiente_numero = increment_counter(counters_table, codigo_tienda, 'USUARIOS')
            if siguiente_numero:
                return f"{codigo_tienda}U{siguiente_numero:03d}"
        
        # Fallback si no hay tabla configurada
        numero = random.randint(1, 999)
        return f"{codigo_tienda}U{numero:03d}"
        
    except Exception as e:
        # Fallback en caso de error
        numero = random.randint(1, 999)
        return f"{codigo_tienda}U{numero:03d}"

def generar_codigo_producto(codigo_tienda):
    """
    Genera un código único para producto en formato {codigo_tienda}P### (T001P001, T002P050, etc.)
    
    Args:
        codigo_tienda (str): Código de la tienda
        
    Returns:
        str: Código de producto generado
    """
    from .dynamodb_utils import increment_counter
    import os
    
    try:
        counters_table = os.environ.get('COUNTERS_TABLE')
        if counters_table:
            siguiente_numero = increment_counter(counters_table, codigo_tienda, 'PRODUCTOS')
            if siguiente_numero:
                return f"{codigo_tienda}P{siguiente_numero:03d}"
        
        # Fallback
        numero = random.randint(1, 999)
        return f"{codigo_tienda}P{numero:03d}"
        
    except Exception as e:
        numero = random.randint(1, 999)
        return f"{codigo_tienda}P{numero:03d}"

def generar_codigo_venta(codigo_tienda):
    """
    Genera un código único para venta en formato {codigo_tienda}V### (T001V001, T002V025, etc.)
    
    Args:
        codigo_tienda (str): Código de la tienda
        
    Returns:
        str: Código de venta generado
    """
    from .dynamodb_utils import increment_counter
    import os
    
    try:
        counters_table = os.environ.get('COUNTERS_TABLE')
        if counters_table:
            siguiente_numero = increment_counter(counters_table, codigo_tienda, 'VENTAS')
            if siguiente_numero:
                return f"{codigo_tienda}V{siguiente_numero:03d}"
        
        # Fallback
        numero = random.randint(1, 999)
        return f"{codigo_tienda}V{numero:03d}"
        
    except Exception as e:
        numero = random.randint(1, 999)
        return f"{codigo_tienda}V{numero:03d}"

def generar_codigo_gasto(codigo_tienda):
    """
    Genera un código único para gasto en formato {codigo_tienda}G### (T001G001, T002G010, etc.)
    
    Args:
        codigo_tienda (str): Código de la tienda
        
    Returns:
        str: Código de gasto generado
    """
    from .dynamodb_utils import increment_counter
    import os
    
    try:
        counters_table = os.environ.get('COUNTERS_TABLE')
        if counters_table:
            siguiente_numero = increment_counter(counters_table, codigo_tienda, 'GASTOS')
            if siguiente_numero:
                return f"{codigo_tienda}G{siguiente_numero:03d}"
        
        # Fallback
        numero = random.randint(1, 999)
        return f"{codigo_tienda}G{numero:03d}"
        
    except Exception as e:
        numero = random.randint(1, 999)
        return f"{codigo_tienda}G{numero:03d}"

def generar_codigo_reporte(codigo_tienda, tipo_reporte):
    """
    Genera un código único para reporte en formato {codigo_tienda}R{tipo}{timestamp}
    Ejemplos: T001RINV20250115143022, T002RVEN20250115143022
    
    Args:
        codigo_tienda (str): Código de la tienda
        tipo_reporte (str): Tipo de reporte (INV, VEN, GAS, GEN)
        
    Returns:
        str: Código de reporte generado
    """
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return f"{codigo_tienda}R{tipo_reporte}{timestamp}"

def generar_codigo_notificacion(codigo_tienda):
    """
    Genera un código único para notificación en formato {codigo_tienda}N###
    
    Args:
        codigo_tienda (str): Código de la tienda
        
    Returns:
        str: Código de notificación generado
    """
    try:
        # Usar contador incremental para consistencia con el patrón del proyecto
        contador = increment_counter('SAAI_Counters', codigo_tienda, 'NOTIFICACIONES')
        if contador:
            return f"{codigo_tienda}N{contador:03d}"
        else:
            # Fallback a timestamp si no hay contador disponible
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            return f"{codigo_tienda}N{timestamp}"
    except Exception:
        # Fallback a timestamp en caso de error
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f"{codigo_tienda}N{timestamp}"

def generar_codigo_analitica(codigo_tienda):
    """
    Genera un código único para registro de analítica en formato {codigo_tienda}A{fecha}
    Ejemplo: T001A20250115
    
    Args:
        codigo_tienda (str): Código de la tienda
        
    Returns:
        str: Código de analítica generado
    """
    fecha = datetime.now().strftime('%Y%m%d')
    return f"{codigo_tienda}A{fecha}"

def generar_codigo_prediccion(codigo_tienda, codigo_producto):
    """
    Genera un código único para predicción de demanda
    Formato: {codigo_tienda}PRED{codigo_producto}{timestamp}
    
    Args:
        codigo_tienda (str): Código de la tienda
        codigo_producto (str): Código del producto
        
    Returns:
        str: Código de predicción generado
    """
    timestamp = datetime.now().strftime('%Y%m%d')
    return f"{codigo_tienda}PRED{codigo_producto}{timestamp}"

def generar_password_temporal():
    """
    Genera una contraseña temporal para nuevos usuarios
    
    Returns:
        str: Contraseña temporal de 8 caracteres
    """
    # Combinar letras mayúsculas, minúsculas y números
    caracteres = string.ascii_letters + string.digits
    password = ''.join(random.choice(caracteres) for _ in range(8))
    return password

def generar_token_recuperacion():
    """
    Genera un token para recuperación de contraseña
    
    Returns:
        str: Token de recuperación de 16 caracteres
    """
    caracteres = string.ascii_uppercase + string.digits
    token = ''.join(random.choice(caracteres) for _ in range(16))
    return token

def validar_formato_codigo_tienda(codigo):
    """
    Valida si un código de tienda tiene el formato correcto T###
    
    Args:
        codigo (str): Código a validar
        
    Returns:
        bool: True si es válido, False en caso contrario
    """
    if not codigo or len(codigo) != 4:
        return False
    
    if not codigo.startswith('T'):
        return False
    
    try:
        numero = int(codigo[1:])
        return 1 <= numero <= 999
    except ValueError:
        return False

def validar_formato_codigo_usuario(codigo, codigo_tienda=None):
    """
    Valida si un código de usuario tiene el formato correcto {tienda}U###
    
    Args:
        codigo (str): Código a validar
        codigo_tienda (str, optional): Código de tienda esperado
        
    Returns:
        bool: True si es válido, False en caso contrario
    """
    if not codigo or len(codigo) != 8:
        return False
    
    if not codigo.endswith('U') and 'U' not in codigo:
        return False
    
    try:
        # Dividir en partes: tienda + U + numero
        if 'U' in codigo:
            parts = codigo.split('U')
            if len(parts) != 2:
                return False
            
            tienda_part = parts[0]
            numero_part = parts[1]
            
            # Validar código de tienda
            if not validar_formato_codigo_tienda(tienda_part):
                return False
            
            # Validar número de usuario
            numero = int(numero_part)
            if not (1 <= numero <= 999):
                return False
            
            # Validar tienda específica si se proporciona
            if codigo_tienda and tienda_part != codigo_tienda:
                return False
            
            return True
    except (ValueError, IndexError):
        return False
    
    return False

def extraer_codigo_tienda_de_entidad(codigo_entidad):
    """
    Extrae el código de tienda de un código de entidad (usuario, producto, venta, etc.)
    
    Args:
        codigo_entidad (str): Código de entidad (ej: T001U005, T002P010)
        
    Returns:
        str: Código de tienda o None si no es válido
    """
    if not codigo_entidad or len(codigo_entidad) < 4:
        return None
    
    codigo_tienda = codigo_entidad[:4]  # Primeros 4 caracteres
    
    if validar_formato_codigo_tienda(codigo_tienda):
        return codigo_tienda
    
    return None

def generar_codigo_siguiente(contador_actual, prefijo, codigo_tienda=""):
    """
    Genera el siguiente código basado en un contador
    
    Args:
        contador_actual (int): Valor actual del contador
        prefijo (str): Prefijo del código (U, P, V, G, etc.)
        codigo_tienda (str): Código de tienda (si aplica)
        
    Returns:
        str: Siguiente código generado
    """
    siguiente_numero = contador_actual + 1
    
    if codigo_tienda:
        return f"{codigo_tienda}{prefijo}{siguiente_numero:03d}"
    else:
        # Para tiendas
        return f"T{siguiente_numero:03d}"