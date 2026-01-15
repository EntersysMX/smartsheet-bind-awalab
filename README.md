# Smartsheet-Bind ERP Middleware

Middleware de sincronizacion entre **Smartsheet** y **Bind ERP** para automatizar facturacion y sincronizacion de inventarios.

## Caracteristicas

- **Push (Webhook):** Smartsheet -> Servidor -> Bind ERP (Creacion de Facturas CFDI 4.0)
- **Pull (Cron Job):** Bind ERP -> Servidor -> Smartsheet (Sincronizacion de Inventarios)
- Backoff exponencial para manejo de rate limits (429)
- Reintentos automaticos para errores de servidor (5xx)
- Paginacion OData automatica
- Validacion de datos con Pydantic
- Logs estructurados
- Health checks integrados

## Tecnologias

- Python 3.11+
- FastAPI
- APScheduler
- Smartsheet Python SDK
- Docker & Docker Compose
- Traefik (reverse proxy)

## Estructura del Proyecto

```
smartsheet-bind-awalab/
├── config.py              # Configuracion y variables de entorno
├── bind_client.py         # Cliente API Bind ERP
├── smartsheet_service.py  # Wrapper SDK Smartsheet
├── business_logic.py      # Logica de negocio
├── main.py                # Servidor FastAPI + Scheduler
├── requirements.txt       # Dependencias Python
├── Dockerfile             # Imagen Docker
├── docker-compose.yml     # Orquestacion (desarrollo)
├── docker-compose.prod.yml # Override produccion con Traefik
├── .env.example           # Plantilla de variables
└── .dockerignore          # Exclusiones Docker build
```

## Configuracion Rapida

### 1. Clonar repositorio

```bash
git clone https://github.com/EntersysMX/smartsheet-bind-awalab.git
cd smartsheet-bind-awalab
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
nano .env  # Editar con tus credenciales
```

Variables requeridas:
- `BIND_API_KEY` - API Key de Bind ERP
- `SMARTSHEET_ACCESS_TOKEN` - Token de Smartsheet
- `SMARTSHEET_INVOICES_SHEET_ID` - ID de la hoja de facturas

### 3. Desplegar

**Desarrollo local:**
```bash
docker-compose up -d --build
```

**Produccion (con Traefik):**
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Endpoints API

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/` | Health check basico |
| GET | `/health` | Health check detallado |
| POST | `/webhook/smartsheet` | Receptor de webhooks |
| POST | `/sync/inventory` | Sincronizacion manual |
| GET | `/sync/inventory/status` | Estado del scheduler |
| POST | `/invoice/process/{sheet_id}/{row_id}` | Facturar fila manual |

## Columnas Requeridas en Smartsheet

### Hoja de Facturacion

| Columna | Tipo | Requerida | Descripcion |
|---------|------|-----------|-------------|
| RFC | Texto | Si | RFC del cliente |
| Razon Social | Texto | No | Nombre del cliente |
| Concepto | Texto | Si | Descripcion del producto/servicio |
| Descripcion | Texto | No | Detalle adicional |
| Cantidad | Numero | Si | Cantidad a facturar |
| Precio Unitario | Numero | Si | Precio sin IVA |
| Clave SAT Producto | Texto | Si | ClaveProdServ SAT (8 digitos) |
| Clave SAT Unidad | Texto | Si | ClaveUnidad SAT (2-3 chars) |
| Metodo Pago | Lista | Si | PUE o PPD |
| Forma Pago | Texto | Si | Codigo SAT (01, 03, etc) |
| Uso CFDI | Texto | Si | Uso CFDI (G01, G03, etc) |
| Regimen Fiscal | Texto | No | Regimen del receptor |
| Codigo Postal | Texto | No | CP del receptor |
| Estado | Lista | Si | Cambiar a "Facturar" para procesar |
| UUID | Texto | Auto | UUID generado (salida) |
| Folio Fiscal | Texto | Auto | Folio de factura (salida) |
| Fecha Facturacion | Fecha | Auto | Timestamp (salida) |
| Resultado | Texto | Auto | Exitoso o mensaje error (salida) |

## Flujo de Facturacion

1. Usuario llena fila en Smartsheet con datos del cliente y factura
2. Usuario cambia columna "Estado" a "Facturar"
3. Webhook notifica al middleware
4. Middleware valida datos y busca cliente en Bind por RFC
5. Middleware crea factura CFDI en Bind
6. Middleware actualiza Smartsheet con UUID, Folio y resultado

## Configurar Webhook en Smartsheet

1. Ir a Smartsheet Developer Tools
2. Crear nuevo webhook apuntando a: `https://tu-dominio.com/webhook/smartsheet`
3. Seleccionar eventos: `row.created`, `row.updated`
4. Guardar el secreto en `SMARTSHEET_WEBHOOK_SECRET`

## Monitoreo

- Los logs se guardan en `/app/logs/middleware.log`
- Health check disponible en `/health`
- Metricas de contenedor via cAdvisor/Prometheus

## Desarrollo Local

```bash
# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar servidor
python main.py
```

## Troubleshooting

### Error 429 (Rate Limit)
El cliente implementa backoff exponencial automatico. Si persiste, verificar que no hay otras aplicaciones usando la misma API Key.

### Cliente no encontrado
Verificar que el RFC existe en Bind ERP antes de facturar.

### Webhook no dispara
1. Verificar que el webhook esta activo en Smartsheet
2. Verificar que el secreto HMAC coincide
3. Revisar logs del contenedor

## Licencia

Propiedad de EnterSys MX - Uso interno

## Contacto

- Administrador: armando.cortes@entersys.mx
