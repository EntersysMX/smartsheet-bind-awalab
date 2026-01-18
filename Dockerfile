# =====================================================
# Dockerfile - Smartsheet-Bind ERP Middleware
# =====================================================

# Etapa de build
FROM python:3.11-slim as builder

WORKDIR /app

# Instalar dependencias de compilación
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependencias
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt


# Etapa de producción
FROM python:3.11-slim

# Metadatos
LABEL maintainer="DevOps Team"
LABEL description="Middleware de sincronización Smartsheet-Bind ERP"
LABEL version="1.0.0"

# Crear usuario no-root para seguridad
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

WORKDIR /app

# Copiar wheels desde builder e instalar
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache /wheels/*

# Copiar código de la aplicación
COPY config.py .
COPY bind_client.py .
COPY smartsheet_service.py .
COPY business_logic.py .
COPY database.py .
COPY main.py .

# Crear directorios para logs y datos, y dar permisos
RUN mkdir -p /app/logs /app/data && chown -R appuser:appgroup /app

# Cambiar a usuario no-root
USER appuser

# Variables de entorno por defecto
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV SERVER_HOST=0.0.0.0
ENV SERVER_PORT=8001
ENV LOG_LEVEL=INFO
ENV LOG_FILE=/app/logs/middleware.log

# Puerto expuesto
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8001/health', timeout=5)" || exit 1

# Comando de inicio
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
