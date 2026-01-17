# welcome/suscribirSnsAlerta.py
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

# SNS para crear suscripciones
sns = boto3.client('sns')

ALERTAS_TOPIC_ARN = os.environ.get('ALERTAS_SNS_TOPIC_ARN')

def handler(event, context):
    """
    SNS → Lambda: Crear suscripción EMAIL directa a AlertasSAAI (NO SES, NO Lambda)
    
    Según documento SAAI + AWS Academy:
    - Consumidor de BienvenidaSAAI  
    - Suscribe el email del admin directamente al topic AlertasSAAI
    - Aplica filtros por tenant_id y severidad CRITICAL
    - SNS maneja directamente el envío de emails (no SES, no Lambda adicional)
    
    ARQUITECTURA CORRECTA AWS ACADEMY:
    AlertasSAAI → [GuardarNotificacion Lambda, Email Subscriptions directas]
    
    NO EXISTE:
    - email_alerta.py Lambda
    - Integración con SES
    - Envío manual de correos
    
    SNS gestiona automáticamente:
    - Envío de emails
    - Filtros por MessageAttributes
    - Confirmación de suscripción
    - Multi-tenancy con FilterPolicy
    """
    try:
        log_request(event)
        
        if not ALERTAS_TOPIC_ARN:
            logger.error("ALERTAS_SNS_TOPIC_ARN no configurado")
            return error_response("Configuración SNS incompleta", 500)
        
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
            
            # Parse del mensaje
            try:
                message_data = json.loads(message_body)
            except json.JSONDecodeError:
                logger.error(f"Error parseando mensaje SNS: {message_body}")
                continue
            
            correo_admin = message_data.get('correo_admin')
            nombre_tienda = message_data.get('nombre_tienda')
            
            if not all([tenant_id, correo_admin]):
                logger.error(f"Datos incompletos: tenant_id={tenant_id}, correo_admin={correo_admin}")
                continue
            
            # Crear filtros SNS para suscripción EMAIL directa
            filter_policy = {
                "tenant_id": [tenant_id],  # Solo alertas de esta tienda
                "severidad": ["CRITICAL"]  # Solo alertas críticas
            }
            
            try:
                # Crear suscripción EMAIL directa (NO Lambda, NO SES)
                subscribe_response = sns.subscribe(
                    TopicArn=ALERTAS_TOPIC_ARN,
                    Protocol='email',  # EMAIL directo via SNS
                    Endpoint=correo_admin,
                    Attributes={
                        'FilterPolicy': json.dumps(filter_policy),
                        'FilterPolicyScope': 'MessageAttributes'
                    }
                )
                
                subscription_arn = subscribe_response.get('SubscriptionArn')
                
                logger.info(f"✅ SUSCRIPCIÓN EMAIL CREADA para {correo_admin} (tienda {tenant_id})")
                logger.info(f"📧 Protocol: EMAIL (SNS nativo)")
                logger.info(f"🔒 Filtros: {filter_policy}")
                logger.info(f"🆔 SubscriptionArn: {subscription_arn}")
                
                # IMPORTANTE: En AWS Academy/SNS, el usuario debe confirmar manualmente
                # SNS enviará email de confirmación automáticamente
                logger.info(f"⚠️  CONFIRMACIÓN REQUERIDA: Admin debe confirmar suscripción desde email")
                
            except Exception as sns_error:
                logger.error(f"❌ Error creando suscripción EMAIL: {str(sns_error)}")
                # No fallar todo el proceso por este error
                continue
            
            # Log de arquitectura correcta
            logger.info(f"🏗️  ARQUITECTURA AWS ACADEMY:")
            logger.info(f"   📨 AlertasSAAI → Email Subscription (directo)")
            logger.info(f"   📊 AlertasSAAI → GuardarNotificacion Lambda")
            logger.info(f"   🚫 NO SES, NO email_alerta.py")
            
            logger.info(f"✅ Configuración SNS completada para tienda {tenant_id} ({nombre_tienda})")
        
        return success_response(
            mensaje="Suscripciones EMAIL SNS configuradas - Verificar email para confirmación"
        )
        
    except Exception as e:
        logger.error(f"Error configurando suscripciones EMAIL SNS: {str(e)}")
        return error_response("Error interno del servidor", 500)