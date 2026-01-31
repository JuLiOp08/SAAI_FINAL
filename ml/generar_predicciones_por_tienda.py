"""
Lambda: GenerarPrediccionesPorTienda
Trigger: SQS (1 mensaje = 1 tienda)
Responsabilidad: Generar predicciones para TODOS los productos de 1 tienda
"""

import boto3
import json
import os
from datetime import datetime, timedelta
from utils import query_by_tenant, put_item_standard, get_item_standard, obtener_fecha_hora_peru
from ml.utils_ml import calcular_prediccion_simple, calcular_alerta

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
sns = boto3.client('sns')
lambda_client = boto3.client('lambda')

ALERTAS_SNS_TOPIC_ARN = os.environ.get('ALERTAS_SNS_TOPIC_ARN')
EMITIR_EVENTOS_WS_FUNCTION = os.environ.get('EMITIR_EVENTOS_WS_FUNCTION_NAME')
BUCKET_MODELOS = os.environ.get('BUCKET_MODELOS', 'saai-modelos-ml')

def handler(event, context):
    """
    Procesa 1 tienda completa desde SQS
    
    SQS event: {"Records": [{"body": '{"tenant_id": "T001"}'}]}
    """
    try:
        # 1. Extraer tenant_id del mensaje SQS
        for record in event['Records']:
            body = json.loads(record['body'])
            tenant_id = body['tenant_id']
            
            print(f"🚀 Procesando tienda: {tenant_id}")
            
            # 2. Listar productos activos de la tienda
            productos = listar_productos_tienda(tenant_id)
            
            if not productos:
                print(f"⚠️ Tienda {tenant_id} no tiene productos activos")
                continue
            
            estadisticas = {
                'total_productos': 0,
                'productos_con_ia': 0,
                'productos_con_formula': 0,
                'productos_omitidos': 0,
                'alertas_generadas': 0
            }
            
            # 3. Procesar cada producto
            for codigo_producto in productos:
                try:
                    prediccion = calcular_prediccion_producto(tenant_id, codigo_producto)
                    
                    if prediccion:
                        # Guardar en t_predicciones
                        guardar_prediccion(tenant_id, codigo_producto, prediccion)
                        
                        estadisticas['total_productos'] += 1
                        if prediccion['metodo'] == 'HOLT_WINTERS':
                            estadisticas['productos_con_ia'] += 1
                        else:
                            estadisticas['productos_con_formula'] += 1
                        
                        # Publicar alerta SNS si crítico
                        alerta = calcular_alerta(
                            stock_actual=prediccion.get('stock_snapshot', 0),
                            demanda_manana=prediccion['demanda_manana'],
                            demanda_semana=prediccion['demanda_proxima_semana']
                        )
                        
                        if alerta == 'STOCK_CRITICO_MANANA':
                            publicar_alerta_sns(tenant_id, codigo_producto, prediccion)
                            estadisticas['alertas_generadas'] += 1
                    else:
                        estadisticas['productos_omitidos'] += 1
                
                except Exception as e:
                    print(f"❌ Error en {codigo_producto}: {str(e)}")
                    estadisticas['productos_omitidos'] += 1
            
            # 4. Emitir 1 evento WebSocket para toda la tienda
            try:
                invocar_emitir_eventos_ws({
                    'tipo': 'predicciones_actualizadas',
                    'tenant_id': tenant_id,
                    'timestamp': datetime.now().isoformat(),
                    'resumen': estadisticas
                })
            except Exception as e:
                print(f"⚠️ Error al emitir evento WS: {str(e)}")
            
            print(f"✅ Tienda {tenant_id} procesada: {estadisticas}")
        
        return {'statusCode': 200, 'estadisticas': estadisticas}
    
    except Exception as e:
        print(f"❌ Error en worker: {str(e)}")
        raise  # Reenviar a DLQ después de 3 intentos


