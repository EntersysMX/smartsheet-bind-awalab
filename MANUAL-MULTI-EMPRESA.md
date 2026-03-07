# Manual de Operación - Smartsheet-Bind Middleware Multi-Empresa

## Índice

1. [Arquitectura General](#arquitectura-general)
2. [Modelo de Datos](#modelo-de-datos)
3. [Flujo de Sincronización](#flujo-de-sincronización)
4. [Dashboard de Administración](#dashboard-de-administración)
5. [API de Administración](#api-de-administración)
6. [Gestión de Empresas](#gestión-de-empresas)
7. [Gestión de Jobs/Procesos](#gestión-de-jobsprocesos)
8. [Scheduler Dinámico](#scheduler-dinámico)
9. [Convenciones y Formato de IDs](#convenciones-y-formato-de-ids)
10. [Troubleshooting](#troubleshooting)

---

## Arquitectura General

El middleware conecta **Bind ERP** con **Smartsheet** para sincronizar datos automáticamente. Soporta múltiples empresas (tenants), cada una con sus propias credenciales de Bind y su workspace de Smartsheet.

```
┌─────────────┐     ┌──────────────────────┐     ┌─────────────┐
│  Bind ERP   │◄───►│  Middleware FastAPI   │◄───►│ Smartsheet  │
│ (por empresa)│     │  + Scheduler (APSch) │     │ (compartido)│
└─────────────┘     │  + SQLite (config)   │     └─────────────┘
                    └──────────────────────┘
```

### Componentes principales

| Archivo | Función |
|---------|---------|
| `main.py` | Servidor FastAPI, scheduler, endpoints API y webhooks |
| `database.py` | Modelos SQLAlchemy (Company, ProcessConfig), migraciones, seed |
| `company_services.py` | Factory: crea BindClient/SmartsheetService por empresa |
| `bind_client.py` | Cliente HTTP para Bind ERP con retry y paginación OData |
| `smartsheet_service.py` | Cliente para Smartsheet API |
| `business_logic.py` | Lógica de sync inventario, facturas, facturación desde webhook |
| `sync_bind_catalogs.py` | Sincronización de 17+ catálogos de Bind a Smartsheet |
| `config.py` | Variables de entorno (.env) |
| `static/dashboard.html` | Dashboard web de administración |

---

## Modelo de Datos

### Tabla `companies`

Almacena las empresas/tenants del sistema.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | String(50) PK | Slug único: "awalab", "empresa2" |
| `name` | String(200) | Nombre legible: "AWALab de México" |
| `bind_api_key` | String(500) | API Key de Bind ERP (JWT) |
| `bind_api_base_url` | String(500) | URL base de Bind (default: https://api.bind.com.mx/api) |
| `smartsheet_workspace_id` | String(100) | ID del workspace en Smartsheet para esta empresa |
| `bind_warehouse_id` | String(100) | ID del almacén principal en Bind |
| `is_active` | Boolean | Si está activa (soft delete = false) |
| `created_at` | DateTime | Fecha de creación |
| `updated_at` | DateTime | Última modificación |

### Tabla `process_configs`

Configuración de cada job/proceso de sincronización.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | Integer PK | Auto-incremental |
| `job_id` | String(100) UNIQUE | Identificador del job: "awalab__sync_invoices" |
| `company_id` | String(50) FK | Referencia a companies.id |
| `name` | String(200) | Nombre descriptivo |
| `description` | Text | Descripción detallada |
| `smartsheet_sheet_id` | String(50) | ID de la hoja de Smartsheet destino |
| `smartsheet_sheet_name` | String(200) | Nombre de la hoja |
| `interval_minutes` | Integer | Intervalo de ejecución (default: 60) |
| `is_active` | Boolean | Si el job está activo en el scheduler |
| `operating_start_hour` | Integer | Hora inicio operación (default: 7 = 7AM CDMX) |
| `operating_end_hour` | Integer | Hora fin operación (default: 20 = 8PM CDMX) |
| `source_system` | String(50) | "bind" o "smartsheet" |
| `target_system` | String(50) | "bind" o "smartsheet" |
| `sync_direction` | String(20) | "pull", "push", "bidirectional" |
| `fields_mapping` | Text (JSON) | Mapeo de campos entre sistemas |

---

## Flujo de Sincronización

### Tipos de sincronización

#### 1. Facturas Bind → Smartsheet (`sync_invoices`)
- Consulta facturas de los últimos 10 minutos en Bind
- UPSERT por UUID: actualiza existentes o inserta nuevas
- Una fila por producto de cada factura
- Campos: UUID, Serie, Folio, Fecha, Cliente, RFC, Subtotal, IVA, Total, Moneda, Estatus, Comentarios

#### 2. Inventario Bind → Smartsheet (`sync_inventory`)
- Obtiene todos los productos del catálogo de Bind
- UPSERT por ID Producto
- Campos: Código, Nombre, Existencias, Unidad, Precio, Almacén

#### 3. Catálogos Bind → Smartsheet (`sync_catalog_*`)
17 catálogos disponibles:

| Job Type | Catálogo | Endpoint Bind |
|----------|----------|---------------|
| `sync_catalog_warehouses` | Almacenes | GET /api/Warehouses |
| `sync_catalog_clients` | Clientes | GET /api/Clients |
| `sync_catalog_products` | Productos | GET /api/Products |
| `sync_catalog_providers` | Proveedores | GET /api/Providers |
| `sync_catalog_users` | Usuarios | GET /api/Users |
| `sync_catalog_currencies` | Monedas | GET /api/Currencies |
| `sync_catalog_pricelists` | Listas de Precios | GET /api/PriceLists |
| `sync_catalog_bankaccounts` | Cuentas Bancarias | GET /api/BankAccounts |
| `sync_catalog_banks` | Bancos | GET /api/Banks |
| `sync_catalog_locations` | Ubicaciones | GET /api/Locations |
| `sync_catalog_orders` | Pedidos | GET /api/Orders |
| `sync_catalog_quotes` | Cotizaciones | GET /api/Quotes |
| `sync_catalog_categories` | Categorías | GET /api/Categories |
| `sync_catalog_accounts` | Cuentas Contables | GET /api/Accounts |
| `sync_catalog_account_categories` | Catálogo Cuentas SAT | GET /api/AccountCategories |
| `sync_catalog_accounting_journals` | Pólizas Contables | GET /api/AccountingJournals |
| `sync_catalog_invoices` | Facturas (catálogo) | GET /api/Invoices |

#### 4. Facturación Smartsheet → Bind (webhook)
- Smartsheet envía webhook cuando una fila cambia a Estado="Facturar"
- El middleware lee los datos de la fila, busca cliente por RFC en Bind, crea la factura CFDI
- Escribe UUID y resultado de vuelta en Smartsheet

### Comportamiento de carga

- **Hoja con <10 registros**: CARGA INICIAL (todos los datos, sin filtro de fecha)
- **Hoja con >=10 registros**: INCREMENTAL (solo últimos 7 días, UPSERT)
- **force_full_load=True**: CARGA COMPLETA forzada

### Horario operativo

Cada job tiene `operating_start_hour` y `operating_end_hour` (zona CDMX). Fuera de ese horario, el job se salta silenciosamente.

---

## Dashboard de Administración

### Acceso

```
URL: https://<tu-dominio>/admin
```

No requiere autenticación (proteger con Traefik/BasicAuth en producción).

### Secciones del Dashboard

#### 1. Barra superior
- Estado de conexiones: indicador verde/amarillo/rojo
- Botón de recarga manual

#### 2. Tarjetas de estadísticas
- **Jobs activos**: cantidad de procesos programados
- **Ejecuciones**: total de ejecuciones registradas
- **Bind ERP**: estado de conexión por empresa (X/Y OK si hay varias)
- **Smartsheet**: estado de conexión

#### 3. Lista de Jobs
Cada tarjeta de job muestra:
- Nombre del proceso
- **Badge de empresa** (ej: `awalab`) en azul junto al nombre
- Próxima ejecución programada
- Intervalo configurado
- Botones: Ejecutar ahora, Pausar/Reanudar, Configurar

#### 4. Historial de ejecuciones
- Últimas 50 ejecuciones con timestamp, job, estado (completado/fallido/manual)

#### 5. Sección Empresas
- **Lista de empresas** registradas con estado (Activa/Inactiva) e indicador de API key
- **Botón Test** (icono wifi): prueba la conexión a Bind con las credenciales de esa empresa
- **Botón Reload** (icono refresh): recarga los jobs del scheduler para esa empresa
- **Botón +** (esquina superior): abre formulario para crear empresa nueva
  - Campos: ID (slug), Nombre, Bind API Key
  - Al crear, se generan automáticamente ~19 ProcessConfigs (inactivos por default)

#### 6. Modal de configuración (clic en engranaje de un job)
- Cambiar intervalo de ejecución (minutos)
- Cambiar horario operativo (hora inicio/fin)
- Ver detalles del proceso, campos sincronizados, endpoint de Bind
- Historial reciente de ese job

---

## API de Administración

Base URL: `https://<tu-dominio>`

### Endpoints de Salud

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Health check básico |
| GET | `/health` | Health check con verificación de conexiones |

### Endpoints de Empresas

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/admin/companies` | Lista todas las empresas |
| GET | `/api/admin/companies/{id}` | Detalle de empresa + ProcessConfigs + jobs activos |
| POST | `/api/admin/companies` | Crear empresa nueva |
| PUT | `/api/admin/companies/{id}` | Actualizar datos de empresa |
| DELETE | `/api/admin/companies/{id}` | Desactivar empresa (soft delete) + remover jobs |
| POST | `/api/admin/companies/{id}/test-connection` | Probar conexión Bind |

#### Crear empresa - POST `/api/admin/companies`

```json
{
  "id": "empresa2",
  "name": "Mi Empresa S.A.",
  "bind_api_key": "eyJhbGciOi...",
  "bind_api_base_url": "https://api.bind.com.mx/api",
  "smartsheet_workspace_id": "123456789",
  "bind_warehouse_id": "guid-del-almacen",
  "is_active": true
}
```

Respuesta:
```json
{
  "success": true,
  "message": "Empresa 'empresa2' creada con 19 procesos configurados",
  "company": { "id": "empresa2", "name": "Mi Empresa S.A.", ... }
}
```

#### Actualizar empresa - PUT `/api/admin/companies/{id}`

Solo enviar los campos a cambiar:
```json
{
  "name": "Nuevo Nombre",
  "bind_api_key": "nueva-key",
  "is_active": false
}
```

### Endpoints de Jobs/Scheduler

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/scheduler/jobs` | Lista jobs con company_id y base_type |
| POST | `/scheduler/reload` | Recarga TODOS los jobs desde BD |
| POST | `/scheduler/reload/{company_id}` | Recarga jobs de una empresa |
| GET | `/api/admin/jobs` | Lista detallada de jobs (para dashboard) |
| GET | `/api/admin/jobs/{job_id}/details` | Detalle completo de un job |
| POST | `/api/admin/jobs/{job_id}/run` | Ejecutar job inmediatamente |
| POST | `/api/admin/jobs/{job_id}/pause` | Pausar job |
| POST | `/api/admin/jobs/{job_id}/resume` | Reanudar job pausado |
| PUT | `/api/admin/jobs/{job_id}/interval` | Cambiar intervalo (query param: minutes) |
| PUT | `/api/admin/jobs/{job_id}/operating-hours` | Cambiar horario (params: start_hour, end_hour) |

### Endpoints de ProcessConfigs

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/admin/process-configs?company_id=X` | Lista configs (filtro opcional por empresa) |
| GET | `/api/admin/process-configs/{job_id}` | Config de un proceso |
| PUT | `/api/admin/process-configs/{job_id}` | Actualizar config |

#### Activar un proceso - PUT `/api/admin/process-configs/{job_id}`

```json
{
  "is_active": true,
  "interval_minutes": 60
}
```

### Endpoints de Sincronización Manual

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/sync/inventory` | Disparar sync inventario manual |
| POST | `/sync/invoices` | Disparar sync facturas manual |
| GET | `/sync/inventory/status` | Estado del scheduler de inventario |
| GET | `/sync/invoices/status` | Estado del scheduler de facturas |

### Endpoints de Historial y Stats

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/admin/history?limit=50` | Historial de ejecuciones |
| GET | `/api/admin/stats` | Estadísticas generales (conexiones por empresa, jobs por empresa) |

### Webhook de Smartsheet

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/webhook/smartsheet` | Recibe webhooks de Smartsheet para facturación |

---

## Gestión de Empresas

### Agregar una nueva empresa (paso a paso)

#### Opción A: Desde el Dashboard

1. Ir a `https://<dominio>/admin`
2. En la sección **Empresas**, hacer clic en el botón **+**
3. Llenar: ID (slug sin espacios), Nombre, API Key de Bind
4. Clic en **Crear Empresa**
5. Se crean ~19 ProcessConfigs inactivos automáticamente
6. Ir a cada job que se quiera activar y cambiar `is_active` a true

#### Opción B: Via API

```bash
# 1. Crear empresa
curl -X POST https://<dominio>/api/admin/companies \
  -H "Content-Type: application/json" \
  -d '{
    "id": "nuevaempresa",
    "name": "Nueva Empresa S.A.",
    "bind_api_key": "eyJ...",
    "smartsheet_workspace_id": "123456789"
  }'

# 2. Verificar conexión a Bind
curl -X POST https://<dominio>/api/admin/companies/nuevaempresa/test-connection

# 3. Activar jobs deseados
curl -X PUT "https://<dominio>/api/admin/process-configs/nuevaempresa__sync_invoices" \
  -H "Content-Type: application/json" \
  -d '{"is_active": true, "interval_minutes": 5}'

curl -X PUT "https://<dominio>/api/admin/process-configs/nuevaempresa__sync_catalog_clients" \
  -H "Content-Type: application/json" \
  -d '{"is_active": true}'

# 4. Recargar scheduler para la empresa
curl -X POST https://<dominio>/scheduler/reload/nuevaempresa

# 5. Verificar jobs registrados
curl https://<dominio>/scheduler/jobs
```

### Desactivar una empresa

```bash
curl -X DELETE https://<dominio>/api/admin/companies/empresaid
```

Esto hace soft-delete (is_active=false) y remueve todos sus jobs del scheduler.

### Modificar credenciales

```bash
curl -X PUT https://<dominio>/api/admin/companies/empresaid \
  -H "Content-Type: application/json" \
  -d '{"bind_api_key": "nueva-key-jwt"}'
```

Después recargar scheduler: `POST /scheduler/reload/empresaid`

---

## Gestión de Jobs/Procesos

### Ejecutar un job manualmente

Desde dashboard: botón "play" en la tarjeta del job.

Via API:
```bash
curl -X POST https://<dominio>/api/admin/jobs/awalab__sync_invoices/run
```

### Pausar/Reanudar un job

```bash
# Pausar
curl -X POST https://<dominio>/api/admin/jobs/awalab__sync_invoices/pause

# Reanudar
curl -X POST https://<dominio>/api/admin/jobs/awalab__sync_invoices/resume
```

### Cambiar intervalo de ejecución

```bash
# Cambiar a cada 30 minutos
curl -X PUT "https://<dominio>/api/admin/jobs/awalab__sync_invoices/interval?minutes=30"
```

### Cambiar horario operativo

```bash
# Operar solo de 8AM a 6PM (CDMX)
curl -X PUT "https://<dominio>/api/admin/jobs/awalab__sync_invoices/operating-hours?start_hour=8&end_hour=18"
```

---

## Scheduler Dinámico

### Cómo funciona

1. Al iniciar el servidor, `schedule_all_active_jobs()` lee TODOS los ProcessConfigs activos de la BD
2. Para cada uno, registra un job en APScheduler con su intervalo configurado
3. Cuando un job se ejecuta, `run_dynamic_job()` parsea el `job_id` para determinar:
   - El tipo de sync (inventario, facturas, catálogo)
   - La empresa (por el `company_id` del ProcessConfig)
4. Crea un BindClient con las credenciales de esa empresa y ejecuta el sync

### Recargar jobs sin reiniciar

```bash
# Recargar todos los jobs
curl -X POST https://<dominio>/scheduler/reload

# Recargar solo los de una empresa
curl -X POST https://<dominio>/scheduler/reload/awalab
```

### Ver jobs activos

```bash
curl https://<dominio>/scheduler/jobs
```

Respuesta:
```json
{
  "jobs": [
    {
      "id": "awalab__sync_invoices",
      "name": "Sincronización de Facturas",
      "company_id": "awalab",
      "base_type": "sync_invoices",
      "next_run": "2026-03-07T10:30:00-06:00"
    }
  ],
  "total": 15
}
```

---

## Convenciones y Formato de IDs

### Job IDs

Formato: `{company_id}__{job_type}`

Ejemplos:
- `awalab__sync_invoices`
- `awalab__sync_inventory`
- `awalab__sync_catalog_clients`
- `empresa2__sync_invoices`

El doble guion bajo `__` separa empresa de tipo de job.

### Company IDs

- Slug en minúsculas, sin espacios ni caracteres especiales
- Ejemplos: `awalab`, `empresa2`, `acme_mx`

### Tokens compartidos vs. por empresa

| Credencial | Alcance |
|------------|---------|
| `SMARTSHEET_ACCESS_TOKEN` | Global (mismo token para todas las empresas) |
| `bind_api_key` | Por empresa (almacenado en tabla companies) |
| `smartsheet_workspace_id` | Por empresa (cada una puede tener su workspace) |
| `bind_warehouse_id` | Por empresa |

---

## Troubleshooting

### El job no se ejecuta

1. Verificar que el ProcessConfig tenga `is_active: true`
2. Verificar que estamos dentro del horario operativo (operating_start_hour / operating_end_hour, zona CDMX)
3. Verificar que el scheduler esté corriendo: `GET /api/admin/stats` → `scheduler.running: true`
4. Recargar scheduler: `POST /scheduler/reload`

### Error de conexión a Bind

1. Probar conexión: `POST /api/admin/companies/{id}/test-connection`
2. Verificar que la API key no haya expirado (los JWT de Bind tienen fecha de expiración)
3. Revisar logs del contenedor: `docker logs smartsheet-bind`

### Datos no aparecen en Smartsheet

1. Verificar que el `smartsheet_workspace_id` de la empresa sea correcto
2. Verificar que el `smartsheet_sheet_id` del ProcessConfig apunte a la hoja correcta
3. Ejecutar el job manualmente: `POST /api/admin/jobs/{job_id}/run`
4. Revisar historial: `GET /api/admin/history`

### Agregar empresa y no se crean jobs

1. Verificar que la empresa se creó: `GET /api/admin/companies/{id}`
2. Los ProcessConfigs se crean INACTIVOS por default. Activarlos:
   ```bash
   curl -X PUT ".../api/admin/process-configs/{company_id}__sync_invoices" \
     -d '{"is_active": true}'
   ```
3. Recargar scheduler: `POST /scheduler/reload/{company_id}`

### Migración de datos legacy

Si existían jobs con IDs sin prefijo (ej: `sync_inventory` en vez de `awalab__sync_inventory`), la migración se ejecuta automáticamente al iniciar el servidor via `migrate_legacy_job_ids("awalab")` en `seed_default_configs()`.

---

## Variables de Entorno (.env)

```env
# Bind ERP (valores default/fallback, las empresas usan sus propias keys)
BIND_API_KEY=eyJ...
BIND_API_BASE_URL=https://api.bind.com.mx/api
BIND_WAREHOUSE_ID=guid-almacen

# Smartsheet (compartido para todas las empresas)
SMARTSHEET_ACCESS_TOKEN=token-aqui

# Servidor
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
DEBUG_MODE=false
LOG_LEVEL=INFO

# Intervalos default (se pueden cambiar por job en BD)
SYNC_INVENTORY_INTERVAL_MINUTES=60
SYNC_INVOICES_INTERVAL_MINUTES=2
```

---

## Tests

### Ejecutar tests unitarios

```bash
python -m pytest tests/test_multi_tenant.py -v
```

7 tests: Company CRUD, job_id parsing, migración legacy, seed configs, factory de servicios.

### Test E2E con segunda empresa

```bash
# Contra servidor local
python tests/test_second_company.py http://localhost:8000

# Contra producción
python tests/test_second_company.py https://smartsheet-bind.entersys.mx
```

Crea una empresa de prueba, verifica ProcessConfigs, prueba conexión, activa un job, recarga scheduler, y limpia al final.
