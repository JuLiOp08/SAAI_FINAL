# SAAI Backend - Sistema de Inventario Inteligente

Este es el backend serverless de SAAI (Smart Assistant for Inventory), un sistema multi-tenant de gestión de inventario para tiendas desarrollado en AWS.

## 🏗️ Arquitectura

- **Proveedor**: AWS
- **Cuenta**: AWS Academy (Account ID: 361725523078)
- **Región**: us-east-1
- **Framework**: Serverless Framework
- **Runtime**: Python 3.9
- **Base de datos**: DynamoDB
- **Autenticación**: JWT con Lambda Authorizer
- **APIs**: REST API + WebSocket API
- **Notificaciones**: Amazon SNS
- **Almacenamiento**: Amazon S3
- **ML**: Amazon SageMaker

## 📂 Estructura del Proyecto

```
SAAI_FINAL/
├── auth/                    # Autenticación y autorización
├── productos/               # Gestión de productos (TRABAJADOR)
├── ventas/                  # Registro de ventas (TRABAJADOR)
├── usuarios/                # Gestión de usuarios (ADMIN)
├── gastos/                  # Gestión de gastos (ADMIN)
├── analytics/               # Analítica de negocio (ADMIN)
├── reports/                 # Generación de reportes (ADMIN)
├── ml/                      # Predicción de demanda (ADMIN)
├── tiendas/                 # Gestión de tiendas (SAAI)
├── notifications/           # Sistema de notificaciones
├── websockets/              # WebSocket para tiempo real
├── welcome/                 # Flujo de bienvenida nuevas tiendas
├── utils/                   # Utilidades comunes
├── serverless.yml           # Configuración de infraestructura
├── requirements.txt         # Dependencias Python
└── package.json             # Configuración del proyecto
```

## 🗄️ Modelo de Datos (DynamoDB)

Todas las tablas siguen el patrón estándar:

```
Partition Key: tenant_id (codigo_tienda)
Sort Key: entity_id (código de la entidad)
Attribute: data (JSON completo de la entidad)
```

### Tablas del Sistema

- `t_tiendas`: Información de tiendas registradas
- `t_usuarios`: Usuarios por tienda (TRABAJADOR/ADMIN)
- `t_productos`: Catálogo de productos por tienda
- `t_ventas`: Registro de ventas por tienda
- `t_gastos`: Registro de gastos por tienda
- `t_notificaciones`: Notificaciones por usuario
- `t_analitica`: Métricas calculadas por tienda
- `t_reportes`: Historial de reportes generados
- `t_predicciones`: Cache de predicciones ML
- `t_tokens_*`: Tokens JWT activos por rol
- `t_counters`: Contadores para generación de códigos
- `t_ws_connections`: Conexiones WebSocket activas

## 🔐 Seguridad y Multi-tenancy

### Autenticación JWT
- **Lambda Authorizer** valida todos los endpoints privados
- **Claims obligatorios**: `codigo_usuario`, `tenant_id`, `rol`
- **Roles**: `TRABAJADOR`, `ADMIN`, `SAAI`
- **Expiración**: 24 horas por defecto

### Aislamiento de Datos
- **Strict Multi-tenancy**: Todos los datos filtrados por `tenant_id`
- **Sin cross-tenant access**: Imposible acceder a datos de otra tienda
- **Soft delete**: Patrón `estado=INACTIVO` para eliminaciones

## 🌍 Zona Horaria

Todo el sistema opera en **America/Lima (UTC-05:00)**:
- Timestamps generados en zona horaria de Perú
- Fechas formateadas para usuarios peruanos
- Reportes y analítica en horario local

## 📡 APIs Disponibles

### Autenticación (Público)
- `POST /login` - Login multi-rol

### TRABAJADOR APIs
- `GET|POST /productos` - Gestión de productos
- `POST /productos/buscar` - Búsqueda de productos
- `PUT|DELETE /productos/{codigo}` - CRUD productos
- `POST /ventas/calcular` - Calcular monto de venta
- `POST /ventas` - Registrar venta
- `GET /ventas` - Listar ventas
- `POST /ventas/buscar` - Búsqueda de ventas

### ADMIN APIs
- `GET|POST /usuarios` - Gestión de usuarios
- `POST /usuarios/buscar` - Búsqueda de usuarios
- `PUT|DELETE /usuarios/{codigo}` - CRUD usuarios
- `GET|POST /gastos` - Gestión de gastos
- `POST /gastos/buscar` - Búsqueda de gastos
- `PUT|DELETE /gastos/{codigo}` - CRUD gastos
- `GET|POST /analitica` - Dashboard analítico
- `POST /reportes/{tipo}` - Generación de reportes
- `GET /reportes/historial` - Historial de reportes
- `POST /predicciones` - Predicción de demanda ML

### SAAI Platform APIs
- `GET|POST /tiendas` - Gestión de tiendas
- `POST /tiendas/buscar` - Búsqueda de tiendas
- `PUT|DELETE /tiendas/{codigo}` - CRUD tiendas

### Notificaciones
- `GET /notificacion` - Listar notificaciones del usuario

