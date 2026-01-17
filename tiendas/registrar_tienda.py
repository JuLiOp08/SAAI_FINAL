# tiendas/registrar_tienda.py
import os
import json
import hashlib
import logging
import boto3
from utils import (
    success_response,
    error_response,
    validation_error_response,
    parse_request_body,
    log_request,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims,
    put_item_standard,
    generar_codigo_tienda,
    generar_codigo_usuario,
    obtener_fecha_hora_peru
)
from constants import ROLE_MAPPING_REVERSE, ESTADO_ACTIVO, ESTADO_TIENDA_ACTIVA

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Servicios AWS
sns_client = boto3.client('sns')

# Tablas DynamoDB
TIENDAS_TABLE = os.environ.get('TIENDAS_TABLE')
USUARIOS_TABLE = os.environ.get('USUARIOS_TABLE')
COUNTERS_TABLE = os.environ.get('COUNTERS_TABLE')

# Topics SNS
BIENVENIDA_SAAI_TOPIC = os.environ.get('BIENVENIDA_SNS_TOPIC_ARN')

def handler(event, context):
    """
    POST /tiendas - Registrar nueva tienda + admin inicial
    
    Según documento SAAI (SAAI):
    Request:
    {
        "body": {
            "nombre_tienda": "Bodega San Juan",
            "email_tienda": "bodega@correo.com",
            "telefono": "999888777",
            "admin": {
                "nombre": "Juan Perez",
                "email": "admin@bodega.com",
                "password": "123456"
            }
        }
    }
    
    Response:
    {
        "success": true,
        "message": "Tienda registrada correctamente",
        "data": {
            "codigo_tienda": "T002",
            "codigo_usuario_admin": "A001",
            "estado": "ACTIVA"
        }
    }
    """
    try:
        log_request(event)
        
        # Validar que el usuario sea SAAI
        user_info = extract_user_from_jwt_claims(event)
        if not user_info or user_info.get('rol', '').upper() != 'SAAI':
            return error_response("Solo usuarios SAAI pueden registrar tiendas", 403)
        
        # Parse request body
        body = parse_request_body(event)
        if not body:
            return validation_error_response("Request body requerido")
        
        # Validar campos obligatorios
        required_fields = ['nombre_tienda', 'email_tienda', 'telefono', 'admin']
        for field in required_fields:
            if not body.get(field):
                return validation_error_response(f"Campo {field} es obligatorio")
        
        admin_data = body.get('admin')
        if not isinstance(admin_data, dict):
            return validation_error_response("Campo admin debe ser un objeto")
        
        admin_required = ['nombre', 'email', 'password']
        for field in admin_required:
            if not admin_data.get(field):
                return validation_error_response(f"Campo admin.{field} es obligatorio")
        
        # Generar código de tienda usando utils
        codigo_tienda = generar_codigo_tienda()
        
        # Crear tienda
        fecha_actual = obtener_fecha_hora_peru()
        
        tienda_data = {
            'codigo_tienda': codigo_tienda,
            'nombre_tienda': str(body['nombre_tienda']).strip(),
            'email_tienda': str(body['email_tienda']).strip().lower(),
            'telefono': str(body['telefono']).strip(),
            'estado': ESTADO_TIENDA_ACTIVA,
            'created_at': fecha_actual,
            'updated_at': fecha_actual
        }
        
        # Guardar tienda en DynamoDB
        put_item_standard(
            TIENDAS_TABLE,
            tenant_id="SAAI",
            entity_id=codigo_tienda,
            data=tienda_data
        )
        
        # Crear usuario admin de la tienda
        codigo_usuario_admin = generar_codigo_usuario(codigo_tienda)
        
        # Hash de la password con salt
        salt = os.urandom(32)
        password_hash = hashlib.pbkdf2_hmac('sha256', admin_data['password'].encode(), salt, 100000)
        
        admin_usuario_data = {
            'codigo_usuario': codigo_usuario_admin,
            'nombre': str(admin_data['nombre']).strip(),
            'email': str(admin_data['email']).strip().lower(),
            'role': ROLE_MAPPING_REVERSE['admin'],
            'password_hash': password_hash.hex(),
            'salt': salt.hex(),
            'estado': ESTADO_ACTIVO,
            'created_at': fecha_actual,
            'updated_at': fecha_actual
        }
        
        # Guardar admin en DynamoDB
        put_item_standard(
            USUARIOS_TABLE,
            tenant_id=codigo_tienda,
            entity_id=codigo_usuario_admin,
            data=admin_usuario_data
        )
        
        # Publicar evento de bienvenida en SNS BienvenidaSAAI
        try:
            mensaje_bienvenida = {
                'tenant_id': codigo_tienda,
                'correo_admin': admin_data['email'],
                'nombre_tienda': body['nombre_tienda'],
                'ts': fecha_actual
            }
            
            sns_client.publish(
                TopicArn=BIENVENIDA_SAAI_TOPIC,
                Message=json.dumps(mensaje_bienvenida),
                MessageAttributes={
                    'tenant_id': {'DataType': 'String', 'StringValue': codigo_tienda},
                    'ts': {'DataType': 'String', 'StringValue': fecha_actual}
                }
            )
            logger.info(f"Evento bienvenida enviado para tienda {codigo_tienda}")
        except Exception as sns_error:
            logger.warning(f"Error enviando evento bienvenida: {sns_error}")
        
        logger.info(f"Tienda registrada: {codigo_tienda} con admin {codigo_usuario_admin}")
        
        return success_response(
            message="Tienda registrada correctamente",
            data={
                "codigo_tienda": codigo_tienda,
                "codigo_usuario_admin": codigo_usuario_admin,
                "estado": "ACTIVA"
            }
        )
        
    except Exception as e:
        logger.error(f"Error registrando tienda: {str(e)}")
        return error_response("Error interno del servidor", 500)