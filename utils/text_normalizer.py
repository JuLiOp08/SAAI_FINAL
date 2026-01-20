# utils/text_normalizer.py
import unicodedata


def normalizar_texto(texto):
    """
    Elimina tildes y caracteres especiales de un string.
    Útil para generar CSVs compatibles con Excel.
    
    Ejemplos:
        "Categoría" -> "Categoria"
        "Descripción" -> "Descripcion"
        "Código" -> "Codigo"
        "José García" -> "Jose Garcia"
    
    Args:
        texto (str): Texto a normalizar
        
    Returns:
        str: Texto sin tildes ni caracteres especiales
    """
    if not isinstance(texto, str):
        return str(texto) if texto is not None else ''
    
    # Normalizar usando NFD (descompone caracteres acentuados)
    # luego filtra solo caracteres ASCII
    texto_normalizado = unicodedata.normalize('NFD', texto)
    texto_sin_tildes = ''.join(
        char for char in texto_normalizado
        if unicodedata.category(char) != 'Mn'  # Mn = Marca no espaciadora (tildes)
    )
    
    return texto_sin_tildes


def normalizar_dict_keys(data_dict):
    """
    Normaliza las claves de un diccionario (elimina tildes).
    
    Args:
        data_dict (dict): Diccionario con claves que pueden tener tildes
        
    Returns:
        dict: Nuevo diccionario con claves normalizadas
    """
    if not isinstance(data_dict, dict):
        return data_dict
    
    return {
        normalizar_texto(key): value
        for key, value in data_dict.items()
    }


def normalizar_dict_values(data_dict, keys_to_normalize=None):
    """
    Normaliza los valores de texto de un diccionario (elimina tildes).
    
    Args:
        data_dict (dict): Diccionario con valores que pueden tener tildes
        keys_to_normalize (list): Lista de claves cuyos valores normalizar.
                                  Si es None, normaliza todos los valores de tipo str.
        
    Returns:
        dict: Nuevo diccionario con valores normalizados
    """
    if not isinstance(data_dict, dict):
        return data_dict
    
    resultado = {}
    for key, value in data_dict.items():
        # Si se especificaron claves específicas, solo normalizar esas
        if keys_to_normalize and key not in keys_to_normalize:
            resultado[key] = value
        # Si el valor es string, normalizar
        elif isinstance(value, str):
            resultado[key] = normalizar_texto(value)
        else:
            resultado[key] = value
    
    return resultado


def normalizar_lista_dicts(lista_dicts, normalizar_keys=True, normalizar_values=True, values_keys=None):
    """
    Normaliza una lista de diccionarios (claves y/o valores).
    
    Args:
        lista_dicts (list): Lista de diccionarios
        normalizar_keys (bool): Si True, normaliza las claves
        normalizar_values (bool): Si True, normaliza los valores de texto
        values_keys (list): Claves específicas cuyos valores normalizar (si None, normaliza todos)
        
    Returns:
        list: Nueva lista con diccionarios normalizados
    """
    if not isinstance(lista_dicts, list):
        return lista_dicts
    
    resultado = []
    for item in lista_dicts:
        if not isinstance(item, dict):
            resultado.append(item)
            continue
        
        nuevo_item = item.copy()
        
        # Normalizar valores primero (antes de cambiar las claves)
        if normalizar_values:
            nuevo_item = normalizar_dict_values(nuevo_item, values_keys)
        
        # Normalizar claves
        if normalizar_keys:
            nuevo_item = normalizar_dict_keys(nuevo_item)
        
        resultado.append(nuevo_item)
    
    return resultado
