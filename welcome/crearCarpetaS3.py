# welcome/crear_carpeta_s3.py
import os
import json
import logging
import boto3
from utils import (
    success_response,
    error_response,
    log_request
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# S3 para creación de carpetas
s3 = boto3.client('s3')

S3_BUCKET = os.environ.get('S3_BUCKET', 'saai-tiendas')

def handler(event, context):
    """
    SNS → Lambda: Crear estructura de carpetas S3 para nueva tienda
    
    Según documento SAAI:
    - Consumidor de BienvenidaSAAI
    - Crea estructura S3: saai-tiendas/{codigo_tienda}/reportes/, /ml-datasets/, /ml-models/
    - Se ejecuta cuando se registra una nueva tienda
    
    Estructura creada:
    saai-tiendas/
    └── T002/
        ├── reportes/
        ├── ml-datasets/
        └── ml-models/
    """
    try:
        log_request(event)
        
        # Procesar todos los records SNS
        for record in event.get('Records', []):
            if record.get('EventSource') != 'aws:sns':
                continue
                
            sns_data = record.get('Sns', {})
            message_attrs = sns_data.get('MessageAttributes', {})
            message_body = sns_data.get('Message', '{}')
            
            # Extraer MessageAttributes
            tenant_id = message_attrs.get('tenant_id', {}).get('Value')
            ts = message_attrs.get('ts', {}).get('Value')
            
            if not tenant_id:
                logger.error("tenant_id requerido para crear carpetas S3")
                continue
            
            # Parse del mensaje
            try:
                message_data = json.loads(message_body)
            except json.JSONDecodeError:
                logger.error(f"Error parseando mensaje SNS: {message_body}")
                continue
            
            nombre_tienda = message_data.get('nombre_tienda', 'Tienda')
            
            # Definir estructura de carpetas
            carpetas = [
                f"{tenant_id}/reportes/",
                f"{tenant_id}/ml-datasets/",
                f"{tenant_id}/ml-models/"
            ]
            
            # Crear cada carpeta
            for carpeta in carpetas:
                try:
                    # En S3, las carpetas se crean mediante un objeto con suffix "/"
                    response = s3.put_object(
                        Bucket=S3_BUCKET,
                        Key=carpeta,
                        Body='',
                        ContentType='application/x-directory',
                        Metadata={
                            'tenant_id': tenant_id,
                            'nombre_tienda': nombre_tienda,
                            'created_at': ts or '',
                            'purpose': 'SAAI tienda setup'
                        }
                    )
                    
                    logger.info(f"Carpeta S3 creada: s3://{S3_BUCKET}/{carpeta}")
                    
                except Exception as s3_error:
                    logger.error(f"Error creando carpeta S3 {carpeta}: {str(s3_error)}")
                    # Continuar con las demás carpetas
            
            # Crear archivo README en la carpeta raíz de la tienda
            readme_content = f"""# SAAI - Datos de {nombre_tienda} ({tenant_id})

## Estructura de Carpetas

### 📊 /reportes/
Almacena todos los reportes generados para la tienda:
- Reporte de Inventario (.xlsx)
- Reporte de Ventas (.xlsx)  
- Reporte de Gastos (.xlsx)
- Reporte General (.xlsx)

### 🤖 /ml-datasets/
Datasets para entrenamiento de Machine Learning:
- Datos históricos de ventas
- Datos de productos y stock
- Features para predicción de demanda

### 🧠 /ml-models/
Modelos entrenados y artefactos ML:
- Modelos SageMaker
- Configuraciones de entrenamiento
- Métricas de evaluación

## Información de la Tienda

- **Código de Tienda:** {tenant_id}
- **Nombre:** {nombre_tienda}
- **Fecha de Creación:** {ts}
- **Sistema:** SAAI (Smart Assistant for Inventory)

## Acceso y Seguridad

- Los datos están aislados por tienda (multi-tenant)
- Solo usuarios autorizados de la tienda pueden acceder
- Backups automáticos configurados
- Versionado de archivos habilitado

---
Generado automáticamente por SAAI | {ts}
"""
            
            try:
                readme_response = s3.put_object(
                    Bucket=S3_BUCKET,
                    Key=f"{tenant_id}/README.md",
                    Body=readme_content.encode('utf-8'),
                    ContentType='text/markdown',
                    Metadata={
                        'tenant_id': tenant_id,
                        'nombre_tienda': nombre_tienda,
                        'created_at': ts or '',
                        'file_type': 'documentation'
                    }
                )
                
                logger.info(f"README creado: s3://{S3_BUCKET}/{tenant_id}/README.md")
                
            except Exception as readme_error:
                logger.error(f"Error creando README: {str(readme_error)}")
            
            logger.info(f"Estructura S3 creada exitosamente para tienda {tenant_id} ({nombre_tienda})")
        
        return success_response(message="Estructura S3 creada")
        
    except Exception as e:
        logger.error(f"Error creando estructura S3: {str(e)}")
        return error_response("Error interno del servidor", 500)