def listar_productos_tienda(tenant_id):
    """
    Lista códigos de productos activos de una tienda
    
    Returns:
        list[str]: Lista de entity_id (codigos de producto)
    """
    response = query_by_tenant('t_productos', tenant_id, include_inactive=False)
    return [item['entity_id'] for item in response.get('items', [])]


def calcular_prediccion_producto(tenant_id, codigo_producto):
    """
    Calcula predicción para 1 producto
    
    Returns:
        dict | None: Predicción o None si no hay datos suficientes
    """
    # 1. Obtener ventas históricas (últimos 90 días)
    ventas = obtener_ventas_historicas(tenant_id, codigo_producto, dias=90)
    
    if not ventas or len(ventas) < 5:  # Mínimo 5 ventas
        print(f"⚠️ {codigo_producto}: datos insuficientes ({len(ventas) if ventas else 0} ventas)")
        return None
    
    # 2. Elegir método según cantidad de datos
    if len(ventas) >= 30:
        # Método IA: Holt-Winters
        modelo = cargar_modelo_s3(tenant_id, codigo_producto)
        if not modelo:
            print(f"⚠️ {codigo_producto}: modelo no existe en S3, usando fórmula...")
            resultado = calcular_prediccion_simple(ventas, dias_forecast=7)
            demanda_manana = resultado['demanda_manana']
            demanda_semana = resultado['demanda_proxima_semana']
            metodo = resultado['metodo']
            confianza = resultado['confianza']
        else:
            forecast = modelo.forecast(steps=7)
            demanda_manana = max(0, int(round(forecast[0])))
            demanda_semana = max(0, int(round(forecast.sum())))
            metodo = 'HOLT_WINTERS'
            confianza = 0.92  # Alta confianza con IA
    else:
        # Método fórmula: Weighted Average
        resultado = calcular_prediccion_simple(ventas, dias_forecast=7)
        demanda_manana = resultado['demanda_manana']
        demanda_semana = resultado['demanda_proxima_semana']
        metodo = resultado['metodo']
        confianza = resultado['confianza']
    
    # 3. Obtener stock actual (para snapshot opcional)
    producto = get_item_standard('t_productos', tenant_id, codigo_producto)
    stock_actual = int(producto.get('stock', 0)) if producto else 0
    
    return {
        'demanda_manana': demanda_manana,
        'demanda_proxima_semana': demanda_semana,
        'metodo': metodo,
        'confianza': confianza,
        'stock_snapshot': stock_actual,  # Snapshot, NO usar para alertas en lectura
        'fecha_prediccion': obtener_fecha_hora_peru()
    }


def obtener_ventas_historicas(tenant_id, codigo_producto, dias=90):
    """
    Obtiene ventas históricas de un producto
    
    NOTA: t_ventas NO tiene GSI por producto. Se usa query_by_tenant
    y se filtra en memoria por codigo_producto.
    
    Returns:
        list[dict]: Lista con {cantidad_vendida, fecha_venta}
    """
    from datetime import datetime, timedelta
    
    fecha_inicio = (datetime.now() - timedelta(days=dias)).isoformat()
    
    try:
        # Query todas las ventas de la tienda (sin GSI)
        response = query_by_tenant('t_ventas', tenant_id, include_inactive=False)
        ventas = response.get('items', [])
        
        # Filtrar en memoria: por producto y fecha
        ventas_producto = []
        for venta in ventas:
            # venta.items es array de productos vendidos
            items_venta = venta.get('items', [])
            fecha_venta = venta.get('fecha_venta', '')
            
            # Filtrar por fecha
            if fecha_venta < fecha_inicio:
                continue
            
            # Buscar producto en items
            for item in items_venta:
                if item.get('codigo_producto') == codigo_producto:
                    ventas_producto.append({
                        'cantidad_vendida': int(item.get('cantidad', 0)),
                        'fecha_venta': fecha_venta
                    })
        
        return ventas_producto
    
    except Exception as e:
        print(f"Error al obtener ventas: {str(e)}")
        return []


