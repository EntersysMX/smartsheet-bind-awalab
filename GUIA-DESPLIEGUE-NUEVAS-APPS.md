# Guia de Infraestructura para Despliegue de Nuevas Aplicaciones

**Documento para:** Planificacion de nuevas aplicaciones con IA
**Servidor:** prod-server (EnterSys Production)
**Ultima actualizacion:** 31 de Diciembre, 2025

---

## 1. Especificaciones del Servidor

### Hardware (Google Cloud Platform)

| Recurso | Especificacion | Disponible |
|---------|----------------|------------|
| **CPU** | Intel Xeon @ 2.20GHz | 2 vCPUs |
| **RAM Total** | 8 GB | ~3.3 GB disponibles |
| **RAM Usada** | ~4.6 GB | 58% en uso |
| **Swap** | 8 GB | ~4 GB disponibles |
| **Disco Total** | 100 GB SSD (pd-balanced) | ~49 GB disponibles |
| **Disco Usado** | ~46 GB | 49% en uso |
| **Ubicacion** | us-central1-c | Iowa, USA |
| **Tipo Maquina** | e2-standard-2 | Proposito general |

### Sistema Operativo

- **OS:** Debian 12 (Bookworm)
- **Kernel:** Linux x86_64
- **Docker:** 28.3.2
- **Docker Compose:** v2.38.2

---

## 2. Arquitectura de Contenedores

### Estado Actual

- **Contenedores activos:** 44
- **Redes Docker:** 14
- **Volumenes persistentes:** 20+

### Reverse Proxy (Traefik)

Todas las aplicaciones web DEBEN usar Traefik como reverse proxy.

```yaml
# Configuracion requerida en docker-compose.yml
services:
  mi-app:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.mi-app.rule=Host(`miapp.dominio.com`)"
      - "traefik.http.routers.mi-app.entrypoints=websecure"
      - "traefik.http.routers.mi-app.tls.certresolver=letsencrypt"
      - "traefik.http.services.mi-app.loadbalancer.server.port=3000"
    networks:
      - traefik-public

networks:
  traefik-public:
    external: true
```

### Redes Docker Disponibles

| Red | Proposito | Usar para |
|-----|-----------|-----------|
| `traefik-public` | Exposicion web publica | Apps con dominio publico |
| `traefik` | Red interna Traefik | Comunicacion con proxy |
| `bridge` | Red por defecto | Apps aisladas |

---

## 3. Puertos en Uso (NO DISPONIBLES)

Los siguientes puertos ya estan ocupados:

| Puerto | Servicio |
|--------|----------|
| 80 | Traefik (HTTP) |
| 443 | Traefik (HTTPS) |
| 3002 | SCRAM Admin Panel |
| 3003 | Nutrition Intelligence Frontend |
| 3100 | Loki (Logs) |
| 5050 | pgAdmin |
| 5432 | PostgreSQL (multiples instancias) |
| 6379 | Redis (multiples instancias) |
| 8000 | APIs Backend |
| 8080 | Traefik Dashboard |
| 9090 | Prometheus |
| 9093 | AlertManager |
| 1433 | SQL Server |

### Puertos Recomendados para Nuevas Apps

- **3004-3010**: Frontends adicionales
- **8001-8010**: APIs/Backends adicionales
- **5433-5440**: Bases de datos PostgreSQL adicionales
- **6380-6389**: Instancias Redis adicionales

---

## 4. Stack Tecnologico Existente

### Bases de Datos Disponibles

| Tipo | Version | Uso Actual |
|------|---------|------------|
| PostgreSQL | 15, 16-alpine | Apps principales |
| MySQL | 8.0 | Mautic, Matomo |
| SQL Server | 2022-latest | Natura AdminProyectos |
| Redis | 7-alpine | Cache y sesiones |

### Servicios de Soporte

| Servicio | Proposito |
|----------|-----------|
| Traefik v2.10 | Reverse proxy, SSL automatico |
| Prometheus | Metricas |
| Grafana | Dashboards |
| AlertManager | Alertas por email |
| Loki | Agregacion de logs |

