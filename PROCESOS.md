# Configuración de Procesos - Smartsheet-Bind Middleware

## Descripción General

El middleware utiliza una base de datos SQLite para almacenar la configuración de cada proceso de sincronización. Esto permite modificar los Sheet IDs de Smartsheet sin necesidad de redesplegar la aplicación.

## Base de Datos

- **Ubicación**: `/app/data/processes.db`
- **Volumen Docker**: `smartsheet-bind-data`
- **Modelo**: `ProcessConfig`

### Campos de ProcessConfig

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `job_id` | String | Identificador único del proceso (ej: `sync_invoices`) |
| `name` | String | Nombre descriptivo del proceso |
| `description` | Text | Descripción detallada del proceso |
| `smartsheet_sheet_id` | String | ID de la hoja de Smartsheet destino |
| `smartsheet_sheet_name` | String | Nombre de la hoja de Smartsheet |
| `interval_minutes` | Integer | Intervalo de ejecución en minutos |
| `is_active` | Boolean | Si el proceso está activo |
| `source_system` | String | Sistema origen (`bind` o `smartsheet`) |
| `target_system` | String | Sistema destino (`bind` o `smartsheet`) |
| `sync_direction` | String | Dirección (`pull`, `push`, `bidirectional`) |
| `fields_mapping` | JSON | Mapeo de campos entre sistemas |

## Procesos Actuales

### 1. Sincronización de Facturas (sync_invoices)

- **Job ID**: `sync_invoices`
- **Dirección**: Bind ERP → Smartsheet
- **Intervalo**: 2 minutos
- **Sheet ID**: `4956740131966852`

**Funcionamiento**:
1. Consulta facturas de los últimos 10 minutos en Bind ERP (zona horaria CDMX)
2. Verifica si ya existen en Smartsheet por UUID
3. Realiza UPSERT: actualiza existentes o inserta nuevas
4. Registra resultado en historial

**Campos sincronizados**:
- UUID, Folio, Fecha, RFC Cliente, Nombre Cliente, Total, Estado

### 2. Sincronización de Inventario (sync_inventory)

- **Job ID**: `sync_inventory`
- **Dirección**: Bind ERP → Smartsheet
- **Intervalo**: 60 minutos
- **Sheet ID**: Configurar según necesidad

**Funcionamiento**:
1. Obtiene productos con existencias del almacén configurado
2. Actualiza hoja de inventario en Smartsheet

**Campos sincronizados**:
- ID Producto, Código, Nombre, Existencias, Almacén

## API de Configuración

### Listar todas las configuraciones

```bash
GET /api/admin/process-configs
```

**Respuesta**:
```json
{
  "success": true,
  "timestamp": "2026-01-18T11:38:21.395587-06:00",
  "configs": [...]
}
```

### Obtener configuración específica

```bash
GET /api/admin/process-configs/{job_id}
```

### Actualizar configuración

```bash
PUT /api/admin/process-configs/{job_id}
Content-Type: application/json

{
  "smartsheet_sheet_id": "1234567890",
  "smartsheet_sheet_name": "Mi Nueva Hoja",
  "interval_minutes": 5
}
```

## Cómo Crear un Nuevo Proceso

### Paso 1: Definir la lógica de sincronización

Crear una función en `business_logic.py`:

```python
def sync_mi_nuevo_proceso(
    ss_service: SmartsheetService = None,
    bind_client: BindClient = None,
    sheet_id: int = None,
) -> dict:
    """
    Sincroniza datos de [origen] a [destino].

    Args:
        ss_service: Servicio de Smartsheet
        bind_client: Cliente de Bind ERP
        sheet_id: ID de la hoja de Smartsheet

    Returns:
        dict con resultado de la sincronización
    """
    # Inicializar servicios si no se proporcionan
    ss_service = ss_service or SmartsheetService()
    bind_client = bind_client or BindClient()

    # Lógica de sincronización...

    return {
        "success": True,
        "timestamp": datetime.now(CDMX_TZ).isoformat(),
        "message": "Sincronización completada"
    }
```

