# reportes/generar_reporte_general.py
import os
import json
import logging
import boto3
from datetime import datetime, timedelta
from io import BytesIO
import pandas as pd
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
    increment_counter
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
        # CONSTRUIR DASHBOARD EJECUTIVO
        # =================================================================
        
        df_dashboard = pd.DataFrame([
            {'Métrica': 'PERÍODO ANALIZADO', 'Valor': f"{fecha_inicio.strftime('%Y-%m-%d')} - {fecha_fin.strftime('%Y-%m-%d')}"},
            {'Métrica': '', 'Valor': ''},
            {'Métrica': 'RESUMEN FINANCIERO', 'Valor': ''},
            {'Métrica': 'Total Ingresos (Ventas)', 'Valor': f"S/ {total_ingresos:.2f}"},
            {'Métrica': 'Total Egresos (Gastos)', 'Valor': f"S/ {total_egresos:.2f}"},
            {'Métrica': 'Balance Neto', 'Valor': f"S/ {balance:.2f}"},
            {'Métrica': 'Valor Inventario Actual', 'Valor': f"S/ {valor_inventario:.2f}"},
            {'Métrica': '', 'Valor': ''},
            {'Métrica': 'INDICADORES OPERATIVOS', 'Valor': ''},
            {'Métrica': 'Total Productos', 'Valor': len(productos)},
            {'Métrica': 'Productos Sin Stock', 'Valor': productos_sin_stock},
            {'Métrica': 'Productos Bajo Stock (≤5)', 'Valor': productos_bajo_stock},
            {'Métrica': 'Total Ventas', 'Valor': len(ventas)},
            {'Métrica': 'Promedio por Venta', 'Valor': f"S/ {total_ingresos/len(ventas):.2f}" if ventas else 'S/ 0.00'},
            {'Métrica': 'Total Gastos', 'Valor': len(gastos)},
            {'Métrica': 'Promedio por Gasto', 'Valor': f"S/ {total_egresos/len(gastos):.2f}" if gastos else 'S/ 0.00'},
            {'Métrica': '', 'Valor': ''},
            {'Métrica': 'FECHA GENERACIÓN', 'Valor': fecha_actual[:19]}
        ])
        
        # =================================================================
        # CONSTRUIR DETALLE DE INVENTARIO
        # =================================================================
        
        datos_inventario = []
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
            
            datos_inventario.append({
                'Código': producto.get('codigo_producto', ''),
                'Nombre': producto.get('nombre', ''),
                'Categoría': producto.get('categoria', ''),
                'Precio': precio,
                'Stock': stock,
                'Estado Stock': estado_stock,
                'Valor Total': valor_total
            })
        
        df_inventario = pd.DataFrame(datos_inventario) if datos_inventario else pd.DataFrame()
        
        # =================================================================
        # CONSTRUIR DETALLE DE VENTAS
        # =================================================================
        
        datos_ventas = []
        for venta in ventas:
            datos_ventas.append({
                'Código Venta': venta.get('codigo_venta', ''),
                'Fecha': venta.get('fecha', ''),
                'Cliente': venta.get('cliente', ''),
                'Total': float(venta.get('total', 0)),
                'Método Pago': venta.get('metodo_pago', ''),
                'Vendedor': venta.get('codigo_usuario', '')
            })
        
        df_ventas = pd.DataFrame(datos_ventas) if datos_ventas else pd.DataFrame()
        
        # =================================================================
        # CONSTRUIR DETALLE DE GASTOS
        # =================================================================
        
        datos_gastos = []
        for gasto in gastos:
            datos_gastos.append({
                'Código Gasto': gasto.get('codigo_gasto', ''),
                'Fecha': gasto.get('fecha', ''),
                'Descripción': gasto.get('descripcion', ''),
                'Categoría': gasto.get('categoria', ''),
                'Monto': float(gasto.get('monto', 0)),
                'Registrado Por': gasto.get('created_by', '')
            })
        
        df_gastos = pd.DataFrame(datos_gastos) if datos_gastos else pd.DataFrame()
        
        # =================================================================
        # CREAR EXCEL CON PANDAS
        # =================================================================
        
        excel_buffer = BytesIO()
        
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            # Hoja 1: Dashboard Ejecutivo
            df_dashboard.to_excel(writer, sheet_name='Dashboard', index=False)
            
            # Hoja 2: Inventario (si hay datos)
            if not df_inventario.empty:
                df_inventario.to_excel(writer, sheet_name='Inventario', index=False)
            
            # Hoja 3: Ventas (si hay datos)
            if not df_ventas.empty:
                df_ventas.to_excel(writer, sheet_name='Ventas', index=False)
            
            # Hoja 4: Gastos (si hay datos)
            if not df_gastos.empty:
                df_gastos.to_excel(writer, sheet_name='Gastos', index=False)
            
            # Formatear columnas en todas las hojas
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
        
        # =================================================================
        # GUARDAR EN S3
        # =================================================================
        
        fecha_str = fecha_actual[:10].replace('-', '') + '_' + fecha_actual[11:19].replace(':', '')
        s3_key = f"{tenant_id}/reportes/general_{codigo_reporte}_{fecha_str}.xlsx"
        
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
            "tipo": "general",
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
            "tamaño_bytes": len(excel_buffer.getvalue()),
            "generado_por": codigo_usuario,
            "estado": "COMPLETADO",
            "created_at": fecha_actual
        }
        
        put_item_standard(
            REPORTES_TABLE,
            tenant_id=tenant_id,
            entity_id=codigo_reporte,
            data=reporte_data
        )
        
        logger.info(f"✅ Reporte general generado: {codigo_reporte}")
        
        return success_response(data={
            "codigo_reporte": codigo_reporte,
            "download_url": download_url
        })
        
    except Exception as e:
        logger.error(f"Error generando reporte general: {str(e)}")
        return error_response("Error interno del servidor", 500)
