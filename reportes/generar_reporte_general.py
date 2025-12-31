# reports/generar_reporte_general.py
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
    POST /reportes/general
    
    Genera reporte Excel combinado (inventario + ventas + gastos).
    Guarda en S3 + registra en t_reportes.
    
    Request: { "body": { "fecha_inicio": "2025-11-01", "fecha_fin": "2025-11-08" } }
    Response: {
      "success": true,
      "data": {
        "codigo_reporte": "R004",
        "download_url": "https://s3.amazonaws.com/.../general.xlsx"
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
            fecha_fin = lima_now
            fecha_inicio = lima_now - timedelta(days=6)
        
        if fecha_inicio > fecha_fin:
            return error_response("Fecha inicio no puede ser mayor a fecha fin", 400)
        
        logger.info(f"📋 Generando reporte general: {tenant_id} ({fecha_inicio.strftime('%Y-%m-%d')} - {fecha_fin.strftime('%Y-%m-%d')})")
        
        # =================================================================
        # GENERAR CÓDIGO DE REPORTE CON TIENDA
        # =================================================================
        
        contador = increment_counter('SAAI_Counters', tenant_id, 'REPORTES')
        codigo_reporte = f"{tenant_id}R{contador:03d}"
        
        # =================================================================
        # OBTENER TODOS LOS DATOS
        # =================================================================
        
        # INVENTARIO ACTUAL
        inventario_data = obtener_datos_inventario(tenant_id)
        
        # VENTAS DEL PERÍODO
        ventas_data = obtener_datos_ventas(tenant_id, fecha_inicio, fecha_fin)
        
        # GASTOS DEL PERÍODO
        gastos_data = obtener_datos_gastos(tenant_id, fecha_inicio, fecha_fin)
        
        # =================================================================
        # CONSTRUIR DASHBOARD EJECUTIVO
        # =================================================================
        
        total_ingresos = sum(float(v['data'].get('total', 0)) for v in ventas_data)
        total_egresos = sum(float(g['data'].get('monto', 0)) for g in gastos_data)
        balance = total_ingresos - total_egresos
        
        valor_inventario = sum(
            int(p['data'].get('stock', 0)) * float(p['data'].get('precio', 0)) 
            for p in inventario_data
        )
        
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
            {'Métrica': 'Total Productos', 'Valor': len(inventario_data)},
            {'Métrica': 'Productos Sin Stock', 'Valor': len([p for p in inventario_data if int(p['data'].get('stock', 0)) == 0])},
            {'Métrica': 'Total Ventas', 'Valor': len(ventas_data)},
            {'Métrica': 'Promedio Venta', 'Valor': f"S/ {total_ingresos/len(ventas_data):.2f}" if ventas_data else 'S/ 0.00'},
            {'Métrica': 'Total Gastos', 'Valor': len(gastos_data)},
            {'Métrica': 'Promedio Gasto', 'Valor': f"S/ {total_egresos/len(gastos_data):.2f}" if gastos_data else 'S/ 0.00'},
            {'Métrica': '', 'Valor': ''},
            {'Métrica': 'FECHA GENERACIÓN', 'Valor': lima_now.strftime('%Y-%m-%d %H:%M:%S')}
        ])
        
        # =================================================================
        # CONSTRUIR HOJAS DETALLADAS
        # =================================================================
        
        # Inventario
        df_inventario = construir_df_inventario(inventario_data)
        
        # Ventas
        df_ventas = construir_df_ventas(ventas_data)
        
        # Gastos
        df_gastos = construir_df_gastos(gastos_data)
        
        # Productos más vendidos
        df_productos_top = construir_df_productos_top(ventas_data)
        
        # Análisis de rentabilidad por categoría
        df_rentabilidad = construir_df_rentabilidad(inventario_data, ventas_data)
        
        # =================================================================
        # CREAR EXCEL CON PANDAS
        # =================================================================
        
        excel_buffer = BytesIO()
        
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            # Dashboard ejecutivo (primera hoja)
            df_dashboard.to_excel(writer, sheet_name='Dashboard', index=False)
            
            # Hojas detalladas
            if not df_inventario.empty:
                df_inventario.to_excel(writer, sheet_name='Inventario', index=False)
            
            if not df_ventas.empty:
                df_ventas.to_excel(writer, sheet_name='Ventas', index=False)
            
            if not df_gastos.empty:
                df_gastos.to_excel(writer, sheet_name='Gastos', index=False)
            
            if not df_productos_top.empty:
                df_productos_top.to_excel(writer, sheet_name='Productos Top', index=False)
            
            if not df_rentabilidad.empty:
                df_rentabilidad.to_excel(writer, sheet_name='Rentabilidad', index=False)
            
            # Formatear todas las hojas
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
        
        fecha_str = lima_now.strftime('%Y%m%d_%H%M%S')
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
            "fecha_generacion": lima_now.isoformat(),
            "parametros": {
                "fecha_inicio": fecha_inicio.strftime('%Y-%m-%d'),
                "fecha_fin": fecha_fin.strftime('%Y-%m-%d'),
                "total_ingresos": total_ingresos,
                "total_egresos": total_egresos,
                "balance": balance,
                "valor_inventario": valor_inventario
            },
            "s3_bucket": S3_BUCKET,
            "s3_key": s3_key,
            "tamaño_bytes": len(excel_buffer.getvalue()),
            "generado_por": codigo_usuario,
            "estado": "COMPLETADO",
            "created_at": lima_now.isoformat()
        }
        
        reportes_table.put_item(Item={
            'tenant_id': tenant_id,
            'entity_id': codigo_reporte,
            'data': reporte_data
        })
        
        logger.info(f"✅ Reporte general generado: {codigo_reporte}")
        
        return success_response(data={
            "codigo_reporte": codigo_reporte,
            "download_url": download_url
        })
        
    except Exception as e:
        logger.error(f"Error generando reporte general: {str(e)}")
        return error_response("Error interno del servidor", 500)

