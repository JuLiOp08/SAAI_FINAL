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
    verificar_rol_permitido,
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
            "productos": [
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
        "message": "Monto calculado",
        "data": {
            "items": [
                {
                    "codigo_producto": "P001",
                    "nombre": "Producto 1",
                    "precio_unitario": 50.0,
                    "cantidad": 2,
                    "subtotal": 100.0
                },
                {
                    "codigo_producto": "P002",
                    "nombre": "Producto 2", 
                    "precio_unitario": 25.50,
                    "cantidad": 1,
                    "subtotal": 25.50
                }
            ],
            "total": 125.50
        }
    }
    """
    try:
        log_request(event)
        
        # Verificar rol TRABAJADOR
        tiene_permiso, error = verificar_rol_permitido(event, ['TRABAJADOR'])
        if not tiene_permiso:
            return error
        
        # Extraer tenant_id del JWT
        tenant_id = extract_tenant_from_jwt_claims(event)
        if not tenant_id:
            return error_response("Token inválido - no se encontró codigo_tienda", 401)
        
        # Parse request body
        body = parse_request_body(event)
        if not body:
            return validation_error_response("Request body requerido")
        
        productos = body.get('productos')
        if not productos or not isinstance(productos, list) or len(productos) == 0:
            return validation_error_response("Productos es obligatorio y debe ser una lista no vacía")
        
        # Validar productos y calcular totales
        total_subtotal = Decimal('0.00')
        productos_calculados = []
        
        for item in productos:
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
            producto_data = get_item_standard(PRODUCTOS_TABLE, tenant_id, codigo_producto)
            if not producto_data or producto_data.get('estado') != 'ACTIVO':
                return error_response(f"Producto {codigo_producto} no encontrado o inactivo", 404)
            
            # Verificar stock disponible
            stock_actual = int(producto_data.get('stock', 0))
            if stock_actual < cantidad:
                return error_response(
                    f"Stock insuficiente para producto {codigo_producto}. Disponible: {stock_actual}, Solicitado: {cantidad}",
                    400
                )
            
            precio_unitario = producto_data.get('precio', Decimal('0.00'))
            if isinstance(precio_unitario, (int, float)):
                precio_unitario = Decimal(str(precio_unitario))
            
            # Calcular subtotal del item
            subtotal_item = precio_unitario * Decimal(str(cantidad))
            total_subtotal += subtotal_item
            
            # Agregar producto calculado según SAAI oficial (usa 'items', 'subtotal', 'nombre')
            producto_calculado = {
                'codigo_producto': codigo_producto,
                'nombre': producto_data.get('nombre'),
                'precio_unitario': decimal_to_float(precio_unitario),
                'cantidad': cantidad,
                'subtotal': decimal_to_float(subtotal_item)
            }
            
            productos_calculados.append(producto_calculado)
        
        # Calcular total (sin IGV según documentación oficial SAAI)
        total = total_subtotal
        
        # Preparar response según documentación oficial SAAI
        calculation_data = {
            'items': productos_calculados,
            'total': decimal_to_float(total)
        }
        
        logger.info(f"Calculado monto de venta para {len(productos)} productos en tienda {tenant_id}. Total: {decimal_to_float(total)}")
        
        return success_response(
            mensaje="Monto calculado",
            data=calculation_data
        )
        
    except Exception as e:
        logger.error(f"Error calculando monto de venta: {str(e)}")
        return error_response("Error interno del servidor", 500)