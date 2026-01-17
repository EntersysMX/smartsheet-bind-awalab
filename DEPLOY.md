# Guia de Despliegue - Smartsheet-Bind ERP Middleware

**Documento para:** Claude Code u otros agentes de IA
**Servidor destino:** prod-server (GCP us-central1-c)
**Ruta en servidor:** `/srv/apps_entersys/smartsheet_bind_awalab`
**Repositorio:** https://github.com/EntersysMX/smartsheet-bind-awalab

---

## 1. Arquitectura del Despliegue

```
Internet
    |
    v
[Traefik Reverse Proxy] (puerto 443, SSL automatico)
    |
    v (red: traefik-public)
[smartsheet-bind-awalab] (puerto interno 8001)
    |
    +---> Bind ERP API (https://api.bind.com.mx/api)
    +---> Smartsheet API (https://api.smartsheet.com)
```

### Redes Docker Involucradas
- `traefik-public`: Red externa para comunicacion con Traefik (OBLIGATORIA)
- `smartsheet-bind-internal`: Red interna del proyecto

---

## 2. Prerequisitos en el Servidor

El servidor ya tiene instalado:
- Docker 28.3.2+
- Docker Compose v2.38.2+
- Traefik como reverse proxy (red `traefik-public` ya existe)
- Certificados SSL via Let's Encrypt (automatico)

Verificar que la red traefik-public existe:
```bash
docker network ls | grep traefik-public
```

---

## 3. Variables de Entorno Requeridas

Crear archivo `.env` en el directorio del proyecto con:

```env
# BIND ERP (OBLIGATORIO)
BIND_API_KEY=<jwt_token_de_bind>
BIND_API_BASE_URL=https://api.bind.com.mx/api
BIND_WAREHOUSE_ID=<uuid_del_almacen>

# SMARTSHEET (OBLIGATORIO)
SMARTSHEET_ACCESS_TOKEN=<token_de_smartsheet>
SMARTSHEET_INVOICES_SHEET_ID=<id_numerico_de_la_hoja>
SMARTSHEET_WEBHOOK_SECRET=
SMARTSHEET_INVENTORY_SHEET_ID=0

# SERVIDOR
SERVER_HOST=0.0.0.0
SERVER_PORT=8001
SMARTSHEET_BIND_DOMAIN=smartsheet-bind-awalab.entersys.mx
DEBUG_MODE=false

# LOGGING
LOG_LEVEL=INFO
LOG_FILE=/app/logs/middleware.log

# SCHEDULER
SYNC_INVENTORY_INTERVAL_MINUTES=60
```

### Como obtener las credenciales

1. **BIND_API_KEY**: Panel de Bind ERP -> Configuracion -> API
2. **BIND_WAREHOUSE_ID**: Ejecutar:
   ```bash
   curl -s -X GET "https://api.bind.com.mx/api/Warehouses" \
     -H "Authorization: Bearer <BIND_API_KEY>" | jq
   ```
3. **SMARTSHEET_ACCESS_TOKEN**: Smartsheet -> Account -> Personal Settings -> API Access
4. **SMARTSHEET_INVOICES_SHEET_ID**: URL de la hoja: `https://app.smartsheet.com/sheets/XXXXXXXXX`

---

## 4. Proceso de Despliegue Completo

### 4.1 Conectar al Servidor

```bash
gcloud compute ssh prod-server --zone=us-central1-c
```

### 4.2 Crear Directorio (solo primera vez)

```bash
sudo mkdir -p /srv/apps_entersys/smartsheet_bind_awalab
sudo chown $USER:$USER /srv/apps_entersys/smartsheet_bind_awalab
cd /srv/apps_entersys/smartsheet_bind_awalab
```

### 4.3 Clonar Repositorio (solo primera vez)

```bash
git clone https://github.com/EntersysMX/smartsheet-bind-awalab.git .
```

### 4.4 Crear archivo .env

```bash
cp .env.example .env
nano .env  # Editar con credenciales reales
```

### 4.5 Desplegar con Docker Compose

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### 4.6 Verificar Despliegue

```bash
# Estado del contenedor
docker compose ps

# Logs
docker compose logs -f

# Health check
curl https://smartsheet-bind-awalab.entersys.mx/health
```

---

## 5. Actualizacion del Codigo

### Flujo obligatorio: Git primero, luego servidor

1. **Hacer cambios localmente**
2. **Commit y push a GitHub:**
   ```bash
   git add .
   git commit -m "Descripcion del cambio"
   git push
   ```
3. **En el servidor, pull y redeploy:**
   ```bash
   cd /srv/apps_entersys/smartsheet_bind_awalab
   git pull
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```

### Comando rapido de actualizacion (desde local con gcloud)

```bash
gcloud compute ssh prod-server --zone=us-central1-c --command="cd /srv/apps_entersys/smartsheet_bind_awalab && git pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build"
```

---

## 6. Configuracion Critica de Traefik

