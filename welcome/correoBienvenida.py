# welcome/correo_bienvenida.py
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

# DESHABILITADO: SES no disponible en AWS Academy
# El envío de correos se hace con SNS Email Subscriptions

def handler(event, context):
    """
    SNS → Lambda: Enviar correo de bienvenida al registrar tienda
    
    Según documento SAAI:
    - Consumidor de BienvenidaSAAI
    - Se dispara cuando RegistrarTienda crea una tienda
    - Envía correo al admin de la tienda recién creada
    
    Event estructura:
    {
        "Records": [
            {
                "EventSource": "aws:sns",
                "Sns": {
                    "Message": "{\"tenant_id\": \"T002\", \"correo_admin\": \"admin@tienda.com\", \"nombre_tienda\": \"Bodega San Juan\", \"ts\": \"2025-11-08T15:30:00-05:00\"}",
                    "MessageAttributes": {
                        "tenant_id": {"Type": "String", "Value": "T002"},
                        "ts": {"Type": "String", "Value": "2025-11-08T15:30:00-05:00"}
                    }
                }
            }
        ]
    }
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
            
            # Parse del mensaje
            try:
                message_data = json.loads(message_body)
            except json.JSONDecodeError:
                logger.error(f"Error parseando mensaje SNS: {message_body}")
                continue
            
            correo_admin = message_data.get('correo_admin')
            nombre_tienda = message_data.get('nombre_tienda')
            
            if not all([tenant_id, correo_admin, nombre_tienda]):
                logger.error(f"Datos incompletos: tenant_id={tenant_id}, correo_admin={correo_admin}, nombre_tienda={nombre_tienda}")
                continue
            
            # Construir email de bienvenida
            subject = f"🎉 ¡Bienvenido a SAAI! - Tu tienda {nombre_tienda} está lista"
            
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
                    .header {{ background-color: #28a745; color: white; padding: 20px; border-radius: 8px; text-align: center; }}
                    .content {{ background-color: #f8f9fa; padding: 25px; margin: 20px 0; border-radius: 8px; }}
                    .highlight {{ background-color: #e7f3ff; padding: 15px; border-left: 4px solid #0066cc; margin: 15px 0; }}
                    .footer {{ color: #6c757d; font-size: 14px; margin-top: 25px; text-align: center; }}
                    .button {{ display: inline-block; background-color: #007bff; color: white; padding: 12px 25px; 
                              text-decoration: none; border-radius: 5px; margin: 10px 0; }}
                    .credentials {{ background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; }}
                    h1, h2, h3 {{ color: #333; }}
                    ul li {{ margin: 8px 0; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>🎉 ¡Bienvenido a SAAI!</h1>
                    <p>Sistema Inteligente de Gestión para tu Negocio</p>
                </div>
                
                <div class="content">
                    <h2>¡Hola! Tu tienda ya está registrada</h2>
                    
                    <div class="highlight">
                        <h3>📋 Información de tu tienda:</h3>
                        <ul>
                            <li><strong>Nombre:</strong> {nombre_tienda}</li>
                            <li><strong>Código de Tienda:</strong> {tenant_id}</li>
                            <li><strong>Email Administrador:</strong> {correo_admin}</li>
                            <li><strong>Fecha de Registro:</strong> {ts}</li>
                        </ul>
                    </div>
                    
                    <h3>🚀 ¿Qué puedes hacer ahora?</h3>
                    <ul>
                        <li><strong>Gestionar Productos:</strong> Agregar, editar y controlar tu inventario</li>
                        <li><strong>Registrar Ventas:</strong> Control completo de ventas con descuento automático de stock</li>
                        <li><strong>Controlar Gastos:</strong> Llevar registro detallado de todos tus gastos</li>
                        <li><strong>Gestionar Usuarios:</strong> Crear trabajadores y administradores</li>
                        <li><strong>Ver Analíticas:</strong> Reportes detallados y métricas de tu negocio</li>
                        <li><strong>Recibir Alertas:</strong> Notificaciones automáticas de stock bajo y más</li>
                        <li><strong>Generar Reportes:</strong> Exportar información en Excel</li>
                        <li><strong>Predicciones IA:</strong> Predicción de demanda con Machine Learning</li>
                    </ul>
                    
                    <div class="credentials">
                        <h3>🔐 Acceso al Sistema:</h3>
                        <p><strong>Email:</strong> {correo_admin}</p>
                        <p><strong>Contraseña:</strong> La que configuraste durante el registro</p>
                        <p><em>Tip: Puedes cambiar tu contraseña desde el panel de administración</em></p>
                    </div>
                    
                    <h3>📈 Funcionalidades Premium:</h3>
                    <ul>
                        <li>✅ <strong>Multi-usuario:</strong> Trabajadores y administradores</li>
                        <li>✅ <strong>Tiempo Real:</strong> Actualizaciones automáticas</li>
                        <li>✅ <strong>Seguridad:</strong> Datos aislados por tienda</li>
                        <li>✅ <strong>Backups:</strong> Tus datos están seguros en AWS</li>
                        <li>✅ <strong>Escalable:</strong> Crece con tu negocio</li>
                    </ul>
                    
                    <a href="#" class="button">🚀 Acceder al Panel de Administración</a>
                </div>
                
                <div class="footer">
                    <h3>📞 ¿Necesitas ayuda?</h3>
                    <p>Nuestro equipo de soporte está disponible para ayudarte:</p>
                    <p>📧 Email: soporte@saai.com</p>
                    <p>📱 WhatsApp: +51 999 888 777</p>
                    <p>🕒 Horario: Lunes a Viernes, 8:00 AM - 6:00 PM (Hora Perú)</p>
                    <br>
                    <p>¡Gracias por confiar en SAAI para hacer crecer tu negocio!</p>
                    <p><strong>Equipo SAAI</strong> | {ts}</p>
                </div>
            </body>
            </html>
            """
            
            # PLACEHOLDER: Correo de bienvenida
            # En AWS Academy, el correo se envía via SNS Email Subscriptions
            # No se usa SES ni envío directo desde Lambda
            try:
                # Log de la acción (no envía correo real)
                logger.info(f"Correo de bienvenida procesado para {correo_admin} - Tienda {tenant_id}")
                logger.info(f"Subject: 🎉 ¡Bienvenido a SAAI! - Tu tienda {nombre_tienda} está lista")
                logger.info(f"Contenido HTML generado ({len(html_body)} caracteres)")
                
                # En AWS Academy, esto no se ejecuta realmente (Lambda está comentado en serverless.yml)
                # Si se habilitara SES en el futuro, aquí iría:
                # ses_client.send_email(
                #     Source='noreply@saai.com',
                #     Destination={'ToAddresses': [correo_admin]},
                #     Message={
                #         'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                #         'Body': {'Html': {'Data': html_body, 'Charset': 'UTF-8'}}
                #     }
                # )
                
            except Exception as email_error:
                logger.error(f"Error en placeholder de correo de bienvenida: {str(email_error)}")
                # No fallar el lambda por error de placeholder
                continue
        
        return success_response(mensaje="Correos de bienvenida procesados")
        
    except Exception as e:
        logger.error(f"Error procesando correos de bienvenida: {str(e)}")
        return error_response("Error interno del servidor", 500)