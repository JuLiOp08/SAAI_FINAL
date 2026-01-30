# reports/generar_reporte_gastos.py
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
        # CONSTRUIR DATOS CSV
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
                'Codigo Gasto': gasto.get('codigo_gasto', ''),
                'Fecha': fecha_gasto,
                'Descripcion': normalizar_texto(gasto.get('descripcion', '')),
                'Categoria': normalizar_texto(categoria),
                'Monto': monto,
                'Registrado Por': gasto.get('codigo_usuario', ''),
                'Estado': gasto.get('estado', 'ACTIVO'),
                'Fecha Registro': gasto.get('created_at', '')[:10] if gasto.get('created_at') else ''
            })
            
            # Acumular por categoría
            categoria_normalizada = normalizar_texto(categoria)
            if categoria_normalizada not in datos_categorias:
                datos_categorias[categoria_normalizada] = {'Cantidad': 0, 'Total': 0}
            
            datos_categorias[categoria_normalizada]['Cantidad'] += 1
            datos_categorias[categoria_normalizada]['Total'] += monto
            
            # Acumular por mes
            if fecha_gasto:
                mes = fecha_gasto[:7]  # YYYY-MM
                if mes not in datos_mensuales:
                    datos_mensuales[mes] = {'Cantidad': 0, 'Total': 0}
                
                datos_mensuales[mes]['Cantidad'] += 1
                datos_mensuales[mes]['Total'] += monto
        
        # Ordenar gastos por fecha (más recientes primero)
        datos_gastos.sort(key=lambda x: x['Fecha'], reverse=True)
        
        # Mayor gasto
        mayor_gasto = max([float(g.get('monto', 0)) for g in gastos]) if gastos else 0
        
        # =================================================================
        # CREAR CSV
        # =================================================================
        
        csv_buffer = StringIO()
        
        # Sección de encabezado
        csv_buffer.write("REPORTE DE GASTOS\n")
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
        writer.writerow(['Total Gastos', total_gastos])
        writer.writerow(['Total Egresos', f"S/ {total_egresos:.2f}"])
        writer.writerow(['Promedio por Gasto', f"S/ {total_egresos/total_gastos:.2f}" if total_gastos > 0 else 'S/ 0.00'])
        writer.writerow(['Categorias Unicas', len(datos_categorias)])
        writer.writerow(['Mayor Gasto', f"S/ {mayor_gasto:.2f}"])
        csv_buffer.write("\n")
        
        # Sección de gastos detallados
        csv_buffer.write("DETALLE DE GASTOS\n")
        writer.writerow(['Codigo Gasto', 'Fecha', 'Descripcion', 'Categoria', 'Monto', 'Registrado Por', 'Estado', 'Fecha Registro'])
        for gasto in datos_gastos:
            writer.writerow([
                gasto['Codigo Gasto'],
                gasto['Fecha'],
                gasto['Descripcion'],
                gasto['Categoria'],
                f"{gasto['Monto']:.2f}",
                gasto['Registrado Por'],
                gasto['Estado'],
                gasto['Fecha Registro']
            ])
        csv_buffer.write("\n")
        
        # Sección de gastos por categoría
        csv_buffer.write("GASTOS POR CATEGORIA\n")
        writer.writerow(['Categoria', 'Cantidad Gastos', 'Total Monto', 'Porcentaje'])
        categorias_sorted = sorted(datos_categorias.items(), key=lambda x: x[1]['Total'], reverse=True)
        for categoria, data in categorias_sorted:
            porcentaje = (data['Total'] / total_egresos * 100) if total_egresos > 0 else 0
            writer.writerow([
                categoria,
                data['Cantidad'],
                f"{data['Total']:.2f}",
                f"{porcentaje:.2f}%"
            ])
        csv_buffer.write("\n")
        
        # Sección de gastos mensuales
        csv_buffer.write("GASTOS POR MES\n")
        writer.writerow(['Mes', 'Cantidad Gastos', 'Total Monto'])
        for mes, data in sorted(datos_mensuales.items()):
            writer.writerow([mes, data['Cantidad'], f"{data['Total']:.2f}"])
        
        csv_content = csv_buffer.getvalue()
        
        # =================================================================
        # GUARDAR EN S3
        # =================================================================
        
        # Subir a S3
        fecha_str = fecha_actual[:10].replace('-', '') + '_' + fecha_actual[11:19].replace(':', '')
        s3_key = f"{tenant_id}/reportes/gastos_{codigo_reporte}_{fecha_str}.csv"
        
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=csv_content.encode('utf-8'),
            ContentType='text/csv',
            ContentDisposition=f'attachment; filename="gastos_{codigo_reporte}.csv"'
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
            "formato": "CSV",
            "fecha_generacion": fecha_actual,
            "parametros": {
                "fecha_inicio": fecha_inicio.strftime('%Y-%m-%d'),
                "fecha_fin": fecha_fin.strftime('%Y-%m-%d'),
                "total_gastos": total_gastos,
                "total_egresos": Decimal(str(round(total_egresos, 2)))
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
        
        logger.info(f"✅ Reporte gastos generado: {codigo_reporte}")
        
        return success_response(data={
            "codigo_reporte": codigo_reporte,
            "download_url": download_url
        })
        
    except Exception as e:
        logger.error(f"Error generando reporte gastos: {str(e)}")
        return error_response("Error interno del servidor", 500)