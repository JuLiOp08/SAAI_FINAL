# websockets/__init__.py
"""
SAAI Backend - Módulo WebSocket para Tiempo Real

Este módulo maneja las conexiones WebSocket para actualizaciones en tiempo real:
- Registro y limpieza de conexiones por tienda (multi-tenant)
- Emisión de eventos a clientes conectados de una tienda específica
- Integración con ventas, analítica y predicciones

Componentes:
1. on_connect.py - Registra nueva conexión WebSocket en t_ws_connections
2. on_disconnect.py - Limpia conexión al desconectarse
3. emitir_eventos_ws.py - Envía eventos a conexiones activas por tienda

Tabla: t_ws_connections
- tenant_id: codigo_tienda
- entity_id: connection_id (API Gateway)
- data: {connection_id, codigo_usuario, role, connected_at, estado, ttl}

Eventos soportados:
- venta_registrada (desde RegistrarVenta)
- analitica_actualizada (desde ActualizarAnalitica)  
- prediccion_generada (desde PrediccionDemanda)

Seguridad:
- Aislamiento multi-tenant estricto por tenant_id
- Validación JWT para obtener usuario/tienda
- Limpieza automática de conexiones inválidas
"""