### Labels OBLIGATORIOS en docker-compose.prod.yml

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.docker.network=traefik-public"  # CRITICO: Especifica la red
  - "traefik.http.routers.smartsheet-bind.rule=Host(`smartsheet-bind-awalab.entersys.mx`)"
  - "traefik.http.routers.smartsheet-bind.entrypoints=websecure"
  - "traefik.http.routers.smartsheet-bind.tls=true"
  - "traefik.http.routers.smartsheet-bind.tls.certresolver=letsencrypt"
  - "traefik.http.services.smartsheet-bind.loadbalancer.server.port=8001"
```

### Redes OBLIGATORIAS

```yaml
networks:
  traefik-public:
    external: true  # DEBE ser external
  internal:
    driver: bridge
```

### Error comun: Gateway Timeout (504)

**Causa:** Traefik usa la IP de la red interna en vez de `traefik-public`

**Solucion:** Agregar el label:
```yaml
- "traefik.docker.network=traefik-public"
```

**Verificar que Traefik usa la IP correcta:**
```bash
curl -s http://localhost:8080/api/http/services | jq '.[] | select(.name | contains("smartsheet"))'
```

La IP debe ser de la red `traefik-public` (172.23.x.x), NO de la red interna (172.31.x.x).

---

## 7. Troubleshooting

### Contenedor reiniciando constantemente

```bash
docker compose logs --tail=50
```

Errores comunes:
- **Pydantic error `regex`**: Cambiar a `pattern` (Pydantic v2)
- **Import error**: Verificar que todos los archivos .py estan en el Dockerfile COPY

### Verificar conectividad de APIs

```bash
# Desde dentro del contenedor
docker exec -it smartsheet-bind-awalab python -c "
from bind_client import BindClient
from smartsheet_service import SmartsheetService
print('Bind:', BindClient().health_check())
print('Smartsheet:', SmartsheetService().health_check())
"
```

### Ver routers de Traefik

```bash
curl -s http://localhost:8080/api/http/routers | jq '.[] | select(.name | contains("smartsheet"))'
```

### Ver servicios de Traefik

```bash
curl -s http://localhost:8080/api/http/services | jq '.[] | select(.name | contains("smartsheet"))'
```

### Forzar recreacion del contenedor

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate
```

### Limpiar y reconstruir desde cero

```bash
docker compose down
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --force-recreate
```

---

## 8. Estructura de Archivos

```
/srv/apps_entersys/smartsheet_bind_awalab/
├── .env                    # Credenciales (NO en git)
├── .env.example            # Plantilla de credenciales
├── .gitignore
├── docker-compose.yml      # Configuracion base
├── docker-compose.prod.yml # Override para produccion con Traefik
├── Dockerfile              # Multi-stage build Python 3.11
├── requirements.txt        # Dependencias Python
├── config.py               # Configuracion y constantes
├── bind_client.py          # Cliente API Bind ERP
├── smartsheet_service.py   # Wrapper SDK Smartsheet
├── business_logic.py       # Logica de negocio
├── main.py                 # FastAPI + Scheduler
└── README.md               # Documentacion general
```

---

## 9. Endpoints de la API

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/` | Health check basico |
| GET | `/health` | Health check con estado de conexiones |
| POST | `/webhook/smartsheet` | Receptor de webhooks de Smartsheet |
| POST | `/sync/inventory` | Disparar sincronizacion manual |
| GET | `/sync/inventory/status` | Estado del scheduler |
| POST | `/invoice/process/{sheet_id}/{row_id}` | Procesar factura manualmente |

---

## 10. Limites de Recursos

Configurados en docker-compose.prod.yml segun guia del servidor:

```yaml
deploy:
  resources:
    limits:
      cpus: "0.5"
      memory: 512M
    reservations:
      cpus: "0.1"
      memory: 128M
```

---

## 11. Logs y Monitoreo

### Ver logs en tiempo real
```bash
docker compose logs -f middleware
```

### Logs persistentes
Los logs se guardan en el volumen `smartsheet-bind-logs` en `/app/logs/middleware.log`

### Health check automatico
El contenedor tiene health check cada 30 segundos:
```bash
docker inspect smartsheet-bind-awalab --format='{{.State.Health.Status}}'
```

---

## 12. DNS Requerido

El dominio `smartsheet-bind-awalab.entersys.mx` debe apuntar a la IP del servidor.
Traefik generara automaticamente el certificado SSL con Let's Encrypt.

---

## Resumen de Comandos Frecuentes

```bash
# Conectar al servidor
gcloud compute ssh prod-server --zone=us-central1-c

# Ir al directorio
cd /srv/apps_entersys/smartsheet_bind_awalab

# Ver estado
docker compose ps

# Ver logs
docker compose logs -f

# Actualizar (despues de git push)
git pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Reiniciar
docker compose restart

# Detener
docker compose down

# Health check
curl https://smartsheet-bind-awalab.entersys.mx/health
```

---

**Documento generado por:** Claude Code
**Ultima actualizacion:** Enero 2026