def cargar_modelo_s3(tenant_id, codigo_producto):
    """
    Carga modelo Holt-Winters desde S3
    
    Returns:
        HoltWinters model | None
    """
    try:
        import pickle
        
        key = f"{tenant_id}/{codigo_producto}/modelo_holt_winters.pkl"
        obj = s3.get_object(Bucket=BUCKET_MODELOS, Key=key)
        modelo = pickle.loads(obj['Body'].read())
        
        return modelo
    except Exception as e:
        print(f"Modelo no encontrado en S3: {str(e)}")
        return None


def guardar_prediccion(tenant_id, codigo_producto, prediccion):
    """
    Guarda predicción en t_predicciones con TTL
    
    IMPORTANTE: put_item_standard crea estructura:
    {tenant_id: X, entity_id: Y, data: {...}}
    Por lo tanto, NO incluir tenant_id ni entity_id dentro de data
    """
    ttl = int((datetime.now() + timedelta(hours=36)).timestamp())
    
    data = {
        'demanda_manana': prediccion['demanda_manana'],
        'demanda_proxima_semana': prediccion['demanda_proxima_semana'],
        'metodo': prediccion['metodo'],
        'confianza': prediccion['confianza'],
        'fecha_prediccion': prediccion['fecha_prediccion'],
        'ttl': ttl,
        'estado': 'ACTIVO'
    }
    
    # put_item_standard agrega tenant_id y entity_id automáticamente
    put_item_standard('t_predicciones', tenant_id, codigo_producto, data)


def publicar_alerta_sns(tenant_id, codigo_producto, prediccion):
    """
    Publica alerta crítica en SNS según SAAI_oficial.txt
    
    Tipo de alerta: stockBajoManana (CRITICAL)
    Dirigido a: correo admin + notificaciones
    """
    try:
        # Obtener nombre producto para mensaje
        producto = get_item_standard('t_productos', tenant_id, codigo_producto)
        nombre_producto = producto.get('nombre', 'Producto desconocido') if producto else 'Producto desconocido'
        
        mensaje = {
            'tipo': 'stockBajoManana',  # Tipo oficial según SAAI_oficial.txt
            'titulo': f'Stock Crítico: {nombre_producto}',
            'mensaje': f'El producto {nombre_producto} tiene stock insuficiente para la demanda de mañana',
            'detalle': {
                'codigo_producto': codigo_producto,
                'nombre_producto': nombre_producto,
                'stock_actual': prediccion.get('stock_snapshot', 0),
                'demanda_manana': prediccion['demanda_manana'],
                'demanda_proxima_semana': prediccion['demanda_proxima_semana']
            }
        }
        
        # Publicar a SNS con MessageAttributes para filtrado
        sns.publish(
            TopicArn=ALERTAS_SNS_TOPIC_ARN,
            Subject=f"⚠️ Stock Crítico: {nombre_producto}",
            Message=json.dumps(mensaje),
            MessageAttributes={
                'tenant_id': {'DataType': 'String', 'StringValue': tenant_id},
                'severidad': {'DataType': 'String', 'StringValue': 'CRITICAL'},
                'tipo': {'DataType': 'String', 'StringValue': 'stockBajoManana'}
            }
        )
        print(f"✅ Alerta SNS publicada: {codigo_producto}")
    except Exception as e:
        print(f"Error al publicar SNS: {str(e)}")


def invocar_emitir_eventos_ws(evento):
    """
    Invoca lambda EmitirEventosWs para notificar frontend
    """
    try:
        lambda_client.invoke(
            FunctionName=EMITIR_EVENTOS_WS_FUNCTION,
            InvocationType='Event',  # Asíncrono
            Payload=json.dumps(evento)
        )
    except Exception as e:
        print(f"Error al invocar EmitirEventosWs: {str(e)}")