---

## 5. Restricciones y Limites

### Recursos Criticos

```
ATENCION: El servidor tiene recursos limitados

- RAM disponible: ~3.3 GB
- CPU: Solo 2 cores compartidos entre 44+ contenedores
- Disco: 49 GB libres (monitorear crecimiento)
- Swap activo: Indica presion de memoria
```

### Limites Recomendados por Contenedor

```yaml
# Ejemplo de limites en docker-compose.yml
services:
  mi-app:
    deploy:
      resources:
        limits:
          cpus: '0.5'      # Maximo 50% de 1 CPU
          memory: 512M     # Maximo 512 MB RAM
        reservations:
          cpus: '0.1'      # Minimo garantizado
          memory: 128M
```

### Aplicaciones que Consumen mas Recursos

| Aplicacion | RAM | Notas |
|------------|-----|-------|
| SQL Server | ~180 MB | Base de datos pesada |
| Prometheus | ~1 GB | Almacena metricas |
| MySQL (Matomo) | ~500 MB | Limite configurado |
| PostgreSQL | ~200 MB c/u | Multiples instancias |

---

## 6. Requisitos para Nueva Aplicacion

### Checklist de Despliegue

- [ ] Dockerfile optimizado (multi-stage build recomendado)
- [ ] docker-compose.yml con limites de recursos
- [ ] Labels de Traefik configurados
- [ ] Red `traefik-public` especificada
- [ ] Volumenes para datos persistentes
- [ ] Variables de entorno en archivo `.env`
- [ ] Health check configurado
- [ ] Puerto interno definido (no exponer directamente)

### Estructura Recomendada

```
/home/Usuario/mi-nueva-app/
├── docker-compose.yml
├── .env
├── Dockerfile
├── src/
└── data/          # Para volumenes si es necesario
```

### Template docker-compose.yml

```yaml
version: '3.8'

services:
  app:
    build: .
    container_name: mi-nueva-app
    restart: unless-stopped
    environment:
      - NODE_ENV=production
      - DATABASE_URL=${DATABASE_URL}
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.mi-app.rule=Host(`app.midominio.com`)"
      - "traefik.http.routers.mi-app.entrypoints=websecure"
      - "traefik.http.routers.mi-app.tls.certresolver=letsencrypt"
      - "traefik.http.services.mi-app.loadbalancer.server.port=3000"
    networks:
      - traefik-public
      - internal
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  database:
    image: postgres:16-alpine
    container_name: mi-app-db
    restart: unless-stopped
    environment:
      - POSTGRES_USER=${DB_USER}
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=${DB_NAME}
    volumes:
      - db-data:/var/lib/postgresql/data
    networks:
      - internal
    deploy:
      resources:
        limits:
          memory: 256M

networks:
  traefik-public:
    external: true
  internal:
    driver: bridge

volumes:
  db-data:
```

---

## 7. Monitoreo y Observabilidad

### Metricas Automaticas

Las aplicaciones son monitoreadas automaticamente por:

