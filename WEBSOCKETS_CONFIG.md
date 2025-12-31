# CONFIGURACIÓN WEBSOCKETS - SAAI BACKEND

## ✅ ESTADO ACTUAL: LISTO PARA DEPLOY

---

## 📋 ARCHIVOS CORREGIDOS

### 1. `emitir_eventos_ws.py`
**Correcciones aplicadas:**
- ✅ Cambiado `get_current_lima_time()` → `obtener_fecha_hora_peru()` (función correcta de utils)
- ✅ Eliminado `.isoformat()` ya que `obtener_fecha_hora_peru()` retorna string directamente
- ✅ Validación de tipos de eventos permitidos
- ✅ Limpieza automática de conexiones inválidas (GoneException)

**Estado:** ✅ CORRECTO

---

### 2. `on_connect.py`
**Correcciones aplicadas:**
- ✅ Agregado `verificar_token_jwt` a imports principales
- ✅ Eliminado import interno duplicado dentro del handler
- ✅ TTL configurado correctamente (24 horas)
- ✅ Validación completa de JWT claims

**Estado:** ✅ CORRECTO

---

### 3. `on_disconnect.py`
**Correcciones aplicadas:**
- ✅ Optimizado scan: usa `entity_id` directamente
- ✅ Agregado `Limit=1` para eficiencia
- ✅ Retorna siempre 200 para evitar reintentos

**Estado:** ✅ CORRECTO

---

## 🔧 CONFIGURACIÓN SERVERLESS.YML

### WebSocket Endpoint
```yaml
WS_API_ENDPOINT: 
  Fn::Join:
    - ""
    - - "https://"
      - Ref: WebSocketApi
      - ".execute-api.${self:provider.region}.amazonaws.com/${self:provider.stage}"
```
**Estado:** ✅ CONFIGURADO CORRECTAMENTE

### WebSocket API Resource
```yaml
WebSocketApi:
  Type: AWS::ApiGatewayV2::Api
  Properties:
    Name: saai-websocket-${self:provider.stage}
    ProtocolType: WEBSOCKET
    RouteSelectionExpression: $request.body.action
```
**Estado:** ✅ CONFIGURADO CORRECTAMENTE

---

## 🗄️ TABLA DYNAMODB REQUERIDA

### t_ws_connections
**Esquema:**
```
- tenant_id (String) - HASH KEY
- entity_id (String) - RANGE KEY (es el connection_id)
- data (Map) - Contiene:
  {
    "connection_id": "abc123...",
    "codigo_usuario": "T001U001",
    "rol": "ADMIN",
    "connected_at": "2025-12-31T15:30:00-05:00",
    "estado": "ACTIVO",
    "ttl": 1735689000
  }
```

**TTL:** Configurar en campo `ttl` (limpieza automática después de 24 horas)

**Estado:** ⚠️ PENDIENTE DE CREAR (se creará con `serverless deploy`)

---

## 🔐 PERMISOS IAM NECESARIOS

### Para AWS Academy (LabRole)
El rol `arn:aws:iam::361725523078:role/LabRole` ya tiene permisos amplios, pero verifica estos específicos:

#### 1. Lambda → Lambda Invocation
```json
{
  "Effect": "Allow",
  "Action": [
    "lambda:InvokeFunction"
  ],
  "Resource": [
    "arn:aws:lambda:us-east-1:361725523078:function:saai-dev-EmitirEventosWs",
    "arn:aws:lambda:us-east-1:361725523078:function:saai-dev-RegistrarVenta",
    "arn:aws:lambda:us-east-1:361725523078:function:saai-dev-ActualizarAnalitica"
  ]
}
```

#### 2. Lambda → API Gateway Management
```json
{
  "Effect": "Allow",
  "Action": [
    "execute-api:ManageConnections",
    "execute-api:Invoke"
  ],
  "Resource": "arn:aws:execute-api:us-east-1:361725523078:*/dev/POST/@connections/*"
}
```

#### 3. Lambda → DynamoDB (t_ws_connections)
```json
{
  "Effect": "Allow",
  "Action": [
    "dynamodb:PutItem",
    "dynamodb:GetItem",
    "dynamodb:DeleteItem",
    "dynamodb:Query",
    "dynamodb:Scan"
  ],
  "Resource": "arn:aws:dynamodb:us-east-1:361725523078:table/saai-dev-ws-connections"
}
```

**Nota:** LabRole probablemente ya incluye estos permisos. Si al hacer deploy recibes errores de permisos, contacta al instructor.

---

## 🔄 FLUJO DE EVENTOS WEBSOCKET

