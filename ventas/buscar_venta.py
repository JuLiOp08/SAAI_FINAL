# ventas/buscar_venta.py
import os
import logging
from decimal import Decimal
from utils import (
    success_response,
    error_response,
    validation_error_response,
    parse_request_body,
    log_request,
    extract_tenant_from_jwt_claims,
    query_by_tenant,
    decimal_to_float
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

VENTAS_TABLE = os.environ.get('VENTAS_TABLE')

def handler(event, context):
    """
    POST /ventas/buscar - Buscar ventas por criterios
    
    Según documento SAAI (TRABAJADOR):
    Request:
    {
        "body": {
            "criterio": "cliente",
            "valor": "Juan"
        }
    }
    
    Response:
    {
        "success": true,
        "data": [
            {
                "codigo_venta": "V001",
                "cliente": "Juan Pérez",
                "total": 148.09,
                "fecha": "2025-11-08",
                "metodo_pago": "efectivo",
                "productos": [
                    {
                        "codigo_producto": "P001",
                        "nombre_producto": "Producto 1",
                        "cantidad": 2,
                        "precio_unitario": 50.0,
                        "subtotal_item": 100.0
                    }
                ]
            }
        ]
    }
    """
    try:
        log_request(event)
        
        # Extraer tenant_id del JWT
        tenant_id = extract_tenant_from_jwt_claims(event)
        if not tenant_id:
            return error_response("Token inválido - no se encontró codigo_tienda", 401)
        
        # Parse request body
        body = parse_request_body(event)
        if not body:
            return validation_error_response("Request body requerido")
        
        criterio = body.get('criterio')
        valor = body.get('valor')
        
        if not criterio or not valor:
            return validation_error_response("Criterio y valor son obligatorios")
        
        # Obtener todas las ventas (query_by_tenant ya filtra INACTIVOS automáticamente)
        ventas_response = query_by_tenant(
            VENTAS_TABLE,
            tenant_id
        )
        
        ventas = ventas_response.get('items', [])
        
        # Buscar por criterio
        valor_lower = str(valor).lower()
        found_ventas = []
        
        for venta_data in ventas:
            # Filtrar solo ventas COMPLETADAS
            if venta_data.get('estado') != 'COMPLETADA':
                continue
            
            match_found = False
            
            if criterio == 'codigo_venta':
                if str(venta_data.get('codigo_venta', '')).lower() == valor_lower:
                    match_found = True
            elif criterio == 'cliente':
                if valor_lower in str(venta_data.get('cliente', '')).lower():
                    match_found = True
            elif criterio == 'fecha':
                if str(venta_data.get('fecha', '')) == str(valor):
                    match_found = True
            elif criterio == 'fecha_rango':
                # Búsqueda por rango de fechas
                if isinstance(valor, dict) and 'desde' in valor and 'hasta' in valor:
                    fecha_venta = str(venta_data.get('fecha', ''))
                    fecha_desde = str(valor['desde'])
                    fecha_hasta = str(valor['hasta'])
                    if fecha_desde <= fecha_venta <= fecha_hasta:
                        match_found = True
            elif criterio == 'metodo_pago':
                if str(venta_data.get('metodo_pago', '')).lower() == valor_lower:
                    match_found = True
            elif criterio == 'total':
                try:
                    total_buscar = float(valor)
                    total_venta = decimal_to_float(venta_data.get('total'))
                    if total_venta == total_buscar:
                        match_found = True
                except (ValueError, TypeError):
                    pass
            elif criterio == 'producto':
                # Buscar por código o nombre de producto en productos
                productos = venta_data.get('productos', [])
                for producto_venta in productos:
                    codigo_prod = str(producto_venta.get('codigo_producto', '')).lower()
                    nombre_prod = str(producto_venta.get('nombre_producto', '')).lower()
                    if valor_lower in codigo_prod or valor_lower in nombre_prod:
                        match_found = True
                        break
            
            if match_found:
                # Convertir Decimal a float para response
                productos_response = []
                for producto_venta in venta_data.get('productos', []):
                    producto_response = {
                        'codigo_producto': producto_venta.get('codigo_producto'),
                        'nombre_producto': producto_venta.get('nombre_producto'),
                        'cantidad': producto_venta.get('cantidad'),
                        'precio_unitario': decimal_to_float(producto_venta.get('precio_unitario')),
                        'subtotal_item': decimal_to_float(producto_venta.get('subtotal_item'))
                    }
                    productos_response.append(producto_response)
                
                venta_response = {
                    'codigo_venta': venta_data.get('codigo_venta'),
                    'cliente': venta_data.get('cliente'),
                    'total': decimal_to_float(venta_data.get('total')),
                    'fecha': venta_data.get('fecha'),
                    'metodo_pago': venta_data.get('metodo_pago'),
                    'productos': productos_response
                }
                
                found_ventas.append(venta_response)
        
        # Ordenar por fecha descendente
        found_ventas.sort(key=lambda x: x.get('fecha', ''), reverse=True)
        
        logger.info(f"Encontradas {len(found_ventas)} ventas para criterio {criterio}={valor} en tienda {tenant_id}")
        
        return success_response(data=found_ventas)
        
    except Exception as e:
        logger.error(f"Error buscando ventas: {str(e)}")
        return error_response("Error interno del servidor", 500)