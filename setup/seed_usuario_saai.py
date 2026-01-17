# -*- coding: utf-8 -*-
"""
Lambda: SeedUsuarioSaai
Crea el usuario SAAI inicial en DynamoDB
EJECUTAR SOLO UNA VEZ (después del deploy inicial)
"""

import boto3
import json
from datetime import datetime
import bcrypt

# Clientes AWS
dynamodb = boto3.resource('dynamodb')
table_usuarios = dynamodb.Table('t_usuarios')

# Credenciales oficiales del usuario SAAI (según SAAI_oficial.txt)
SAAI_USER = {
    'email': 'saai@saai.com',
    'password': 'admin123',  # Plain text (se hasheará)
    'nombre': 'SAAI Admin'
}


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
        # 1. Hash de la password con bcrypt (salt 10 rounds)
        password_plain = SAAI_USER['password']
        password_hash = bcrypt.hashpw(password_plain.encode('utf-8'), bcrypt.gensalt(rounds=10)).decode('utf-8')
        
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
                'password_hash': password_hash,
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
