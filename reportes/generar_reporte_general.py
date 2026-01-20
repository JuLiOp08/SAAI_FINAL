# reportes/generar_reporte_general.py
import os
import json
import logging
import boto3
import csv
from datetime import datetime, timedelta
from io import StringIO
from utils import (
    success_response,
    error_response,
    validation_error_response,
    log_request,
    parse_request_body,
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

# S3 Client
s3_client = boto3.client('s3')

# Environment Variables
S3_BUCKET = os.environ.get('S3_BUCKET')
PRODUCTOS_TABLE = os.environ.get('PRODUCTOS_TABLE')
VENTAS_TABLE = os.environ.get('VENTAS_TABLE')
GASTOS_TABLE = os.environ.get('GASTOS_TABLE')
REPORTES_TABLE = os.environ.get('REPORTES_TABLE')

def handler(event, context):
    """
    POST /reportes/general
    
    Genera reporte Excel combinado (inventario + ventas + gastos + indicadores).
    Guarda en S3 + registra en t_reportes.
    
    Request: { "body": { "fecha_inicio": "2025-11-01", "fecha_fin": "2025-11-08" } }
    Response: {
      "success": true,
      "data": {
        "codigo_reporte": "T001R004",
        "download_url": "https://s3.amazonaws.com/.../general.xlsx"
      }
    }
    """
    try:
        log_request(event, context)
        
        # JWT validation + tenant
        tenant_id = extract_tenant_from_jwt_claims(event)
        user_info = extract_user_from_jwt_claims(event)
        codigo_usuario = user_info.get('codigo_usuario') if user_info else None
        
        # Parse body para fechas
        body = parse_request_body(event)
        if not body:
            body = {}
        
        fecha_actual = obtener_fecha_hora_peru()
        
        # Fechas del reporte (default: últimos 7 días)
        if 'fecha_inicio' in body and 'fecha_fin' in body:
            try:
                fecha_inicio = datetime.strptime(body['fecha_inicio'], '%Y-%m-%d')
                fecha_fin = datetime.strptime(body['fecha_fin'], '%Y-%m-%d')
            except ValueError:
                return validation_error_response({"fecha": "Formato de fecha inválido. Use YYYY-MM-DD"})
        else:
            fecha_fin = datetime.fromisoformat(fecha_actual[:10])
            fecha_inicio = fecha_fin - timedelta(days=6)
        
        if fecha_inicio > fecha_fin:
            return validation_error_response({"fecha": "Fecha inicio no puede ser mayor a fecha fin"})
        
        logger.info(f"📋 Generando reporte general: {tenant_id} ({fecha_inicio.strftime('%Y-%m-%d')} - {fecha_fin.strftime('%Y-%m-%d')})")
        
        # =================================================================
        # GENERAR CÓDIGO DE REPORTE
        # =================================================================
        
        contador = increment_counter(REPORTES_TABLE, tenant_id, 'REPORTES')
        codigo_reporte = f"{tenant_id}R{contador:03d}"
        
        # =================================================================
        # OBTENER DATOS DE LAS 3 FUENTES
        # =================================================================
        
        # 1. INVENTARIO ACTUAL
        result_productos = query_by_tenant(PRODUCTOS_TABLE, tenant_id)
        productos = result_productos.get('items', [])
        
        # 2. VENTAS DEL PERÍODO
        result_ventas = query_by_tenant(VENTAS_TABLE, tenant_id)
        todas_ventas = result_ventas.get('items', [])
        
        # Filtrar ventas por fecha y estado
        ventas = []
        for venta in todas_ventas:
            fecha_venta = venta.get('fecha', '')[:10]
            if (fecha_inicio.strftime('%Y-%m-%d') <= fecha_venta <= fecha_fin.strftime('%Y-%m-%d') and 
                venta.get('estado') == 'COMPLETADA'):
                ventas.append(venta)
        
        # 3. GASTOS DEL PERÍODO
        result_gastos = query_by_tenant(GASTOS_TABLE, tenant_id)
        todos_gastos = result_gastos.get('items', [])
        
        # Filtrar gastos por fecha y estado
        gastos = []
        for gasto in todos_gastos:
            fecha_gasto = gasto.get('fecha', '')[:10]
            if (fecha_inicio.strftime('%Y-%m-%d') <= fecha_gasto <= fecha_fin.strftime('%Y-%m-%d') and 
                gasto.get('estado') == 'ACTIVO'):
                gastos.append(gasto)
        
        # =================================================================
        # CALCULAR MÉTRICAS GENERALES
        # =================================================================
        
        total_ingresos = sum(float(v.get('total', 0)) for v in ventas)
        total_egresos = sum(float(g.get('monto', 0)) for g in gastos)
        balance = total_ingresos - total_egresos
        
        valor_inventario = sum(
            int(p.get('stock', 0)) * float(p.get('precio', 0)) 
            for p in productos
        )
        
        productos_sin_stock = len([p for p in productos if int(p.get('stock', 0)) == 0])
        productos_bajo_stock = len([p for p in productos if 0 < int(p.get('stock', 0)) <= 5])
        
        # =================================================================
        # CREAR CSV CON TODAS LAS SECCIONES
        # =================================================================
        
        csv_buffer = StringIO()
        
        # Sección de encabezado principal
        csv_buffer.write("REPORTE GENERAL\n")
        csv_buffer.write(f"Codigo Reporte: {codigo_reporte}\n")
        csv_buffer.write(f"Tienda: {tenant_id}\n")
        csv_buffer.write(f"Periodo: {fecha_inicio.strftime('%Y-%m-%d')} a {fecha_fin.strftime('%Y-%m-%d')}\n")
        csv_buffer.write(f"Generado por: {codigo_usuario}\n")
        csv_buffer.write(f"Fecha: {fecha_actual[:19]}\n")
        csv_buffer.write("\n")
        
        # =================================================================
        # SECCIÓN 1: DASHBOARD EJECUTIVO
        # =================================================================
        
        csv_buffer.write("="*60 + "\n")
        csv_buffer.write("DASHBOARD EJECUTIVO\n")
        csv_buffer.write("="*60 + "\n")
        csv_buffer.write("\n")
        
        writer = csv.writer(csv_buffer)
        writer.writerow(['Metrica', 'Valor'])
        writer.writerow(['RESUMEN FINANCIERO', ''])
        writer.writerow(['Total Ingresos (Ventas)', f"S/ {total_ingresos:.2f}"])
        writer.writerow(['Total Egresos (Gastos)', f"S/ {total_egresos:.2f}"])
        writer.writerow(['Balance Neto', f"S/ {balance:.2f}"])
        writer.writerow(['Valor Inventario Actual', f"S/ {valor_inventario:.2f}"])
        writer.writerow(['', ''])
        writer.writerow(['INDICADORES OPERATIVOS', ''])
        writer.writerow(['Total Productos', len(productos)])
        writer.writerow(['Productos Sin Stock', productos_sin_stock])
        writer.writerow(['Productos Bajo Stock (<=5)', productos_bajo_stock])
        writer.writerow(['Total Ventas', len(ventas)])
        writer.writerow(['Promedio por Venta', f"S/ {total_ingresos/len(ventas):.2f}" if ventas else 'S/ 0.00'])
        writer.writerow(['Total Gastos', len(gastos)])
        writer.writerow(['Promedio por Gasto', f"S/ {total_egresos/len(gastos):.2f}" if gastos else 'S/ 0.00'])
        csv_buffer.write("\n\n")
        
        # =================================================================
        # SECCIÓN 2: DETALLE DE INVENTARIO
        # =================================================================
        
        csv_buffer.write("="*60 + "\n")
        csv_buffer.write("INVENTARIO ACTUAL\n")
        csv_buffer.write("="*60 + "\n")
        csv_buffer.write("\n")
        
        if productos:
            writer.writerow(['Codigo', 'Nombre', 'Categoria', 'Precio', 'Stock', 'Estado Stock', 'Valor Total'])
            for producto in productos:
                stock = int(producto.get('stock', 0))
                precio = float(producto.get('precio', 0))
                valor_total = stock * precio
                
                if stock == 0:
                    estado_stock = "SIN STOCK"
                elif stock <= 5:
                    estado_stock = "BAJO STOCK"
                else:
                    estado_stock = "NORMAL"
                
                writer.writerow([
                    producto.get('codigo_producto', ''),
                    normalizar_texto(producto.get('nombre', '')),
                    normalizar_texto(producto.get('categoria', '')),
                    f"{precio:.2f}",
                    stock,
                    estado_stock,
                    f"{valor_total:.2f}"
                ])
        else:
            writer.writerow(['No hay productos en el inventario'])
        
        csv_buffer.write("\n\n")
        
        # =================================================================
        # SECCIÓN 3: DETALLE DE VENTAS
        # =================================================================
        
        csv_buffer.write("="*60 + "\n")
        csv_buffer.write("VENTAS DEL PERIODO\n")
        csv_buffer.write("="*60 + "\n")
        csv_buffer.write("\n")
        
        if ventas:
            writer.writerow(['Codigo Venta', 'Fecha', 'Cliente', 'Total', 'Metodo Pago', 'Vendedor'])
            for venta in ventas:
                writer.writerow([
                    venta.get('codigo_venta', ''),
                    venta.get('fecha', ''),
                    normalizar_texto(venta.get('cliente', '')),
                    f"{float(venta.get('total', 0)):.2f}",
                    normalizar_texto(venta.get('metodo_pago', '')),
                    venta.get('codigo_usuario', '')
                ])
        else:
            writer.writerow(['No hay ventas en el periodo seleccionado'])
        
        csv_buffer.write("\n\n")
        
        # =================================================================
        # SECCIÓN 4: DETALLE DE GASTOS
        # =================================================================
        
        csv_buffer.write("="*60 + "\n")
        csv_buffer.write("GASTOS DEL PERIODO\n")
        csv_buffer.write("="*60 + "\n")
        csv_buffer.write("\n")
        
        if gastos:
            writer.writerow(['Codigo Gasto', 'Fecha', 'Descripcion', 'Categoria', 'Monto', 'Registrado Por'])
            for gasto in gastos:
                writer.writerow([
                    gasto.get('codigo_gasto', ''),
                    gasto.get('fecha', ''),
                    normalizar_texto(gasto.get('descripcion', '')),
                    normalizar_texto(gasto.get('categoria', '')),
                    f"{float(gasto.get('monto', 0)):.2f}",
                    gasto.get('created_by', '')
                ])
        else:
            writer.writerow(['No hay gastos en el periodo seleccionado'])
        
        csv_buffer.write("\n")
        
        csv_content = csv_buffer.getvalue()
        
        # =================================================================
        # GUARDAR EN S3
        # =================================================================
        
        fecha_str = fecha_actual[:10].replace('-', '') + '_' + fecha_actual[11:19].replace(':', '')
        s3_key = f"{tenant_id}/reportes/general_{codigo_reporte}_{fecha_str}.csv"
        
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=csv_content.encode('utf-8'),
            ContentType='text/csv',
            ContentDisposition=f'attachment; filename="general_{codigo_reporte}.csv"'
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
            "tipo": "general",
            "formato": "CSV",
            "fecha_generacion": fecha_actual,
            "parametros": {
                "fecha_inicio": fecha_inicio.strftime('%Y-%m-%d'),
                "fecha_fin": fecha_fin.strftime('%Y-%m-%d'),
                "total_ingresos": total_ingresos,
                "total_egresos": total_egresos,
                "balance": balance
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
                REPORTES_TABLE,
                tenant_id=tenant_id,
                entity_id=codigo_reporte,
                data=reporte_data
            )
            logger.info(f"✅ Reporte guardado en t_reportes: {codigo_reporte}")
        except Exception as db_error:
            logger.error(f"❌ ERROR guardando en DynamoDB: {str(db_error)}")
            logger.error(f"Detalles - Table: {REPORTES_TABLE}, tenant_id: {tenant_id}, entity_id: {codigo_reporte}")
        
        logger.info(f"✅ Reporte general generado: {codigo_reporte}")
        
        return success_response(data={
            "codigo_reporte": codigo_reporte,
            "download_url": download_url
        })
        
    except Exception as e:
        logger.error(f"Error generando reporte general: {str(e)}")
        return error_response("Error interno del servidor", 500)