### Paso 2: Crear función ejecutora en main.py

```python
async def run_mi_nuevo_sync():
    """Ejecuta la sincronización de mi nuevo proceso."""
    logger.info("Ejecutando mi nuevo proceso...")
    try:
        # Obtener sheet_id desde la base de datos
        config = get_process_config("mi_nuevo_proceso")
        sheet_id = int(config.smartsheet_sheet_id) if config and config.smartsheet_sheet_id else None

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: sync_mi_nuevo_proceso(sheet_id=sheet_id)
        )

        add_to_history("mi_nuevo_proceso", "Mi Nuevo Proceso",
                      "completed" if result.get("success") else "failed", result)
        return result
    except Exception as e:
        logger.error(f"Error en mi nuevo proceso: {e}")
        add_to_history("mi_nuevo_proceso", "Mi Nuevo Proceso", "failed", {"error": str(e)})
        raise
```

### Paso 3: Registrar el job en el scheduler

En la función `lifespan()` de `main.py`:

```python
# Configurar scheduler para mi nuevo proceso
if settings.MI_NUEVO_PROCESO_INTERVAL_MINUTES > 0:
    scheduler.add_job(
        run_mi_nuevo_sync,
        trigger=IntervalTrigger(minutes=settings.MI_NUEVO_PROCESO_INTERVAL_MINUTES),
        id="mi_nuevo_proceso",
        name="Mi Nuevo Proceso",
        replace_existing=True,
    )
```

### Paso 4: Agregar configuración por defecto en database.py

En la función `seed_default_configs()`:

```python
create_or_update_process_config(
    job_id="mi_nuevo_proceso",
    name="Mi Nuevo Proceso",
    description="Descripción de lo que hace el proceso...",
    smartsheet_sheet_id="ID_DE_LA_HOJA",
    smartsheet_sheet_name="Nombre de la Hoja",
    interval_minutes=30,
    is_active=True,
    source_system="bind",  # o "smartsheet"
    target_system="smartsheet",  # o "bind"
    sync_direction="pull",  # o "push" o "bidirectional"
    fields_mapping={
        "bind_fields": ["Campo1", "Campo2"],
        "smartsheet_columns": ["Columna1", "Columna2"],
    },
)
```

### Paso 5: Agregar metadatos para el dashboard

En `JOB_METADATA` de `main.py`:

```python
"mi_nuevo_proceso": {
    "name": "Mi Nuevo Proceso",
    "description": "Descripción corta",
    "short_desc": "Origen → Destino | Datos sincronizados",
    "icon": "custom",
    "source": "Bind ERP → Smartsheet",
    "endpoint": "/api/sync/mi-proceso",
    "details": """
        <div>HTML con detalles del proceso...</div>
    """,
},
```

### Paso 6: Permitir ejecución manual

En el endpoint `/api/admin/jobs/{job_id}/run`:

```python
elif job_id == "mi_nuevo_proceso":
    background_tasks.add_task(run_mi_nuevo_sync)
```

## Dashboard de Administración

Accede al dashboard en: `https://smartsheet-bind-awalab.entersys.mx/admin`

Funcionalidades:
- Ver estado de todos los procesos
- Pausar/Reanudar procesos
- Ejecutar manualmente
- Cambiar intervalo de ejecución
- Ver detalles con Sheet ID desde la BD
- Consultar historial de ejecuciones

## Notas Importantes

1. **Zona horaria**: Todas las fechas usan `America/Mexico_City` (CDMX)
2. **Persistencia**: La base de datos está en un volumen Docker persistente
3. **Fallback**: Si no hay configuración en BD, se usan variables de entorno
4. **Límites API**: Bind tiene límite de 100 registros por request
5. **UPSERT**: Las facturas se actualizan por UUID para evitar duplicados
