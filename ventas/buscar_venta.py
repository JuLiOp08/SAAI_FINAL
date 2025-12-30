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
                "items": [
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
        
        # Obtener todas las ventas completadas
        ventas_response = query_by_tenant(
            VENTAS_TABLE,
            tenant_id,
            filter_expression="attribute_exists(#data) AND #data.estado = :estado",
            expression_attribute_names={"#data": "data"},
            expression_attribute_values={":estado": "COMPLETADA"}
        )
        
        ventas = ventas_response.get('Items', [])
        
        # Buscar por criterio
        valor_lower = str(valor).lower()
        found_ventas = []
        
        for item in ventas:
            venta_data = item.get('data', {})
            
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
                # Buscar por código o nombre de producto en items
                items = venta_data.get('items', [])
                for item_venta in items:
                    codigo_prod = str(item_venta.get('codigo_producto', '')).lower()
                    nombre_prod = str(item_venta.get('nombre_producto', '')).lower()
                    if valor_lower in codigo_prod or valor_lower in nombre_prod:
                        match_found = True
                        break
            
            if match_found:
                # Convertir Decimal a float para response
                items_response = []
                for item_venta in venta_data.get('items', []):
                    item_response = {
                        'codigo_producto': item_venta.get('codigo_producto'),
                        'nombre_producto': item_venta.get('nombre_producto'),
                        'cantidad': item_venta.get('cantidad'),
                        'precio_unitario': decimal_to_float(item_venta.get('precio_unitario')),
                        'subtotal_item': decimal_to_float(item_venta.get('subtotal_item'))
                    }
                    items_response.append(item_response)
                
                venta_response = {
                    'codigo_venta': venta_data.get('codigo_venta'),
                    'cliente': venta_data.get('cliente'),
                    'total': decimal_to_float(venta_data.get('total')),
                    'fecha': venta_data.get('fecha'),
                    'metodo_pago': venta_data.get('metodo_pago'),
                    'items': items_response
                }
                
                found_ventas.append(venta_response)
        
        # Ordenar por fecha descendente
        found_ventas.sort(key=lambda x: x.get('fecha', ''), reverse=True)
        
        logger.info(f"Encontradas {len(found_ventas)} ventas para criterio {criterio}={valor} en tienda {tenant_id}")
        
        return success_response(data=found_ventas)
        
    except Exception as e:
        logger.error(f"Error buscando ventas: {str(e)}")
        return error_response("Error interno del servidor", 500)