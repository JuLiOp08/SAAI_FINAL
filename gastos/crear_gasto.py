# gastos/crear_gasto.py
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
    extract_user_from_jwt_claims,
    put_item_standard,
    generar_codigo_gasto,
    obtener_fecha_hora_peru
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Tablas DynamoDB
GASTOS_TABLE = os.environ.get('GASTOS_TABLE')
COUNTERS_TABLE = os.environ.get('COUNTERS_TABLE')

def handler(event, context):
    """
    POST /gastos - Crear nuevo gasto
    
    Según documento SAAI (ADMIN):
    Request:
    {
        "body": {
            "descripcion": "Pago proveedor",
            "monto": 150.0,
            "categoria": "proveedores",
            "fecha": "2025-11-08"
        }
    }
    
    Response:
    {
        "success": true,
        "message": "Gasto registrado",
        "data": {
            "codigo_gasto": "T002G001"
        }
    }
    """
    try:
        log_request(event)
        
        # Extraer tenant_id del JWT
        tenant_id = extract_tenant_from_jwt_claims(event)
        if not tenant_id:
            return error_response("Token inválido - no se encontró codigo_tienda", 401)
        
        # Extraer usuario para auditoría
        user_data = extract_user_from_jwt_claims(event)
        codigo_usuario = user_data.get('codigo_usuario') if user_data else None
        
        # Parse request body
        body = parse_request_body(event)
        if not body:
            return validation_error_response("Request body requerido")
        
        # Validar campos obligatorios
        required_fields = ['descripcion', 'monto', 'categoria', 'fecha']
        for field in required_fields:
            if not body.get(field):
                return validation_error_response(f"Campo {field} es obligatorio")
        
        # Validar tipos de datos
        try:
            monto = float(body['monto'])
            if monto <= 0:
                return validation_error_response("El monto debe ser mayor a 0")
        except (ValueError, TypeError):
            return validation_error_response("Monto debe ser un número válido")
        
        # Generar código de gasto usando utils
        codigo_gasto = generar_codigo_gasto(tenant_id)
        
        # Crear entidad gasto
        fecha_actual = obtener_fecha_hora_peru()
        
        gasto_data = {
            'codigo_gasto': codigo_gasto,
            'descripcion': str(body['descripcion']).strip(),
            'monto': Decimal(str(monto)),
            'categoria': str(body['categoria']).strip(),
            'fecha': str(body['fecha']).strip(),
            'estado': 'ACTIVO',
            'created_at': fecha_actual,
            'updated_at': fecha_actual
        }
        
        # Agregar auditoría si hay usuario
        if codigo_usuario:
            gasto_data['codigo_usuario'] = codigo_usuario
            gasto_data['created_by'] = codigo_usuario
        
        # Guardar en DynamoDB
        put_item_standard(
            GASTOS_TABLE,
            tenant_id=tenant_id,
            entity_id=codigo_gasto,
            data=gasto_data
        )
        
        logger.info(f"Gasto creado: {codigo_gasto} en tienda {tenant_id}")
        
        return success_response(
            message="Gasto registrado",
            data={"codigo_gasto": codigo_gasto}
        )
        
    except Exception as e:
        logger.error(f"Error creando gasto: {str(e)}")
        return error_response("Error interno del servidor", 500)