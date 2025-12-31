# reports/generar_reporte_inventario.py
import os
import json
import logging
import boto3
from datetime import datetime
from boto3.dynamodb.conditions import Key
from io import BytesIO
import pandas as pd
from utils import (
    success_response,
    error_response,
    log_request,
    obtener_fecha_hora_peru,
    extract_tenant_from_jwt_claims,
    extract_user_from_jwt_claims,
    put_item_standard,
    query_by_tenant,
    increment_counter
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
        
        result = query_by_tenant('SAAI_Productos', tenant_id)
        productos = result.get('items', [])
        
        if not productos:
            return error_response("No hay productos activos para generar reporte", 400)
        
        # =================================================================
        # GENERAR CÓDIGO DE REPORTE CON TIENDA
        # =================================================================
        
        contador = increment_counter('SAAI_Counters', tenant_id, 'REPORTES')
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
                'Código Producto': producto.get('codigo_producto', ''),
                'Nombre': producto.get('nombre', ''),
                'Categoría': producto.get('categoria', ''),
                'Descripción': producto.get('descripcion', ''),
                'Precio Unitario': precio,
                'Stock Actual': stock,
                'Estado Stock': estado_stock,
                'Valor Total': valor_total,
                'Fecha Creación': producto.get('created_at', '')[:10],  # Solo fecha
                'Creado Por': producto.get('created_by', '')
            })
        
        # =================================================================
        # CREAR EXCEL CON PANDAS
        # =================================================================
        
        # DataFrame principal
        df_productos = pd.DataFrame(datos_excel)
        
        # DataFrame resumen
        df_resumen = pd.DataFrame([
            {'Métrica': 'Total Productos', 'Valor': total_productos},
            {'Métrica': 'Productos Sin Stock', 'Valor': productos_sin_stock},
            {'Métrica': 'Productos Bajo Stock', 'Valor': productos_bajo_stock},
            {'Métrica': 'Valor Total Inventario', 'Valor': f"S/ {total_valor:.2f}"},
            {'Métrica': 'Fecha Generación', 'Valor': fecha_actual[:19]}  # YYYY-MM-DDTHH:mm:ss
        ])
        
        # =================================================================
        # GUARDAR EN S3
        # =================================================================
        
        excel_buffer = BytesIO()
        
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            # Hoja de productos
            df_productos.to_excel(writer, sheet_name='Inventario', index=False)
            
            # Hoja de resumen
            df_resumen.to_excel(writer, sheet_name='Resumen', index=False)
            
            # Formatear columnas
            workbook = writer.book
            worksheet = writer.sheets['Inventario']
            
            # Ajustar ancho de columnas
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        excel_buffer.seek(0)
        
        # Subir a S3
        fecha_str = fecha_actual[:10].replace('-', '') + '_' + fecha_actual[11:19].replace(':', '')
        s3_key = f"{tenant_id}/reportes/inventario_{codigo_reporte}_{fecha_str}.xlsx"
        
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=excel_buffer.getvalue(),
            ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
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
                "productos_bajo_stock": productos_bajo_stock
            },
            "s3_bucket": S3_BUCKET,
            "s3_key": s3_key,
            "tamaño_bytes": len(excel_buffer.getvalue()),
            "generado_por": codigo_usuario,
            "estado": "COMPLETADO",
            "created_at": fecha_actual
        }
        
        put_item_standard(
            'SAAI_Reportes',
            tenant_id=tenant_id,
            entity_id=codigo_reporte,
            data=reporte_data
        )
        
        logger.info(f"✅ Reporte inventario generado: {codigo_reporte}")
        
        return success_response(data={
            "codigo_reporte": codigo_reporte,
            "download_url": download_url
        })
        
    except Exception as e:
        logger.error(f"Error generando reporte inventario: {str(e)}")
        return error_response("Error interno del servidor", 500)