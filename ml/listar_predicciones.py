"""
Lambda: ListarPredicciones
Endpoint: GET /predicciones
Responsabilidad: Listar todas las predicciones de la tienda con enriquecimiento
"""

import boto3
from decimal import Decimal
from utils import query_by_tenant, batch_get_items
from utils.auth_helpers import verificar_rol_permitido, extract_tenant_from_jwt_claims
from utils.response_helpers import success_response, error_response
from ml.utils_ml import calcular_alerta

def handler(event, context):
    """
    Lista predicciones con paginación
    
    Query params:
        - limit (int, optional): 50 por defecto
        - next_token (str, optional): para paginación
    """
    # 1. Autenticación
    tiene_permiso, error = verificar_rol_permitido(event, ['ADMIN'])
    if not tiene_permiso:
        return error
    
    tenant_id = extract_tenant_from_jwt_claims(event)
    
    # 2. Parámetros de paginación
    query_params = event.get('queryStringParameters') or {}
    limit = int(query_params.get('limit', 50))
    next_token = query_params.get('next_token')
    
    try:
        # 3. Query t_predicciones (solo predicciones)
        predicciones = query_by_tenant(
            't_predicciones',
            tenant_id,
            limit=limit,
            next_token=next_token,
            include_inactive=False
        )
        
        items = predicciones.get('items', [])
        
        # 4. BatchGet t_productos (enriquecimiento)
        if items:
            codigos = [p['entity_id'] for p in items]
            productos = batch_get_items('t_productos', tenant_id, codigos)
            
            # 5. Merge + calcular alertas
            for pred in items:
                codigo = pred['entity_id']
                producto = productos.get(codigo, {})
                
                # Enriquecer
                pred['codigo_producto'] = codigo
                pred['nombre_producto'] = producto.get('nombre', 'Producto sin nombre')
                pred['categoria'] = producto.get('categoria', 'Sin categoría')
                pred['stock_actual'] = int(producto.get('stock', 0))
                
                # Calcular alerta con stock ACTUAL
                pred['alerta'] = calcular_alerta(
                    stock_actual=pred['stock_actual'],
                    demanda_manana=int(pred.get('demanda_manana', 0)),
                    demanda_semana=int(pred.get('demanda_proxima_semana', 0))
                )
                
                # Limpiar campos internos
                pred.pop('entity_id', None)
                pred.pop('ttl', None)
                pred.pop('estado', None)
        
        # 6. Calcular resumen
        resumen = {
            'total_productos': len(items),
            'productos_con_ia': sum(1 for p in items if p.get('metodo') == 'HOLT_WINTERS'),
            'productos_con_formula': sum(1 for p in items if p.get('metodo') == 'WEIGHTED_AVERAGE'),
            'productos_alerta_critica': sum(1 for p in items if p.get('alerta') == 'STOCK_CRITICO_MANANA'),
            'productos_alerta_moderada': sum(1 for p in items if p.get('alerta') == 'STOCK_BAJO_SEMANA')
        }
        
        # 7. UX: Mensaje si no hay predicciones (primera ejecución o fallo)
        mensaje = 'Predicciones obtenidas exitosamente'
        if len(items) == 0:
            mensaje = 'Aún no hay predicciones disponibles. Las predicciones se generan automáticamente cada día a las 2:00 AM (hora Perú).'
        
        return success_response(
            mensaje=mensaje,
            data={
                'predicciones': items,
                'resumen': resumen,
                'next_token': predicciones.get('next_token')
            }
        )
    
    except Exception as e:
        print(f"❌ Error al listar predicciones: {str(e)}")
        return error_response(f"Error al obtener predicciones: {str(e)}", 500)
