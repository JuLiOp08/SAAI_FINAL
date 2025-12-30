# utils/datetime_utils.py
from datetime import datetime, timezone, timedelta

# Zona horaria del Perú (UTC-5)
PERU_TIMEZONE = timezone(timedelta(hours=-5))

def obtener_fecha_hora_peru():
    """
    Obtiene la fecha y hora actual en zona horaria de Perú (UTC-5)
    
    Returns:
        str: Fecha y hora en formato ISO 8601 con zona horaria de Perú
    """
    return datetime.now(PERU_TIMEZONE).isoformat()

def obtener_solo_fecha_peru():
    """
    Obtiene solo la fecha actual en zona horaria de Perú
    
    Returns:
        str: Fecha en formato YYYY-MM-DD
    """
    return datetime.now(PERU_TIMEZONE).strftime('%Y-%m-%d')

def obtener_timestamp_peru():
    """
    Obtiene timestamp unix de la fecha/hora actual de Perú
    
    Returns:
        int: Timestamp unix
    """
    return int(datetime.now(PERU_TIMEZONE).timestamp())

def formatear_fecha_legible(fecha_iso):
    """
    Convierte una fecha ISO a formato legible en español
    
    Args:
        fecha_iso (str): Fecha en formato ISO 8601
        
    Returns:
        str: Fecha en formato "DD/MM/YYYY HH:mm"
    """
    try:
        if isinstance(fecha_iso, str):
            fecha = datetime.fromisoformat(fecha_iso.replace('Z', '+00:00'))
        else:
            fecha = fecha_iso
        
        # Convertir a zona horaria de Perú
        fecha_peru = fecha.astimezone(PERU_TIMEZONE)
        return fecha_peru.strftime('%d/%m/%Y %H:%M')
    except Exception:
        return fecha_iso

def es_fecha_valida(fecha_str):
    """
    Valida si una fecha está en formato correcto
    
    Args:
        fecha_str (str): Fecha a validar
        
    Returns:
        bool: True si es válida, False en caso contrario
    """
    try:
        datetime.fromisoformat(fecha_str.replace('Z', '+00:00'))
        return True
    except Exception:
        return False

def obtener_inicio_dia_peru(fecha_iso=None):
    """
    Obtiene el inicio del día (00:00:00) en zona horaria de Perú
    
    Args:
        fecha_iso (str, optional): Fecha específica. Si no se proporciona, usa la fecha actual
        
    Returns:
        str: Fecha y hora de inicio del día en formato ISO
    """
    if fecha_iso:
        fecha = datetime.fromisoformat(fecha_iso.replace('Z', '+00:00'))
        fecha = fecha.astimezone(PERU_TIMEZONE)
    else:
        fecha = datetime.now(PERU_TIMEZONE)
    
    inicio_dia = fecha.replace(hour=0, minute=0, second=0, microsecond=0)
    return inicio_dia.isoformat()

def obtener_fin_dia_peru(fecha_iso=None):
    """
    Obtiene el fin del día (23:59:59) en zona horaria de Perú
    
    Args:
        fecha_iso (str, optional): Fecha específica. Si no se proporciona, usa la fecha actual
        
    Returns:
        str: Fecha y hora de fin del día en formato ISO
    """
    if fecha_iso:
        fecha = datetime.fromisoformat(fecha_iso.replace('Z', '+00:00'))
        fecha = fecha.astimezone(PERU_TIMEZONE)
    else:
        fecha = datetime.now(PERU_TIMEZONE)
    
    fin_dia = fecha.replace(hour=23, minute=59, second=59, microsecond=999999)
    return fin_dia.isoformat()

def calcular_diferencia_dias(fecha1_iso, fecha2_iso):
    """
    Calcula la diferencia en días entre dos fechas
    
    Args:
        fecha1_iso (str): Primera fecha en formato ISO
        fecha2_iso (str): Segunda fecha en formato ISO
        
    Returns:
        int: Diferencia en días (puede ser negativa si fecha1 > fecha2)
    """
    try:
        fecha1 = datetime.fromisoformat(fecha1_iso.replace('Z', '+00:00'))
        fecha2 = datetime.fromisoformat(fecha2_iso.replace('Z', '+00:00'))
        
        diferencia = fecha2.date() - fecha1.date()
        return diferencia.days
    except Exception:
        return 0

def obtener_rango_semana_actual():
    """
    Obtiene el rango de la semana actual (lunes a domingo) en zona horaria de Perú
    
    Returns:
        tuple: (inicio_semana_iso, fin_semana_iso)
    """
    hoy = datetime.now(PERU_TIMEZONE)
    
    # Calcular inicio de semana (lunes)
    dias_desde_lunes = hoy.weekday()
    inicio_semana = hoy - timedelta(days=dias_desde_lunes)
    inicio_semana = inicio_semana.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Calcular fin de semana (domingo)
    fin_semana = inicio_semana + timedelta(days=6)
    fin_semana = fin_semana.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return inicio_semana.isoformat(), fin_semana.isoformat()

def obtener_rango_mes_actual():
    """
    Obtiene el rango del mes actual en zona horaria de Perú
    
    Returns:
        tuple: (inicio_mes_iso, fin_mes_iso)
    """
    hoy = datetime.now(PERU_TIMEZONE)
    
    # Primer día del mes
    inicio_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Último día del mes
    if hoy.month == 12:
        siguiente_mes = hoy.replace(year=hoy.year + 1, month=1, day=1)
    else:
        siguiente_mes = hoy.replace(month=hoy.month + 1, day=1)
    
    fin_mes = siguiente_mes - timedelta(days=1)
    fin_mes = fin_mes.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return inicio_mes.isoformat(), fin_mes.isoformat()

def validar_formato_fecha(fecha_str, formato='%Y-%m-%d'):
    """
    Valida si una fecha cumple con un formato específico
    
    Args:
        fecha_str (str): Fecha a validar
        formato (str): Formato esperado (por defecto '%Y-%m-%d')
        
    Returns:
        bool: True si cumple el formato, False en caso contrario
    """
    try:
        datetime.strptime(fecha_str, formato)
        return True
    except ValueError:
        return False