- **cAdvisor:** Metricas de contenedores (CPU, RAM, red)
- **Prometheus:** Almacenamiento de metricas
- **Grafana:** Visualizacion (https://monitoring.entersys.mx)

### Agregar Metricas Personalizadas (Opcional)

Si la app expone metricas Prometheus en `/metrics`:

```yaml
# Agregar label para scraping
labels:
  - "prometheus.scrape=true"
  - "prometheus.port=3000"
  - "prometheus.path=/metrics"
```

### Logs

Los logs de contenedores se agregan automaticamente via Loki.

Formato recomendado de logs:
```json
{"level":"info","timestamp":"2025-01-01T00:00:00Z","message":"App started"}
```

---

## 8. Seguridad

### Reglas de Firewall GCP

| Puerto | Protocolo | Acceso |
|--------|-----------|--------|
| 22 | TCP | SSH (restringido) |
| 80 | TCP | HTTP (redirige a 443) |
| 443 | TCP | HTTPS |
| 9090 | TCP | Prometheus (interno) |

### Buenas Practicas

1. **NUNCA** exponer puertos directamente al exterior (usar Traefik)
2. **NUNCA** usar credenciales en el codigo (usar variables de entorno)
3. **SIEMPRE** usar HTTPS (Traefik lo maneja automaticamente)
4. **SIEMPRE** definir health checks
5. Usar imagenes oficiales o verificadas
6. Mantener imagenes actualizadas

### Secretos

```yaml
# Usar archivo .env (NO commitear a git)
environment:
  - DB_PASSWORD=${DB_PASSWORD}
  - API_KEY=${API_KEY}
```

---

## 9. Costos Asociados

### Costo Base del Servidor

| Concepto | MXN/mes | USD/mes |
|----------|---------|---------|
| VM e2-standard-2 | ~$845 | ~$48 |
| Disco 100GB | ~$175 | ~$10 |
| Snapshots | ~$20 | ~$1 |
| **Total Base** | **~$1,040** | **~$59** |

### Costos Adicionales Potenciales

| Servicio | Costo | Notas |
|----------|-------|-------|
| Vertex AI (Gemini) | ~$7 MXN/dia | Si se usa IA |
| Network Egress | Variable | Trafico saliente |
| Cloud Storage | $0.02/GB/mes | Si se requiere |

---

## 10. Proceso de Despliegue

### Pasos para Desplegar Nueva App

1. **Conectar al servidor:**
   ```bash
   gcloud compute ssh prod-server --zone=us-central1-c
   ```

2. **Crear directorio:**
   ```bash
   mkdir -p ~/mi-nueva-app && cd ~/mi-nueva-app
   ```

3. **Crear archivos de configuracion:**
   - docker-compose.yml
   - .env
   - Dockerfile (si aplica)

4. **Verificar red Traefik:**
   ```bash
   docker network ls | grep traefik-public
   ```

5. **Desplegar:**
   ```bash
   docker compose up -d
   ```

6. **Verificar estado:**
   ```bash
   docker compose ps
   docker compose logs -f
   ```

7. **Verificar en Traefik:**
   - Acceder a https://app.midominio.com
   - Revisar dashboard Traefik si hay errores

---

## 11. Comandos Utiles

```bash
# Ver todos los contenedores
docker ps -a

# Ver logs de un contenedor
docker logs -f nombre-contenedor

# Ver uso de recursos
docker stats

# Limpiar recursos no usados
docker system prune -f

# Reiniciar aplicacion
docker compose restart

# Actualizar aplicacion
docker compose pull && docker compose up -d

# Ver redes
docker network ls

# Inspeccionar red
docker network inspect traefik-public
```

---

## 12. Contacto y Soporte

- **Administrador:** armando.cortes@entersys.mx
- **Alertas:** Configuradas via AlertManager
- **Monitoreo:** https://monitoring.entersys.mx

---

## Resumen Ejecutivo para IA

```
CAPACIDAD DEL SERVIDOR:
- CPU: 2 cores (limitado, compartido entre 44 contenedores)
- RAM: 3.3 GB disponibles de 8 GB
- Disco: 49 GB disponibles de 100 GB
- Swap activo indica presion de memoria

TECNOLOGIA:
- Docker + Docker Compose
- Traefik como reverse proxy (SSL automatico)
- PostgreSQL, MySQL, Redis disponibles
- Prometheus + Grafana para monitoreo

RESTRICCIONES CRITICAS:
1. Limitar memoria de nuevos contenedores a 512MB max
2. Usar red traefik-public para exposicion web
3. No exponer puertos directamente
4. Configurar health checks obligatorio
5. Preferir imagenes Alpine (menor tamano)

PARA APPS QUE REQUIEREN MAS RECURSOS:
- Considerar servidor dedicado
- O escalar el servidor actual (e2-standard-4)
```

---

**Documento generado por:** Claude Code
**Version:** 1.0