### Arquitectura
```
┌─────────────────┐
│  Frontend JS    │
│  (WebSocket)    │
└────────┬────────┘
         │
         │ 1. wss://xxx.execute-api.us-east-1.amazonaws.com/dev
         │
         ▼
┌─────────────────┐
│ API Gateway WS  │
│  $connect       │────► OnConnect Lambda ────► t_ws_connections (INSERT)
│  $disconnect    │────► OnDisconnect Lambda ──► t_ws_connections (DELETE)
└─────────────────┘
         ▲
         │
         │ 3. postToConnection
         │
┌─────────────────┐
│EmitirEventosWs  │
│   Lambda        │◄──── 2. Lambda invoke (async)
└─────────────────┘
         ▲
         │
┌────────┴────────┐
│ RegistrarVenta  │  ActualizarAnalitica  │  PrediccionDemanda
│     Lambda      │       Lambda          │      Lambda
└─────────────────┘
```

### Eventos confirmados (según SAAI oficial)
1. **RegistrarVenta** → `venta_registrada`
   - Actualiza listado de ventas
   - Actualiza stock en tiempo real
   - Notificaciones instantáneas

2. **ActualizarAnalitica** → `analitica_actualizada`
   - Actualiza dashboard
   - Actualiza notificaciones

3. **PrediccionDemanda** → `prediccion_generada` (PENDIENTE)
   - Actualiza notificaciones

---

## ✅ CHECKLIST PRE-DEPLOY

- [x] **emitir_eventos_ws.py**: Imports correctos
- [x] **on_connect.py**: JWT validation correcta
- [x] **on_disconnect.py**: Cleanup optimizado
- [x] **serverless.yml**: WS_API_ENDPOINT configurado
- [x] **serverless.yml**: WebSocketApi resource definido
- [x] **serverless.yml**: Funciones WS registradas ($connect, $disconnect)
- [x] **Validación**: Sin errores de sintaxis
- [ ] **Deploy**: Ejecutar `serverless deploy`
- [ ] **Test**: Probar conexión WebSocket desde frontend

---

## 🧪 TESTING POST-DEPLOY

### 1. Obtener WebSocket URL
```bash
# Después del deploy, buscar:
endpoints:
  wss://xxxxx.execute-api.us-east-1.amazonaws.com/dev
```

### 2. Test con wscat (Node.js)
```bash
npm install -g wscat

# Conectar con token JWT
wscat -c "wss://xxxxx.execute-api.us-east-1.amazonaws.com/dev?token=eyJhbGc..."

# Deberías ver: Connected
# Desconectar: Ctrl+C
```

### 3. Test desde Frontend
```javascript
const ws = new WebSocket(`wss://xxxxx.execute-api.us-east-1.amazonaws.com/dev?token=${jwtToken}`);

ws.onopen = () => console.log('WebSocket conectado');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Evento recibido:', message);
  
  // message.event_type = 'venta_registrada' | 'analitica_actualizada'
  // message.data = { ... }
};

ws.onerror = (error) => console.error('WebSocket error:', error);
ws.onclose = () => console.log('WebSocket desconectado');
```

---

## 🚨 TROUBLESHOOTING

### Error: "Connection ID not found"
**Causa:** API Gateway no envió connectionId
**Solución:** Verificar que la ruta sea `$connect` o `$disconnect`

### Error: "WEBSOCKET_ENDPOINT no configurado"
**Causa:** Variable de entorno no generada
**Solución:** Re-deploy con `serverless deploy` (se genera automáticamente)

### Error: "GoneException" en postToConnection
**Causa:** Conexión ya cerrada
**Solución:** ✅ Ya implementado - se limpia automáticamente

### Conexión no persiste más de 2 horas
**Causa:** Timeout por defecto de API Gateway
**Solución:** Implementar ping/pong keep-alive desde frontend (cada 5 min)

---

## 📝 NOTAS ADICIONALES

### Diferencias SNS vs WebSocket
- **SNS (AlertasSAAI)**: Para notificaciones asíncronas → t_notificaciones
- **WebSocket**: Para updates en tiempo real → UI instantánea
- **Ambos se usan en paralelo** (no son excluyentes)

### Costos AWS Academy
- ✅ WebSocket API Gateway: Incluido en créditos
- ✅ Lambda invocations: Incluido en free tier
- ✅ DynamoDB: Incluido en free tier

### Limitaciones AWS Academy
- ⚠️ No se pueden crear roles IAM custom
- ⚠️ Usar LabRole existente
- ✅ Se pueden crear recursos (API Gateway, Lambda, DynamoDB)

---

## 🎯 SIGUIENTES PASOS

1. **Ejecutar:** `serverless deploy`
2. **Verificar:** Outputs del deploy (WebSocket URL)
3. **Probar:** Conexión desde frontend con JWT
4. **Validar:** Registrar venta → Recibir evento en WebSocket
5. **Monitorear:** CloudWatch Logs de las 3 funciones WS

---

**Última actualización:** 31 de diciembre de 2025
**Estado:** ✅ LISTO PARA DEPLOY
