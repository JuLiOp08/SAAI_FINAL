# reports/generar_reporte_gastos.py
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
    POST /reportes/gastos
    
    Genera reporte Excel de gastos del período.
    Guarda en S3 + registra en t_reportes.
    
    Request: { "body": { "fecha_inicio": "2025-11-01", "fecha_fin": "2025-11-08" } }
    Response: {
      "success": true,
      "data": {
        "codigo_reporte": "R003",
        "download_url": "https://s3.amazonaws.com/.../gastos.xlsx"
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
            fecha_fin = datetime.fromisoformat(fecha_actual[:10])
            fecha_inicio = fecha_fin - timedelta(days=6)
        
        if fecha_inicio > fecha_fin:
            return error_response("Fecha inicio no puede ser mayor a fecha fin", 400)
        
        logger.info(f"📋 Generando reporte gastos: {tenant_id} ({fecha_inicio.strftime('%Y-%m-%d')} - {fecha_fin.strftime('%Y-%m-%d')})")
        
        # =================================================================
        # OBTENER DATOS DE GASTOS
        # =================================================================
        
        result = query_by_tenant(os.environ['GASTOS_TABLE'], tenant_id)
        todos_gastos = result.get('items', [])
        
        # Filtrar por fechas en Python
        gastos = []
        for gasto in todos_gastos:
            fecha_gasto = gasto.get('fecha', '')[:10]  # YYYY-MM-DD
            if (fecha_inicio.strftime('%Y-%m-%d') <= fecha_gasto <= fecha_fin.strftime('%Y-%m-%d')):
                gastos.append(gasto)
        
        if not gastos:
            return error_response("No hay gastos en el período seleccionado", 400)
        
        # =================================================================
        # GENERAR CÓDIGO DE REPORTE CON TIENDA
        # =================================================================
        
        contador = increment_counter(os.environ['COUNTERS_TABLE'], tenant_id, 'REPORTES')
        codigo_reporte = f"{tenant_id}R{contador:03d}"
        
        # =================================================================
        # CONSTRUIR DATOS EXCEL
        # =================================================================
        
        datos_gastos = []
        datos_categorias = {}
        datos_mensuales = {}
        total_gastos = len(gastos)
        total_egresos = 0
        
        for gasto in gastos:
            monto = float(gasto.get('monto', 0))
            total_egresos += monto
            
            fecha_gasto = gasto.get('fecha', '')
            categoria = gasto.get('categoria', 'Sin categoría')
            
            # Datos de gasto individual
            datos_gastos.append({
                'Código Gasto': gasto.get('codigo_gasto', ''),
                'Fecha': fecha_gasto,
                'Descripción': gasto.get('descripcion', ''),
                'Categoría': categoria,
                'Monto': monto,
                'Registrado Por': gasto.get('codigo_usuario', ''),
                'Estado': gasto.get('estado', 'ACTIVO'),
                'Fecha Registro': gasto.get('created_at', '')[:10] if gasto.get('created_at') else ''
            })
            
            # Acumular por categoría
            if categoria not in datos_categorias:
                datos_categorias[categoria] = {'Cantidad': 0, 'Total': 0}
            
            datos_categorias[categoria]['Cantidad'] += 1
            datos_categorias[categoria]['Total'] += monto
            
            # Acumular por mes
            if fecha_gasto:
                mes = fecha_gasto[:7]  # YYYY-MM
                if mes not in datos_mensuales:
                    datos_mensuales[mes] = {'Cantidad': 0, 'Total': 0}
                
                datos_mensuales[mes]['Cantidad'] += 1
                datos_mensuales[mes]['Total'] += monto
        
        # =================================================================
        # CREAR EXCEL CON PANDAS
        # =================================================================
        
        # DataFrames
        df_gastos = pd.DataFrame(datos_gastos)
        df_gastos = df_gastos.sort_values('Fecha', ascending=False)  # Más recientes primero
        
        df_categorias = pd.DataFrame([
            {
                'Categoría': cat, 
                'Cantidad Gastos': data['Cantidad'], 
                'Total Monto': data['Total'],
                'Porcentaje': (data['Total'] / total_egresos * 100) if total_egresos > 0 else 0
            }
            for cat, data in datos_categorias.items()
        ])
        df_categorias = df_categorias.sort_values('Total Monto', ascending=False)
        
        df_mensuales = pd.DataFrame([
            {'Mes': mes, 'Cantidad Gastos': data['Cantidad'], 'Total Monto': data['Total']}
            for mes, data in sorted(datos_mensuales.items())
        ])
        
        df_resumen = pd.DataFrame([
            {'Métrica': 'Período', 'Valor': f"{fecha_inicio.strftime('%Y-%m-%d')} - {fecha_fin.strftime('%Y-%m-%d')}"},
            {'Métrica': 'Total Gastos', 'Valor': total_gastos},
            {'Métrica': 'Total Egresos', 'Valor': f"S/ {total_egresos:.2f}"},
            {'Métrica': 'Promedio por Gasto', 'Valor': f"S/ {total_egresos/total_gastos:.2f}" if total_gastos > 0 else 'S/ 0.00'},
            {'Métrica': 'Categorías Únicas', 'Valor': len(datos_categorias)},
            {'Métrica': 'Mayor Gasto', 'Valor': f"S/ {max([float(g.get('monto', 0)) for g in gastos]):.2f}" if gastos else 'S/ 0.00'},
            {'Métrica': 'Fecha Generación', 'Valor': fecha_actual[:19]}
        ])
        
        # =================================================================
        # GUARDAR EN S3
        # =================================================================
        
        excel_buffer = BytesIO()
        
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            # Hojas del reporte
            df_gastos.to_excel(writer, sheet_name='Gastos', index=False)
            df_categorias.to_excel(writer, sheet_name='Por Categoría', index=False)
            df_mensuales.to_excel(writer, sheet_name='Por Mes', index=False)
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
        fecha_str = fecha_actual[:10].replace('-', '') + '_' + fecha_actual[11:19].replace(':', '')
        s3_key = f"{tenant_id}/reportes/gastos_{codigo_reporte}_{fecha_str}.xlsx"
        
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
            "tipo": "gastos",
            "fecha_generacion": fecha_actual,
            "parametros": {
                "fecha_inicio": fecha_inicio.strftime('%Y-%m-%d'),
                "fecha_fin": fecha_fin.strftime('%Y-%m-%d'),
                "total_gastos": total_gastos,
                "total_egresos": total_egresos
            },
            "s3_bucket": S3_BUCKET,
            "s3_key": s3_key,
            "tamaño_bytes": len(excel_buffer.getvalue()),
            "generado_por": codigo_usuario,
            "estado": "COMPLETADO",
            "created_at": fecha_actual
        }
        
        put_item_standard(
            os.environ['REPORTES_TABLE'],
            tenant_id=tenant_id,
            entity_id=codigo_reporte,
            data=reporte_data
        )
        
        logger.info(f"✅ Reporte gastos generado: {codigo_reporte}")
        
        return success_response(data={
            "codigo_reporte": codigo_reporte,
            "download_url": download_url
        })
        
    except Exception as e:
        logger.error(f"Error generando reporte gastos: {str(e)}")
        return error_response("Error interno del servidor", 500)