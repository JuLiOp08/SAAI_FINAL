"""
Lambda: BuscarPredicciones
Endpoint: POST /predicciones/buscar
Responsabilidad: Buscar/filtrar predicciones con criterios
"""

import boto3
from boto3.dynamodb.conditions import Attr, And
from utils import batch_get_items, parse_request_body
from utils.auth_helpers import verificar_rol_permitido, extract_tenant_from_jwt_claims
from utils.response_helpers import success_response, error_response
from ml.utils_ml import calcular_alerta

dynamodb = boto3.resource('dynamodb')

def handler(event, context):
    """
    Busca predicciones con filtros
    
    Body:
        {
            "filtros": {
                "codigo_producto": "T001P005" (opcional),
                "categoria": "Bebidas" (opcional),
                "metodo": "HOLT_WINTERS" (opcional),
                "stock_minimo": 5 (opcional),
                "stock_maximo": 50 (opcional),
                "demanda_minima": 10 (opcional)
            },
            "ordenar_por": "demanda_manana" (opcional),
            "orden": "desc" (opcional),
            "limit": 50 (opcional)
        }
    """
    # 1. Autenticación
    tiene_permiso, error = verificar_rol_permitido(event, ['ADMIN'])
    if not tiene_permiso:
        return error
    
    tenant_id = extract_tenant_from_jwt_claims(event)
    
    try:
        body = parse_request_body(event)
        
        filtros = body.get('filtros', {})
        ordenar_por = body.get('ordenar_por', 'demanda_manana')
        orden = body.get('orden', 'desc')
        limit = body.get('limit', 50)
        
        # 2. Scan t_predicciones con FilterExpression
        # (Nota: Para MVP usamos Scan. Para >1000 productos, migrar a GSI + Query)
        
        # CRÍTICO: SIEMPRE filtrar por tenant_id para seguridad multi-tenant
        filter_expression = build_filter_expression(tenant_id, filtros)
        
        table = dynamodb.Table('t_predicciones')
        response = table.scan(
            FilterExpression=filter_expression,
            Limit=limit * 2  # Sobrecargar porque filtraremos en memoria después
        )
        
        items = response.get('Items', [])
        
        # 3. Enriquecer con t_productos (mismo que ListarPredicciones)
        if items:
            codigos = [p['entity_id'] for p in items]
            productos = batch_get_items('t_productos', tenant_id, codigos)
            
            for pred in items:
                codigo = pred['entity_id']
                producto = productos.get(codigo, {})
                
                pred['codigo_producto'] = codigo
                pred['nombre_producto'] = producto.get('nombre', '')
                pred['categoria'] = producto.get('categoria', '')
                pred['stock_actual'] = int(producto.get('stock', 0))
                
                pred['alerta'] = calcular_alerta(
                    stock_actual=pred['stock_actual'],
                    demanda_manana=int(pred.get('demanda_manana', 0)),
                    demanda_semana=int(pred.get('demanda_proxima_semana', 0))
                )
        
        # 4. Filtrar en memoria por campos de t_productos (categoria, stock)
        items_filtrados = aplicar_filtros_enriquecidos(items, filtros)
        
        # 5. Ordenar DESPUÉS de enriquecimiento (stock_actual ya disponible)
        items_ordenados = sorted(
            items_filtrados,
            key=lambda x: x.get(ordenar_por, 0),
            reverse=(orden == 'desc')
        )
        
        # 6. Paginar
        items_paginados = items_ordenados[:limit]
        
        # Limpiar campos internos
        for pred in items_paginados:
            pred.pop('entity_id', None)
            pred.pop('ttl', None)
            pred.pop('estado', None)
        
        return success_response(
            mensaje=f"Encontrados {len(items_paginados)} productos",
            data={
                'predicciones': items_paginados,
                'total_resultados': len(items_paginados)
            }
        )
    
    except Exception as e:
        print(f"❌ Error al buscar predicciones: {str(e)}")
        return error_response(f"Error al buscar predicciones: {str(e)}", 500)


def build_filter_expression(tenant_id, filtros):
    """
    Construye FilterExpression para DynamoDB Scan
    
    CRÍTICO: SIEMPRE incluye filtro por tenant_id para:
    - Seguridad multi-tenant (no devolver datos de otras tiendas)
    - Reducir costo de scan (aunque sigue siendo scan)
    - Evitar errores de lógica
    
    Args:
        tenant_id (str): ID de la tienda (OBLIGATORIO)
        filtros (dict): Filtros adicionales del request
    
    Returns:
        ConditionExpression: Condición combinada con tenant_id
    """
    conditions = []
    
    # 🔒 OBLIGATORIO: Filtrar por tenant_id (seguridad multi-tenant)
    conditions.append(Attr('tenant_id').eq(tenant_id))
    
    # Filtros adicionales en t_predicciones
    if 'codigo_producto' in filtros:
        conditions.append(Attr('entity_id').eq(filtros['codigo_producto']))
    
    if 'metodo' in filtros:
        conditions.append(Attr('metodo').eq(filtros['metodo']))
    
    if 'demanda_minima' in filtros:
        conditions.append(Attr('demanda_manana').gte(filtros['demanda_minima']))
    
    # Retornar condición combinada (siempre habrá al menos tenant_id)
    return And(*conditions) if len(conditions) > 1 else conditions[0]


def aplicar_filtros_enriquecidos(items, filtros):
    """
    Filtra en memoria por campos de t_productos (categoria, stock)
    
    Se hace en memoria porque estos campos están en tabla diferente
    """
    resultado = items
    
    if 'categoria' in filtros:
        resultado = [p for p in resultado if p.get('categoria') == filtros['categoria']]
    
    if 'stock_minimo' in filtros:
        resultado = [p for p in resultado if p.get('stock_actual', 0) >= filtros['stock_minimo']]
    
    if 'stock_maximo' in filtros:
        resultado = [p for p in resultado if p.get('stock_actual', 0) <= filtros['stock_maximo']]
    
    return resultado
