# gastos/buscar_gasto.py
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

GASTOS_TABLE = os.environ.get('GASTOS_TABLE')

def handler(event, context):
    """
    POST /gastos/buscar - Buscar gastos por criterios
    
    Según documento SAAI (ADMIN):
    Request:
    {
        "body": {
            "criterio": "descripcion",
            "valor": "Pago"
        }
    }
    
    Response:
    {
        "success": true,
        "data": [
            {
                "codigo_gasto": "G001",
                "descripcion": "Pago proveedor",
                "monto": 150.0,
                "categoria": "proveedores",
                "fecha": "2025-11-08"
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
        
        # Obtener todos los gastos activos
        gastos_response = query_by_tenant(
            GASTOS_TABLE,
            tenant_id,
            filter_expression="attribute_exists(#data) AND #data.estado = :estado",
            expression_attribute_names={"#data": "data"},
            expression_attribute_values={":estado": "ACTIVO"}
        )
        
        gastos = gastos_response.get('Items', [])
        
        # Buscar por criterio
        valor_lower = str(valor).lower()
        found_gastos = []
        
        for item in gastos:
            gasto_data = item.get('data', {})
            
            match_found = False
            
            if criterio == 'codigo_gasto':
                if str(gasto_data.get('codigo_gasto', '')).lower() == valor_lower:
                    match_found = True
            elif criterio == 'descripcion':
                if valor_lower in str(gasto_data.get('descripcion', '')).lower():
                    match_found = True
            elif criterio == 'categoria':
                if str(gasto_data.get('categoria', '')).lower() == valor_lower:
                    match_found = True
            elif criterio == 'fecha':
                if str(gasto_data.get('fecha', '')) == str(valor):
                    match_found = True
            elif criterio == 'monto':
                try:
                    monto_buscar = float(valor)
                    monto_gasto = decimal_to_float(gasto_data.get('monto'))
                    if monto_gasto == monto_buscar:
                        match_found = True
                except (ValueError, TypeError):
                    pass
            
            if match_found:
                # Convertir Decimal a float para response
                gasto_response = {
                    'codigo_gasto': gasto_data.get('codigo_gasto'),
                    'descripcion': gasto_data.get('descripcion'),
                    'monto': decimal_to_float(gasto_data.get('monto')),
                    'categoria': gasto_data.get('categoria'),
                    'fecha': gasto_data.get('fecha')
                }
                
                found_gastos.append(gasto_response)
        
        # Ordenar por fecha descendente
        found_gastos.sort(key=lambda x: x.get('fecha', ''), reverse=True)
        
        logger.info(f"Encontrados {len(found_gastos)} gastos para criterio {criterio}={valor} en tienda {tenant_id}")
        
        return success_response(data=found_gastos)
        
    except Exception as e:
        logger.error(f"Error buscando gastos: {str(e)}")
        return error_response("Error interno del servidor", 500)