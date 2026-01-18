# -*- coding: utf-8 -*-
"""
Lambda: SeedUsuarioSaai
Crea el usuario SAAI inicial en DynamoDB
EJECUTAR SOLO UNA VEZ (después del deploy inicial)
"""

import boto3
import json
import hashlib
import os
from datetime import datetime

# Clientes AWS
dynamodb = boto3.resource('dynamodb')
USUARIOS_TABLE = os.environ.get('USUARIOS_TABLE')
table_usuarios = dynamodb.Table(USUARIOS_TABLE)

# Credenciales oficiales del usuario SAAI (según SAAI_oficial.txt)
SAAI_USER = {
    'email': 'saai@saai.com',
    'password': 'admin123',  # Plain text (se hasheará)
    'nombre': 'SAAI Admin'
}


def hash_password(password):
    """
    Hash de password usando PBKDF2-HMAC-SHA256 con salt aleatorio
    """
    # Generar salt aleatorio de 32 bytes
    salt = os.urandom(32)
    
    # Hash PBKDF2 con 100,000 iteraciones
    password_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    
    return password_hash.hex(), salt.hex()


def handler(event, context):
    """
    Crea el usuario SAAI inicial en t_usuarios
    
    Response:
    {
        "success": true,
        "message": "Usuario SAAI creado exitosamente",
        "data": {
            "email": "saai@saai.com",
            "password": "admin123",
            "codigo_usuario": "SAAI001"
        }
    }
    """
    try:
        # 1. Hash de la password con PBKDF2
        password_plain = SAAI_USER['password']
        password_hash, salt = hash_password(password_plain)
        
        # 2. Timestamp actual (America/Lima)
        now = datetime.utcnow().isoformat() + '-05:00'
        
        # 3. Estructura según SAAI_oficial.txt:
        # tenant_id = "SAAI"
        # entity_id = codigo_usuario (SAAI001)
        # data = JSON completo del usuario
        
        item = {
            'tenant_id': 'SAAI',
            'entity_id': 'SAAI001',
            'data': {
                'codigo_usuario': 'SAAI001',
                'nombre': SAAI_USER['nombre'],
                'email': SAAI_USER['email'],
                'password': password_hash,
                'salt': salt,
                'role': 'saai',
                'estado': 'ACTIVO',
                'created_at': now,
                'updated_at': now
            }
        }
        
        # 4. Insertar en DynamoDB
        table_usuarios.put_item(Item=item)
        
        print(f"✅ Usuario SAAI creado: {SAAI_USER['email']}")
        
        # 5. Response con credenciales para usar en Postman
        return {
            'statusCode': 201,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': True,
                'message': 'Usuario SAAI creado exitosamente',
                'data': {
                    'email': SAAI_USER['email'],
                    'password': SAAI_USER['password'],
                    'codigo_usuario': 'SAAI001',
                    'role': 'saai',
                    'instrucciones': 'Usa estas credenciales en Postman -> Login SAAI'
                }
            })
        }
        
    except Exception as e:
        print(f"❌ Error creando usuario SAAI: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'message': 'Error creando usuario SAAI',
                'error': str(e)
            })
        }