## 🔔 Sistema de Notificaciones

### SNS Topics
- **AlertasSAAI**: Alertas operativas (stock bajo, errores)
- **BienvenidaSAAI**: Flujo de nuevas tiendas

### Consumidores Automáticos
- Guardar notificaciones en DynamoDB
- Envío de correos de bienvenida
- Creación de carpetas S3 por tienda
- Suscripción a alertas por email

## 🚀 WebSocket (Tiempo Real)

- **Conexión**: `wss://api.ejemplo.com/websocket`
- **Eventos**: `nueva_venta`, `stock_bajo`, `metricas_actualizadas`
- **Aislamiento**: Solo eventos de la tienda del usuario
- **TTL**: Conexiones expiran automáticamente

## 📊 Machine Learning

### Predicción de Demanda
- **Servicio**: Amazon SageMaker
- **Frecuencia**: Entrenamiento cada 3 días
- **Cache**: Predicciones guardadas en DynamoDB
- **Features**: Histórico de ventas, estacionalidad, tendencias

## 📈 Reportes

### Tipos Disponibles
- **Inventario** (`INV`): Stock actual por producto
- **Ventas** (`VEN`): Resumen de ventas por período
- **Gastos** (`GAS`): Análisis de gastos por categoría
- **General** (`GEN`): Reporte combinado completo

### Almacenamiento
- **Bucket S3**: `saai-tiendas-{stage}`
- **Estructura**: `/tienda/{codigo_tienda}/reportes/{tipo}/{fecha}/`
- **Formato**: Excel (.xlsx) con múltiples hojas
- **Access**: Presigned URLs para descarga segura

## ⚡ Variables de Entorno

```bash
# JWT Configuration
JWT_SECRET=saai-secret-key-2025
JWT_EXPIRES_IN=86400

# AWS Configuration (AWS Academy)
ACCOUNT_ID=361725523078
REGION=us-east-1

# DynamoDB Tables (auto-generated)
TIENDAS_TABLE=saai-backend-dev-tiendas
USUARIOS_TABLE=saai-backend-dev-usuarios
# ... más tablas

# SNS Topics
ALERTAS_SAAI_TOPIC_ARN=arn:aws:sns:us-east-1:361725523078:AlertasSAAI-dev
BIENVENIDA_SAAI_TOPIC_ARN=arn:aws:sns:us-east-1:361725523078:BienvenidaSAAI-dev

# S3 Bucket
S3_BUCKET=saai-tiendas-dev
```

## 🚀 Deployment

### Pre-requisitos
```bash
npm install -g serverless
npm install
pip install -r requirements.txt
```

### Deploy a AWS Academy
```bash
# Development
serverless deploy --stage dev

# Production
serverless deploy --stage prod
```

### Verificar Deploy
```bash
serverless info --stage dev
```

## 📋 Códigos de Entidad

### Formato Estándar
- **Tiendas**: `T001`, `T002`, ...
- **Usuarios**: `T001U001`, `T001U002`, ...
- **Productos**: `T001P001`, `T001P002`, ...
- **Ventas**: `T001V001`, `T001V002`, ...
- **Gastos**: `T001G001`, `T001G002`, ...

### Generación
- Contadores atómicos por tienda en DynamoDB
- Auto-incremento con formato consistente
- Validación de formato en todas las APIs

## 🔍 Monitoreo y Logs

### CloudWatch Logs
- Cada Lambda tiene su log group
- Logs estructurados con levels (INFO, ERROR, DEBUG)
- Request/Response tracing para debugging

### Métricas Clave
- Latencia de APIs por endpoint
- Tasas de error por función
- Uso de DynamoDB (RCU/WCU)
- Tamaño de conexiones WebSocket

## 🛡️ Manejo de Errores

### Respuestas Estándar
```json
{
  "exito": true|false,
  "mensaje": "Descripción del resultado",
  "data": {...},          // Solo en éxito
  "error": "...",         // Solo en error
  "detalles": {...}       // Información adicional de error
}
```

### Códigos HTTP
- `200`: Operación exitosa
- `201`: Recurso creado
- `400`: Error de validación
- `401`: Token inválido/expirado
- `403`: Sin permisos
- `404`: Recurso no encontrado
- `409`: Conflicto (ej: código duplicado)
- `500`: Error interno

## 🧪 Testing

```bash
# Ejecutar tests
python -m pytest tests/

# Lint
flake8 .

# Format
black .
```

## 📖 Documentación de Referencia

- [Documento SAAI Oficial](./SAAI_oficial.txt) - Especificaciones completas
- [AWS Academy Learner Lab](https://aws.amazon.com/training/awsacademy/)
- [Serverless Framework](https://www.serverless.com/framework/docs/)

## 🤝 Contribución

1. Seguir exactamente las especificaciones del documento oficial
2. Mantener el patrón multi-tenant estricto
3. Usar zona horaria de Perú en todas las fechas
4. Validar formatos de código según estándares
5. Implementar manejo de errores robusto

---

**SAAI Team** - Sistema de Inventario Inteligente para Tiendas 🏪