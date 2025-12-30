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
    get_tenant_id_from_jwt,
    paginate_response
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB y S3
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')

reportes_table = dynamodb.Table(os.environ['REPORTES_TABLE'])
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
        tenant_id = get_tenant_id_from_jwt(event)
        
        # Query params
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', 20))
        next_token = query_params.get('next_token')
        tipo_filtro = query_params.get('tipo')  # inventario, ventas, gastos, general
        
        logger.info(f"📋 Listando historial reportes: {tenant_id} (tipo={tipo_filtro})")
        
        # =================================================================
        # QUERY DYNAMODB
        # =================================================================
        
        query_kwargs = {
            'KeyConditionExpression': Key('tenant_id').eq(tenant_id),
            'ScanIndexForward': False,  # Orden descendente (más recientes primero)
            'Limit': limit
        }
        
        # Aplicar filtro por tipo si se especifica
        if tipo_filtro:
            query_kwargs['FilterExpression'] = '#data.#tipo = :tipo'
            query_kwargs['ExpressionAttributeNames'] = {
                '#data': 'data',
                '#tipo': 'tipo'
            }
            query_kwargs['ExpressionAttributeValues'] = {
                ':tipo': tipo_filtro
            }
        
        # Paginación
        if next_token:
            try:
                start_key = json.loads(next_token)
                query_kwargs['ExclusiveStartKey'] = start_key
            except (json.JSONDecodeError, ValueError):
                logger.warning(f"Token de paginación inválido: {next_token}")
                # Continuar sin token
        
        response = reportes_table.query(**query_kwargs)
        
        reportes_items = response.get('Items', [])
        
        # =================================================================
        # CONSTRUIR RESPUESTA CON PRESIGNED URLS
        # =================================================================
        
        reportes_response = []
        
        for reporte_item in reportes_items:
            data = reporte_item['data']
            
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
        # PAGINACIÓN
        # =================================================================
        
        response_data = {
            'reportes': reportes_response
        }
        
        # Si hay más resultados, incluir next_token
        if 'LastEvaluatedKey' in response:
            try:
                response_data['next_token'] = json.dumps(response['LastEvaluatedKey'])
            except Exception as e:
                logger.error(f"Error serializando LastEvaluatedKey: {str(e)}")
        
        logger.info(f"✅ Historial reportes listado: {len(reportes_response)} reportes")
        
        return success_response(data=response_data)
        
    except Exception as e:
        logger.error(f"Error listando historial reportes: {str(e)}")
        return error_response("Error interno del servidor", 500)