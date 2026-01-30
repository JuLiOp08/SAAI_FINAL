# reports/generar_reporte_ventas.py
import os
import json
import logging
import boto3
import csv
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Key
from io import StringIO
from decimal import Decimal
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
        
        # Verificar rol ADMIN
        tiene_permiso, error = verificar_rol_permitido(event, ['ADMIN'])
        if not tiene_permiso:
            return error
        
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
        
        result = query_by_tenant(os.environ['VENTAS_TABLE'], tenant_id)
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
        
        contador = increment_counter(os.environ['COUNTERS_TABLE'], tenant_id, 'REPORTES')
        codigo_reporte = f"{tenant_id}R{contador:03d}"
        
        # =================================================================
        # CONSTRUIR DATOS CSV
        # =================================================================
        
        datos_ventas = []
        datos_productos_vendidos = {}
        datos_metodos_pago = {}
        total_ventas = len(ventas)
        total_ingresos = 0
        
        for venta in ventas:
            total_venta = float(venta.get('total', 0))
            total_ingresos += total_venta
            
            # Datos de venta individual
            datos_ventas.append({
                'Codigo Venta': venta.get('codigo_venta', ''),
                'Fecha': venta.get('fecha', ''),
                'Cliente': normalizar_texto(venta.get('cliente', '')),
                'Total': total_venta,
                'Metodo Pago': normalizar_texto(venta.get('metodo_pago', '')),
                'Cantidad Items': len(venta.get('productos', [])),
                'Vendedor': venta.get('codigo_usuario', ''),
                'Estado': venta.get('estado', 'COMPLETADA'),
                'Fecha Registro': venta.get('created_at', '')[:10] if venta.get('created_at') else ''
            })
            
            # Acumular productos vendidos
            for producto in venta.get('productos', []):
                codigo = producto.get('codigo_producto', '')
                nombre = producto.get('nombre', codigo)
                cantidad = int(producto.get('cantidad', 0))
                precio = float(producto.get('precio_unitario', 0))
                subtotal = float(producto.get('subtotal', 0))
                
                if codigo not in datos_productos_vendidos:
                    datos_productos_vendidos[codigo] = {
                        'Codigo Producto': codigo,
                        'Nombre Producto': normalizar_texto(nombre),
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
        # CREAR CSV
        # =================================================================
        
        csv_buffer = StringIO()
        
        # Sección de encabezado
        csv_buffer.write("REPORTE DE VENTAS\n")
        csv_buffer.write(f"Codigo Reporte: {codigo_reporte}\n")
        csv_buffer.write(f"Tienda: {tenant_id}\n")
        csv_buffer.write(f"Periodo: {fecha_inicio.strftime('%Y-%m-%d')} a {fecha_fin.strftime('%Y-%m-%d')}\n")
        csv_buffer.write(f"Generado por: {codigo_usuario}\n")
        csv_buffer.write(f"Fecha: {fecha_actual[:19]}\n")
        csv_buffer.write("\n")
        
        # Sección de resumen
        csv_buffer.write("RESUMEN\n")
        writer = csv.writer(csv_buffer)
        writer.writerow(['Metrica', 'Valor'])
        writer.writerow(['Total Ventas', total_ventas])
        writer.writerow(['Total Ingresos', f"S/ {total_ingresos:.2f}"])
        writer.writerow(['Promedio por Venta', f"S/ {total_ingresos/total_ventas:.2f}" if total_ventas > 0 else 'S/ 0.00'])
        writer.writerow(['Productos Unicos', len(datos_productos_vendidos)])
        csv_buffer.write("\n")
        
        # Sección de ventas detalladas
        csv_buffer.write("DETALLE DE VENTAS\n")
        writer.writerow(['Codigo Venta', 'Fecha', 'Cliente', 'Total', 'Metodo Pago', 'Cantidad Items', 'Vendedor', 'Estado', 'Fecha Registro'])
        for venta in datos_ventas:
            writer.writerow([
                venta['Codigo Venta'],
                venta['Fecha'],
                venta['Cliente'],
                f"{venta['Total']:.2f}",
                venta['Metodo Pago'],
                venta['Cantidad Items'],
                venta['Vendedor'],
                venta['Estado'],
                venta['Fecha Registro']
            ])
        csv_buffer.write("\n")
        
        # Sección de productos vendidos
        csv_buffer.write("PRODUCTOS VENDIDOS\n")
        writer.writerow(['Codigo Producto', 'Nombre Producto', 'Cantidad Total', 'Ingresos Total', 'Precio Promedio'])
        productos_sorted = sorted(datos_productos_vendidos.values(), key=lambda x: x['Cantidad Total'], reverse=True)
        for producto in productos_sorted:
            writer.writerow([
                producto['Codigo Producto'],
                producto['Nombre Producto'],
                producto['Cantidad Total'],
                f"{producto['Ingresos Total']:.2f}",
                f"{producto['Precio Promedio']:.2f}"
            ])
        csv_buffer.write("\n")
        
        # Sección de métodos de pago
        csv_buffer.write("METODOS DE PAGO\n")
        writer.writerow(['Metodo Pago', 'Cantidad Ventas', 'Total Ingresos'])
        for metodo, data in datos_metodos_pago.items():
            writer.writerow([normalizar_texto(metodo), data['Cantidad'], f"{data['Total']:.2f}"])
        
        csv_content = csv_buffer.getvalue()
        
        # =================================================================
        # GUARDAR EN S3
        # =================================================================
        
        # Subir a S3
        fecha_str = fecha_actual[:10].replace('-', '') + '_' + fecha_actual[11:19].replace(':', '')
        s3_key = f"{tenant_id}/reportes/ventas_{codigo_reporte}_{fecha_str}.csv"
        
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=csv_content.encode('utf-8'),
            ContentType='text/csv',
            ContentDisposition=f'attachment; filename="ventas_{codigo_reporte}.csv"'
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
            "formato": "CSV",
            "fecha_generacion": fecha_actual,
            "parametros": {
                "fecha_inicio": fecha_inicio.strftime('%Y-%m-%d'),
                "fecha_fin": fecha_fin.strftime('%Y-%m-%d'),
                "total_ventas": total_ventas,
                "total_ingresos": Decimal(str(round(total_ingresos, 2)))
            },
            "s3_bucket": S3_BUCKET,
            "s3_key": s3_key,
            "tamaño_bytes": len(csv_content.encode('utf-8')),
            "generado_por": codigo_usuario,
            "estado": "COMPLETADO",
            "created_at": fecha_actual
        }
        
        # Guardar en t_reportes
        logger.info(f"💾 Guardando reporte en DynamoDB: tenant_id={tenant_id}, entity_id={codigo_reporte}")
        try:
            put_item_standard(
                os.environ['REPORTES_TABLE'],
                tenant_id=tenant_id,
                entity_id=codigo_reporte,
                data=reporte_data
            )
            logger.info(f"✅ Reporte guardado en t_reportes: {codigo_reporte}")
        except Exception as db_error:
            logger.error(f"❌ ERROR guardando en DynamoDB: {str(db_error)}")
            logger.error(f"Detalles - Table: {os.environ.get('REPORTES_TABLE')}, tenant_id: {tenant_id}, entity_id: {codigo_reporte}")
            # Continuamos aunque falle DynamoDB (el archivo ya está en S3)
        
        logger.info(f"✅ Reporte ventas generado: {codigo_reporte}")
        
        return success_response(data={
            "codigo_reporte": codigo_reporte,
            "download_url": download_url
        })
        
    except Exception as e:
        logger.error(f"Error generando reporte ventas: {str(e)}")
        return error_response("Error interno del servidor", 500)