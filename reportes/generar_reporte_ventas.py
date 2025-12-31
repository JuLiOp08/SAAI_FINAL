# reports/generar_reporte_ventas.py
import os
import json
import logging
import boto3
from datetime import datetime, timedelta
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
    POST /reportes/ventas
    
    Genera reporte Excel de ventas del período.
    Guarda en S3 + registra en t_reportes.
    
    Request: { "body": { "fecha_inicio": "2025-11-01", "fecha_fin": "2025-11-08" } }
    Response: {
      "success": true,
      "data": {
        "codigo_reporte": "R002",
        "download_url": "https://s3.amazonaws.com/.../ventas.xlsx"
      }
    }
    """
    try:
        log_request(event)
        
        # JWT validation + tenant
        tenant_id = extract_tenant_from_jwt_claims(event)
        user_info = extract_user_from_jwt_claims(event)
        codigo_usuario = user_info.get('codigo_usuario') if user_info else None
        
        # Parse body para fechas
        body = json.loads(event.get('body', '{}'))
        
        fecha_actual = obtener_fecha_hora_peru()
        
        # Fechas del reporte (default: últimos 7 días)
        if 'fecha_inicio' in body and 'fecha_fin' in body:
            try:
                fecha_inicio = datetime.strptime(body['fecha_inicio'], '%Y-%m-%d')
                fecha_fin = datetime.strptime(body['fecha_fin'], '%Y-%m-%d')
            except ValueError:
                return error_response("Formato de fecha inválido. Use YYYY-MM-DD", 400)
        else:
            fecha_fin = datetime.fromisoformat(fecha_actual[:10])  # Solo fecha
            fecha_inicio = fecha_fin - timedelta(days=6)
        
        if fecha_inicio > fecha_fin:
            return error_response("Fecha inicio no puede ser mayor a fecha fin", 400)
        
        logger.info(f"📋 Generando reporte ventas: {tenant_id} ({fecha_inicio.strftime('%Y-%m-%d')} - {fecha_fin.strftime('%Y-%m-%d')})")
        
        # =================================================================
        # OBTENER DATOS DE VENTAS
        # =================================================================
        
        result = query_by_tenant('SAAI_Ventas', tenant_id)
        todas_ventas = result.get('items', [])
        
        # Filtrar por fechas y estado
        ventas = []
        for venta in todas_ventas:
            fecha_venta = venta.get('fecha', '')[:10]  # YYYY-MM-DD
            if (fecha_inicio.strftime('%Y-%m-%d') <= fecha_venta <= fecha_fin.strftime('%Y-%m-%d') and 
                venta.get('estado') == 'COMPLETADA'):
                ventas.append(venta)
        
        if not ventas:
            return error_response("No hay ventas en el período seleccionado", 400)
        
        # =================================================================
        # GENERAR CÓDIGO DE REPORTE CON TIENDA
        # =================================================================
        
        contador = increment_counter('SAAI_Counters', tenant_id, 'REPORTES')
        codigo_reporte = f"{tenant_id}R{contador:03d}"
        
        # =================================================================
        # CONSTRUIR DATOS EXCEL
        # =================================================================
        
        datos_ventas = []
        datos_productos_vendidos = {}
        datos_metodos_pago = {}
        total_ventas = len(ventas)
        total_ingresos = 0
        
        for venta in ventas:
            data = venta['data']
            total_venta = float(data.get('total', 0))
            total_ingresos += total_venta
            
            # Datos de venta individual
            datos_ventas.append({
                'Código Venta': data.get('codigo_venta', ''),
                'Fecha': data.get('fecha', ''),  # Ya es solo fecha YYYY-MM-DD
                'Cliente': data.get('cliente', ''),
                'Total': total_venta,
                'Método Pago': data.get('metodo_pago', ''),
                'Cantidad Items': len(data.get('productos', [])),
                'Vendedor': data.get('codigo_usuario', ''),
                'Estado': data.get('estado', 'COMPLETADA'),
                'Fecha Registro': data.get('created_at', '')[:10] if data.get('created_at') else ''
            })
            
            # Acumular productos vendidos
            for producto in data.get('productos', []):  # Cambiar de 'items' a 'productos'
                codigo = producto.get('codigo_producto', '')
                nombre = producto.get('nombre_producto', codigo)  # Cambiar de 'nombre' a 'nombre_producto'
                cantidad = int(producto.get('cantidad', 0))
                precio = float(producto.get('precio_unitario', 0))
                subtotal = float(producto.get('subtotal_item', 0))  # Usar subtotal_item calculado
                
                if codigo not in datos_productos_vendidos:
                    datos_productos_vendidos[codigo] = {
                        'Código Producto': codigo,
                        'Nombre Producto': nombre,
                        'Cantidad Total': 0,
                        'Ingresos Total': 0,
                        'Precio Promedio': precio
                    }
                
                datos_productos_vendidos[codigo]['Cantidad Total'] += cantidad
                datos_productos_vendidos[codigo]['Ingresos Total'] += subtotal
            
            # Acumular métodos de pago
            metodo = venta.get('metodo_pago', 'No especificado')
            if metodo not in datos_metodos_pago:
                datos_metodos_pago[metodo] = {'Cantidad': 0, 'Total': 0}
            
            datos_metodos_pago[metodo]['Cantidad'] += 1
            datos_metodos_pago[metodo]['Total'] += total_venta
        
        # =================================================================
        # CREAR EXCEL CON PANDAS
        # =================================================================
        
        # DataFrames
        df_ventas = pd.DataFrame(datos_ventas)
        
        df_productos = pd.DataFrame(list(datos_productos_vendidos.values()))
        if not df_productos.empty:
            df_productos = df_productos.sort_values('Cantidad Total', ascending=False)
        
        df_metodos_pago = pd.DataFrame([
            {'Método Pago': metodo, 'Cantidad Ventas': data['Cantidad'], 'Total Ingresos': data['Total']}
            for metodo, data in datos_metodos_pago.items()
        ])
        
        df_resumen = pd.DataFrame([
            {'Métrica': 'Período', 'Valor': f"{fecha_inicio.strftime('%Y-%m-%d')} - {fecha_fin.strftime('%Y-%m-%d')}"},
            {'Métrica': 'Total Ventas', 'Valor': total_ventas},
            {'Métrica': 'Total Ingresos', 'Valor': f"S/ {total_ingresos:.2f}"},
            {'Métrica': 'Promedio por Venta', 'Valor': f"S/ {total_ingresos/total_ventas:.2f}" if total_ventas > 0 else 'S/ 0.00'},
            {'Métrica': 'Productos Únicos', 'Valor': len(datos_productos_vendidos)},
            {'Métrica': 'Fecha Generación', 'Valor': fecha_actual[:19]}  # YYYY-MM-DDTHH:mm:ss
        ])
        
        # =================================================================
        # GUARDAR EN S3
        # =================================================================
        
        excel_buffer = BytesIO()
        
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            # Hojas del reporte
            df_ventas.to_excel(writer, sheet_name='Ventas', index=False)
            df_productos.to_excel(writer, sheet_name='Productos Vendidos', index=False)
            df_metodos_pago.to_excel(writer, sheet_name='Métodos Pago', index=False)
            df_resumen.to_excel(writer, sheet_name='Resumen', index=False)
            
            # Formatear columnas
            for sheet_name in writer.sheets:
                worksheet = writer.sheets[sheet_name]
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
        fecha_str = lima_now.strftime('%Y%m%d_%H%M%S')
        s3_key = f"{tenant_id}/reportes/ventas_{codigo_reporte}_{fecha_str}.xlsx"
        
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
            "tipo": "ventas",
            "fecha_generacion": fecha_actual,
            "parametros": {
                "fecha_inicio": fecha_inicio.strftime('%Y-%m-%d'),
                "fecha_fin": fecha_fin.strftime('%Y-%m-%d'),
                "total_ventas": total_ventas,
                "total_ingresos": total_ingresos
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
        
        logger.info(f"✅ Reporte ventas generado: {codigo_reporte}")
        
        return success_response(data={
            "codigo_reporte": codigo_reporte,
            "download_url": download_url
        })
        
    except Exception as e:
        logger.error(f"Error generando reporte ventas: {str(e)}")
        return error_response("Error interno del servidor", 500)