# ventas/calcular_monto.py
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
    get_item_standard,
    decimal_to_float
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

PRODUCTOS_TABLE = os.environ.get('PRODUCTOS_TABLE')

def handler(event, context):
    """
    POST /ventas/calcular - Calcular monto total de venta (NO guarda datos)
    
    Según documento SAAI (TRABAJADOR):
    Request:
    {
        "body": {
            "items": [
                {
                    "codigo_producto": "P001",
                    "cantidad": 2
                },
                {
                    "codigo_producto": "P002", 
                    "cantidad": 1
                }
            ]
        }
    }
    
    Response:
    {
        "success": true,
        "data": {
            "subtotal": 125.50,
            "igv": 22.59,
            "total": 148.09,
            "items": [
                {
                    "codigo_producto": "P001",
                    "nombre_producto": "Producto 1",
                    "precio_unitario": 50.0,
                    "cantidad": 2,
                    "subtotal_item": 100.0
                },
                {
                    "codigo_producto": "P002",
                    "nombre_producto": "Producto 2", 
                    "precio_unitario": 25.50,
                    "cantidad": 1,
                    "subtotal_item": 25.50
                }
            ]
        }
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
        
        items = body.get('items')
        if not items or not isinstance(items, list) or len(items) == 0:
            return validation_error_response("Items es obligatorio y debe ser una lista no vacía")
        
        # Validar items y calcular totales
        total_subtotal = Decimal('0.00')
        items_calculados = []
        
        for item in items:
            codigo_producto = item.get('codigo_producto')
            cantidad = item.get('cantidad')
            
            if not codigo_producto:
                return validation_error_response("codigo_producto es obligatorio en cada item")
            
            try:
                cantidad = int(cantidad)
                if cantidad <= 0:
                    return validation_error_response("La cantidad debe ser mayor a 0")
            except (ValueError, TypeError):
                return validation_error_response("La cantidad debe ser un número entero válido")
            
            # Obtener producto para verificar existencia y precio
            producto = get_item_standard(PRODUCTOS_TABLE, tenant_id, codigo_producto)
            if not producto or producto.get('estado') != 'ACTIVO':
                return error_response(f"Producto {codigo_producto} no encontrado o inactivo", 404)
            
            # Verificar stock disponible
            stock_actual = int(producto.get('stock', 0))
            if stock_actual < cantidad:
                return error_response(
                    f"Stock insuficiente para producto {codigo_producto}. Disponible: {stock_actual}, Solicitado: {cantidad}",
                    400
                )
            
            precio_unitario = producto.get('precio', Decimal('0.00'))
            if isinstance(precio_unitario, (int, float)):
                precio_unitario = Decimal(str(precio_unitario))
            
            # Calcular subtotal del item
            subtotal_item = precio_unitario * Decimal(str(cantidad))
            total_subtotal += subtotal_item
            
            # Agregar item calculado
            item_calculado = {
                'codigo_producto': codigo_producto,
                'nombre_producto': producto.get('nombre'),
                'precio_unitario': decimal_to_float(precio_unitario),
                'cantidad': cantidad,
                'subtotal_item': decimal_to_float(subtotal_item)
            }
            
            items_calculados.append(item_calculado)
        
        # Calcular IGV (18% en Perú)
        igv_rate = Decimal('0.18')
        igv = total_subtotal * igv_rate
        total = total_subtotal + igv
        
        # Preparar response
        calculation_data = {
            'subtotal': decimal_to_float(total_subtotal),
            'igv': decimal_to_float(igv),
            'total': decimal_to_float(total),
            'items': items_calculados
        }
        
        logger.info(f"Calculado monto de venta para {len(items)} items en tienda {tenant_id}. Total: {decimal_to_float(total)}")
        
        return success_response(data=calculation_data)
        
    except Exception as e:
        logger.error(f"Error calculando monto de venta: {str(e)}")
        return error_response("Error interno del servidor", 500)