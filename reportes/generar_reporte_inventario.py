# reports/generar_reporte_inventario.py
import os
import json
import logging
import boto3
import csv
from io import StringIO
from utils import (
    success_response,
    error_response,
    log_request,
    obtener_fecha_hora_peru,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims,
    put_item_standard,
    query_by_tenant,
    increment_counter,
    normalizar_texto
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB y S3
s3_client = boto3.client('s3')

S3_BUCKET = os.environ.get('S3_BUCKET')

def handler(event, context):
    """
    POST /reportes/inventario
    
    Genera reporte Excel del inventario actual.
    Guarda en S3 + registra en t_reportes.
    
    Request: { "body": {} }
    Response: {
      "success": true,
      "data": {
        "codigo_reporte": "R001",
        "download_url": "https://s3.amazonaws.com/.../inventario.xlsx"
      }
    }
    """
    try:
        log_request(event)
        
        # JWT validation + tenant
        tenant_id = extract_tenant_from_jwt_claims(event)
        user_info = extract_user_from_jwt_claims(event)
        codigo_usuario = user_info.get('codigo_usuario') if user_info else None
        
        fecha_actual = obtener_fecha_hora_peru()
        
        logger.info(f"📋 Generando reporte inventario: {tenant_id}")
        
        # =================================================================
        # OBTENER DATOS DE INVENTARIO
        # =================================================================
        
        result = query_by_tenant(os.environ['PRODUCTOS_TABLE'], tenant_id)
        productos = result.get('items', [])
        
        if not productos:
            return error_response("No hay productos activos para generar reporte", 400)
        
        # =================================================================
        # GENERAR CÓDIGO DE REPORTE CON TIENDA
        # =================================================================
        
        contador = increment_counter(os.environ['COUNTERS_TABLE'], tenant_id, 'REPORTES')
        codigo_reporte = f"{tenant_id}R{contador:03d}"
        
        # =================================================================
        # CONSTRUIR DATOS EXCEL
        # =================================================================
        
        datos_excel = []
        total_productos = 0
        total_valor = 0
        productos_sin_stock = 0
        productos_bajo_stock = 0
        
        for producto in productos:
            # Datos ya vienen filtrados por query_by_tenant (solo ACTIVOS)
            stock = int(producto.get('stock', 0))
            precio = float(producto.get('precio', 0))
            valor_total = stock * precio
            
            # Estadísticas
            total_productos += 1
            total_valor += valor_total
            
            if stock == 0:
                productos_sin_stock += 1
                estado_stock = "SIN STOCK"
            elif stock <= 5:
                productos_bajo_stock += 1
                estado_stock = "BAJO STOCK"
            else:
                estado_stock = "NORMAL"
            
            datos_excel.append({
                'Codigo Producto': producto.get('codigo_producto', ''),
                'Nombre': normalizar_texto(producto.get('nombre', '')),
                'Categoria': normalizar_texto(producto.get('categoria', '')),
                'Descripcion': normalizar_texto(producto.get('descripcion', '')),
                'Precio Unitario': precio,
                'Stock Actual': stock,
                'Estado Stock': estado_stock,
                'Valor Total': valor_total,
                'Fecha Creacion': producto.get('created_at', '')[:10]
            })
        
        # =================================================================
        # GENERAR CSV
        # =================================================================
        
        csv_buffer = StringIO()
        csv_writer = csv.writer(csv_buffer)
        
        # Encabezado resumen
        csv_writer.writerow(['REPORTE DE INVENTARIO'])
        csv_writer.writerow(['Codigo Reporte:', codigo_reporte])
        csv_writer.writerow(['Tienda:', tenant_id])
        csv_writer.writerow(['Generado por:', codigo_usuario])
        csv_writer.writerow(['Fecha:', fecha_actual])
        csv_writer.writerow([])  # Línea vacía
        
        # Encabezados de productos
        csv_writer.writerow([
            'Codigo Producto',
            'Nombre',
            'Categoria',
            'Descripcion',
            'Precio Unitario',
            'Stock Actual',
            'Estado Stock',
            'Valor Total',
            'Fecha Creacion'
        ])
        
        # Datos de productos
        for dato in datos_excel:
            csv_writer.writerow([
                dato['Codigo Producto'],
                dato['Nombre'],
                dato['Categoria'],
                dato['Descripcion'],
                f"{dato['Precio Unitario']:.2f}",
                dato['Stock Actual'],
                dato['Estado Stock'],
                f"{dato['Valor Total']:.2f}",
                dato['Fecha Creacion']
            ])
        
        # Resumen al final
        csv_writer.writerow([])
        csv_writer.writerow(['RESUMEN'])
        csv_writer.writerow(['Total Productos:', total_productos])
        csv_writer.writerow(['Productos Sin Stock:', productos_sin_stock])
        csv_writer.writerow(['Productos Bajo Stock:', productos_bajo_stock])
        csv_writer.writerow(['Valor Total Inventario:', f"S/ {total_valor:.2f}"])
        
        # =================================================================
        # GUARDAR EN S3
        # =================================================================
        
        csv_content = csv_buffer.getvalue()
        csv_buffer.close()
        
        # S3 key
        fecha_str = fecha_actual[:10].replace('-', '') + '_' + fecha_actual[11:19].replace(':', '')
        s3_key = f"{tenant_id}/reportes/inventario_{codigo_reporte}_{fecha_str}.csv"
        
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=csv_content.encode('utf-8'),
            ContentType='text/csv',
            ContentDisposition=f'attachment; filename="inventario_{codigo_reporte}.csv"'
        )
        
        logger.info(f"📁 Archivo guardado en S3: {s3_key}")
        
        # =================================================================
        # GENERAR PRESIGNED URL
        # =================================================================
        
        download_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': s3_key},
            ExpiresIn=3600  # 1 hora
        )
        
        # =================================================================
        # REGISTRAR EN t_reportes
        # =================================================================
        
        reporte_data = {
            "codigo_reporte": codigo_reporte,
            "tipo": "inventario",
            "fecha_generacion": fecha_actual,
            "parametros": {
                "total_productos": total_productos,
                "productos_sin_stock": productos_sin_stock,
                "productos_bajo_stock": productos_bajo_stock,
                "valor_total": round(total_valor, 2)
            },
            "s3_bucket": S3_BUCKET,
            "s3_key": s3_key,
            "tamaño_bytes": len(csv_content.encode('utf-8')),
            "generado_por": codigo_usuario,
            "estado": "COMPLETADO",
            "formato": "CSV"
        }
        
        put_item_standard(
            os.environ['REPORTES_TABLE'],
            tenant_id=tenant_id,
            entity_id=codigo_reporte,
            data=reporte_data
        )
        
        logger.info(f"✅ Reporte inventario generado: {codigo_reporte}")
        
        return success_response(
            mensaje="Reporte de inventario generado exitosamente",
            data={
                "codigo_reporte": codigo_reporte,
                "download_url": download_url,
                "formato": "CSV",
                "total_productos": total_productos
            }
        )
        
    except Exception as e:
        logger.error(f"Error generando reporte inventario: {str(e)}", exc_info=True)
        return error_response("Error interno del servidor", 500)