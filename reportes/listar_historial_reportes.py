# reports/listar_historial_reportes.py
import os
import json
import logging
import boto3
from boto3.dynamodb.conditions import Key
from utils import (
    success_response,
    error_response,
    log_request,
    extract_tenant_from_jwt_claims,
    query_by_tenant,
    extract_pagination_params,
    create_next_token
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB y S3
s3_client = boto3.client('s3')

S3_BUCKET = os.environ.get('S3_BUCKET')

def handler(event, context):
    """
    GET /reportes/historial
    
    Lista historial de reportes generados con presigned URLs frescos.
    
    Query params: ?limit=10&next_token=xyz&tipo=inventario
    
    Response: {
      "success": true,
      "data": {
        "reportes": [
          {
            "codigo_reporte": "R001",
            "tipo": "ventas",
            "fecha": "2025-11-08",
            "download_url": "https://s3.amazonaws.com/..."
          }
        ],
        "next_token": "..."
      }
    }
    """
    try:
        log_request(event)
        
        # JWT validation + tenant
        tenant_id = extract_tenant_from_jwt_claims(event)
        
        # Extraer parámetros de paginación según SAAI 1.6
        pagination = extract_pagination_params(event, default_limit=20, max_limit=100)
        
        # Query params adicionales
        query_params = event.get('queryStringParameters') or {}
        tipo_filtro = query_params.get('tipo')  # inventario, ventas, gastos, general
        
        logger.info(f"📋 Listando historial reportes: {tenant_id} (tipo={tipo_filtro})")
        
        # =================================================================
        # OBTENER REPORTES CON PAGINACIÓN
        # =================================================================
        
        result = query_by_tenant(
            os.environ['REPORTES_TABLE'],
            tenant_id,
            limit=pagination['limit'],
            last_evaluated_key=pagination['exclusive_start_key']
        )
        
        reportes_items = result.get('items', [])
        
        # Filtrar por tipo si se especifica
        if tipo_filtro:
            reportes_items = [r for r in reportes_items if r.get('data', {}).get('tipo') == tipo_filtro]
        
        # =================================================================
        # CONSTRUIR RESPUESTA CON PRESIGNED URLS
        # =================================================================
        
        reportes_response = []
        
        for reporte_item in reportes_items:
            # Acceder a los datos dentro del campo 'data'
            data = reporte_item.get('data', {})
            
            # Información básica del reporte
            reporte_info = {
                'codigo_reporte': data.get('codigo_reporte'),
                'tipo': data.get('tipo'),
                'fecha': data.get('fecha_generacion', '')[:10] if data.get('fecha_generacion') else '',  # Solo fecha
                'hora': data.get('fecha_generacion', '')[11:19] if len(data.get('fecha_generacion', '')) > 10 else '',  # Solo hora
                'estado': data.get('estado', 'COMPLETADO'),
                'tamaño_mb': round(data.get('tamaño_bytes', 0) / 1024 / 1024, 2),
                'generado_por': data.get('generado_por'),
                'parametros': data.get('parametros', {}),
                'download_url': None  # Se genera más abajo
            }
            
            # =================================================================
            # GENERAR PRESIGNED URL FRESCO
            # =================================================================
            
            s3_key = data.get('s3_key')
            if s3_key and S3_BUCKET:
                try:
                    # Verificar que el archivo existe en S3 antes de generar URL
                    s3_client.head_object(Bucket=S3_BUCKET, Key=s3_key)
                    
                    # Generar presigned URL (válido por 1 hora)
                    download_url = s3_client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': S3_BUCKET, 'Key': s3_key},
                        ExpiresIn=3600  # 1 hora
                    )
                    
                    reporte_info['download_url'] = download_url
                    logger.debug(f"Presigned URL generado para {reporte_info['codigo_reporte']}")
                    
                except Exception as s3_error:
                    logger.error(f"Error generando presigned URL para {s3_key}: {str(s3_error)}")
                    reporte_info['download_url'] = None
                    reporte_info['estado'] = 'ERROR_S3'
            else:
                logger.warning(f"S3 key no encontrado para reporte {reporte_info['codigo_reporte']}")
                reporte_info['download_url'] = None
                reporte_info['estado'] = 'SIN_ARCHIVO'
            
            reportes_response.append(reporte_info)
        
        # =================================================================
        # PAGINACIÓN SAAI 1.6
        # =================================================================
        
        response_data = {
            'reportes': reportes_response
        }
        
        # Agregar next_token si hay más páginas
        if result.get('last_evaluated_key'):
            next_token = create_next_token(result['last_evaluated_key'])
            if next_token:
                response_data['next_token'] = next_token
        
        logger.info(f"✅ Historial reportes listado: {len(reportes_response)} reportes")
        
        return success_response(data=response_data)
        
    except Exception as e:
        logger.error(f"Error listando historial reportes: {str(e)}")
        return error_response("Error interno del servidor", 500)