# =================================================================
# FUNCIONES AUXILIARES
# =================================================================

def obtener_datos_inventario(tenant_id):
    """Obtiene todos los productos activos"""
    try:
        response = productos_table.query(
            KeyConditionExpression=Key('tenant_id').eq(tenant_id),
            FilterExpression='#data.#estado = :estado',
            ExpressionAttributeNames={'#data': 'data', '#estado': 'estado'},
            ExpressionAttributeValues={':estado': 'ACTIVO'}
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error obteniendo inventario: {str(e)}")
        return []

def obtener_datos_ventas(tenant_id, fecha_inicio, fecha_fin):
    """Obtiene ventas del período"""
    try:
        response = ventas_table.query(
            KeyConditionExpression=Key('tenant_id').eq(tenant_id),
            FilterExpression='#data.#fecha BETWEEN :inicio AND :fin AND #data.#estado = :estado',
            ExpressionAttributeNames={'#data': 'data', '#fecha': 'fecha', '#estado': 'estado'},
            ExpressionAttributeValues={
                ':inicio': fecha_inicio.strftime('%Y-%m-%d'),
                ':fin': fecha_fin.strftime('%Y-%m-%d'),
                ':estado': 'COMPLETADA'  # Cambiar de 'ACTIVO' a 'COMPLETADA'
            }
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error obteniendo ventas: {str(e)}")
        return []

def obtener_datos_gastos(tenant_id, fecha_inicio, fecha_fin):
    """Obtiene gastos del período"""
    try:
        response = gastos_table.query(
            KeyConditionExpression=Key('tenant_id').eq(tenant_id),
            FilterExpression='#data.#fecha BETWEEN :inicio AND :fin AND #data.#estado = :estado',
            ExpressionAttributeNames={'#data': 'data', '#fecha': 'fecha', '#estado': 'estado'},
            ExpressionAttributeValues={
                ':inicio': fecha_inicio.strftime('%Y-%m-%d'),
                ':fin': fecha_fin.strftime('%Y-%m-%d'),
                ':estado': 'ACTIVO'
            }
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error obteniendo gastos: {str(e)}")
        return []

def construir_df_inventario(inventario_data):
    """Construye DataFrame de inventario"""
    if not inventario_data:
        return pd.DataFrame()
    
    datos = []
    for producto in inventario_data:
        data = producto['data']
        stock = int(data.get('stock', 0))
        precio = float(data.get('precio', 0))
        
        estado_stock = "SIN STOCK" if stock == 0 else ("BAJO STOCK" if stock <= 5 else "NORMAL")
        
        datos.append({
            'Código': data.get('codigo_producto', ''),
            'Nombre': data.get('nombre', ''),
            'Categoría': data.get('categoria', ''),
            'Stock': stock,
            'Precio': precio,
            'Valor Total': stock * precio,
            'Estado': estado_stock
        })
    
    return pd.DataFrame(datos)

def construir_df_ventas(ventas_data):
    """Construye DataFrame de ventas"""
    if not ventas_data:
        return pd.DataFrame()
    
    datos = []
    for venta in ventas_data:
        data = venta['data']
        datos.append({
            'Código': data.get('codigo_venta', ''),
            'Fecha': data.get('fecha', ''),  # Ya es sólo fecha YYYY-MM-DD
            'Cliente': data.get('cliente', ''),
            'Total': float(data.get('total', 0)),
            'Método Pago': data.get('metodo_pago', ''),
            'Items': len(data.get('productos', [])),  # Cambiar de 'items' a 'productos'
            'Vendedor': data.get('codigo_usuario', ''),
            'Estado': data.get('estado', 'COMPLETADA')
        })
    
    return pd.DataFrame(datos)

def construir_df_gastos(gastos_data):
    """Construye DataFrame de gastos"""
    if not gastos_data:
        return pd.DataFrame()
    
    datos = []
    for gasto in gastos_data:
        data = gasto['data']
        datos.append({
            'Código': data.get('codigo_gasto', ''),
            'Fecha': data.get('fecha', ''),
            'Descripción': data.get('descripcion', ''),
            'Categoría': data.get('categoria', ''),
            'Monto': float(data.get('monto', 0)),
            'Registrado Por': data.get('codigo_usuario', ''),  # Este campo sí existe en gastos
            'Estado': data.get('estado', 'ACTIVO')
        })
    
    return pd.DataFrame(datos)

def construir_df_productos_top(ventas_data):
    """Construye DataFrame de productos más vendidos"""
    if not ventas_data:
        return pd.DataFrame()
    
    productos_vendidos = {}
    
    for venta in ventas_data:
        for producto in venta['data'].get('productos', []):  # Cambiar de 'items' a 'productos'
            codigo = producto.get('codigo_producto', '')
            nombre = producto.get('nombre_producto', codigo)  # Cambiar de 'nombre' a 'nombre_producto'
            cantidad = int(producto.get('cantidad', 0))
            precio = float(producto.get('precio_unitario', 0))
            
            if codigo not in productos_vendidos:
                productos_vendidos[codigo] = {
                    'Código': codigo,
                    'Nombre': nombre,
                    'Cantidad Vendida': 0,
                    'Ingresos Total': 0
                }
            
            productos_vendidos[codigo]['Cantidad Vendida'] += cantidad
            productos_vendidos[codigo]['Ingresos Total'] += producto.get('subtotal_item', cantidad * precio)
    
    df = pd.DataFrame(list(productos_vendidos.values()))
    if not df.empty:
        df = df.sort_values('Cantidad Vendida', ascending=False).head(10)
    
    return df

def construir_df_rentabilidad(inventario_data, ventas_data):
    """Construye análisis de rentabilidad por categoría"""
    if not inventario_data or not ventas_data:
        return pd.DataFrame()
    
    # Agrupar productos por categoría
    categorias = {}
    
    for producto in inventario_data:
        data = producto['data']
        categoria = data.get('categoria', 'Sin categoría')
        stock = int(data.get('stock', 0))
        precio = float(data.get('precio', 0))
        
        if categoria not in categorias:
            categorias[categoria] = {
                'Productos': 0,
                'Valor Inventario': 0,
                'Ventas': 0,
                'Ingresos': 0
            }
        
        categorias[categoria]['Productos'] += 1
        categorias[categoria]['Valor Inventario'] += stock * precio
    
    # Agregar datos de ventas
    for venta in ventas_data:
        for producto in venta['data'].get('productos', []):  # Cambiar de 'items' a 'productos'
            # Buscar categoría del producto (simplificado)
            codigo = producto.get('codigo_producto', '')
            categoria = 'Sin categoría'  # Default
            
            # Encontrar categoría real del producto
            for inv_producto in inventario_data:
                if inv_producto['data'].get('codigo_producto') == codigo:
                    categoria = inv_producto['data'].get('categoria', 'Sin categoría')
                    break
            
            cantidad = int(producto.get('cantidad', 0))
            precio = float(producto.get('precio_unitario', 0))
            
            if categoria not in categorias:
                categorias[categoria] = {
                    'Productos': 0,
                    'Valor Inventario': 0,
                    'Ventas': 0,
                    'Ingresos': 0
                }
            
            categorias[categoria]['Ventas'] += cantidad
            categorias[categoria]['Ingresos'] += cantidad * precio
    
    # Construir DataFrame
    datos = []
    for categoria, stats in categorias.items():
        datos.append({
            'Categoría': categoria,
            'Productos': stats['Productos'],
            'Valor Inventario': stats['Valor Inventario'],
            'Unidades Vendidas': stats['Ventas'],
            'Ingresos Ventas': stats['Ingresos'],
            'Rotación': (stats['Ventas'] / stats['Productos']) if stats['Productos'] > 0 else 0
        })
    
    df = pd.DataFrame(datos)
    if not df.empty:
        df = df.sort_values('Ingresos Ventas', ascending=False)
    
    return df