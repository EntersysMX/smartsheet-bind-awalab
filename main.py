"""
main.py - Servidor FastAPI y Scheduler para el middleware Smartsheet-Bind ERP.
Maneja webhooks de Smartsheet y ejecuta sincronizaciones programadas.
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from bind_client import BindClient
from business_logic import (
    WebhookPayload,
    process_invoice_request,
    sync_inventory,
    sync_inventory_movements,
    sync_invoices_from_bind,
)
from config import settings
from smartsheet_service import SmartsheetService

# ========== CONFIGURACIÓN DE LOGGING ==========

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.LOG_FILE),
    ],
)

logger = logging.getLogger(__name__)

# ========== SCHEDULER GLOBAL ==========

scheduler = AsyncIOScheduler()


# ========== LIFECYCLE MANAGEMENT ==========

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manejo del ciclo de vida de la aplicación."""
    # Startup
    logger.info("Iniciando middleware Smartsheet-Bind ERP...")

    # Validar configuración
    config_errors = settings.validate()
    if config_errors:
        for error in config_errors:
            logger.error(f"Error de configuración: {error}")
        if not settings.DEBUG_MODE:
            raise RuntimeError("Configuración inválida. Revise las variables de entorno.")

    # Verificar conectividad
    try:
        if settings.BIND_API_KEY:
            bind_client = BindClient()
            if bind_client.health_check():
                logger.info("Conexión a Bind ERP verificada")
            else:
                logger.warning("No se pudo verificar conexión a Bind ERP")

        if settings.SMARTSHEET_ACCESS_TOKEN:
            ss_service = SmartsheetService()
            if ss_service.health_check():
                logger.info("Conexión a Smartsheet verificada")
            else:
                logger.warning("No se pudo verificar conexión a Smartsheet")
    except Exception as e:
        logger.warning(f"Error verificando conexiones: {e}")

    # Configurar scheduler para inventario
    if settings.SYNC_INVENTORY_INTERVAL_MINUTES > 0:
        scheduler.add_job(
            run_inventory_sync,
            trigger=IntervalTrigger(minutes=settings.SYNC_INVENTORY_INTERVAL_MINUTES),
            id="sync_inventory",
            name="Sincronización de Inventario",
            replace_existing=True,
        )
        logger.info(
            f"Job de inventario configurado cada "
            f"{settings.SYNC_INVENTORY_INTERVAL_MINUTES} minutos."
        )

    # Configurar scheduler para facturas (Bind -> Smartsheet)
    if settings.SYNC_INVOICES_INTERVAL_MINUTES > 0:
        scheduler.add_job(
            run_invoices_sync,
            trigger=IntervalTrigger(minutes=settings.SYNC_INVOICES_INTERVAL_MINUTES),
            id="sync_invoices",
            name="Sincronización de Facturas Bind -> Smartsheet",
            replace_existing=True,
        )
        logger.info(
            f"Job de facturas configurado cada "
            f"{settings.SYNC_INVOICES_INTERVAL_MINUTES} minutos."
        )

    # Iniciar scheduler si hay jobs configurados
    if scheduler.get_jobs():
        scheduler.start()
        logger.info("Scheduler iniciado con los jobs configurados.")

    logger.info(f"Servidor listo en puerto {settings.SERVER_PORT}")

    yield

    # Shutdown
    logger.info("Deteniendo servidor...")
    if scheduler.running:
        scheduler.shutdown(wait=False)
    logger.info("Servidor detenido.")


# ========== FASTAPI APP ==========

app = FastAPI(
    title="Smartsheet-Bind ERP Middleware",
    description="Middleware de sincronización entre Smartsheet y Bind ERP",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== MODELOS DE RESPUESTA ==========

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    bind_connected: Optional[bool] = None
    smartsheet_connected: Optional[bool] = None


class WebhookResponse(BaseModel):
    success: bool
    message: str
    smartsheetHookResponse: Optional[str] = None


class SyncResponse(BaseModel):
    success: bool
    timestamp: str
    message: str
    details: Optional[dict] = None


# ========== FUNCIONES AUXILIARES ==========

async def run_invoice_processing(sheet_id: int, row_id: int):
    """Ejecuta el procesamiento de factura en background."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        process_invoice_request,
        sheet_id,
        row_id,
    )


async def run_inventory_sync():
    """Ejecuta la sincronización de inventario."""
    logger.info("Ejecutando sincronización programada de inventario...")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, sync_inventory)
    logger.info(f"Sincronización completada: {result}")
    return result


async def run_invoices_sync():
    """Ejecuta la sincronización de facturas Bind -> Smartsheet."""
    logger.info("Ejecutando sincronización programada de facturas...")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, sync_invoices_from_bind)
    logger.info(f"Sincronización de facturas completada: {result}")
    return result


def verify_smartsheet_signature(
    request_body: bytes,
    signature: str,
) -> bool:
    """Verifica la firma HMAC del webhook de Smartsheet."""
    if not settings.SMARTSHEET_WEBHOOK_SECRET:
        logger.warning("SMARTSHEET_WEBHOOK_SECRET no configurado, omitiendo verificación")
        return True

    ss_service = SmartsheetService()
    return ss_service.verify_webhook_signature(
        settings.SMARTSHEET_WEBHOOK_SECRET,
        signature,
        request_body,
    )


# ========== ENDPOINTS ==========

@app.get("/", response_model=HealthResponse)
async def root():
    """Endpoint raíz - health check básico."""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check detallado con verificación de conexiones."""
    bind_ok = None
    smartsheet_ok = None

    try:
        if settings.BIND_API_KEY:
            bind_client = BindClient()
            bind_ok = bind_client.health_check()
    except Exception as e:
        logger.error(f"Error verificando Bind: {e}")
        bind_ok = False

    try:
        if settings.SMARTSHEET_ACCESS_TOKEN:
            ss_service = SmartsheetService()
            smartsheet_ok = ss_service.health_check()
    except Exception as e:
        logger.error(f"Error verificando Smartsheet: {e}")
        smartsheet_ok = False

    return HealthResponse(
        status="ok" if (bind_ok is not False and smartsheet_ok is not False) else "degraded",
        timestamp=datetime.now().isoformat(),
        bind_connected=bind_ok,
        smartsheet_connected=smartsheet_ok,
    )


@app.post("/webhook/smartsheet", response_model=WebhookResponse)
async def smartsheet_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    smartsheet_hmac_sha256: Optional[str] = Header(None, alias="Smartsheet-Hmac-SHA256"),
):
    """
    Endpoint para recibir webhooks de Smartsheet.

    Maneja:
    - Challenge verification (registro inicial del webhook)
    - Eventos ROW_CHANGED para disparar facturación
    """
    # Leer body crudo para verificación de firma
    body = await request.body()

    # Verificar firma si está configurada
    if smartsheet_hmac_sha256:
        if not verify_smartsheet_signature(body, smartsheet_hmac_sha256):
            logger.warning("Firma de webhook inválida")
            raise HTTPException(status_code=401, detail="Firma inválida")

    # Parsear payload
    try:
        payload = WebhookPayload.model_validate_json(body)
    except Exception as e:
        logger.error(f"Error parseando webhook payload: {e}")
        raise HTTPException(status_code=400, detail=f"Payload inválido: {e}")

    # Manejar challenge verification (registro de webhook)
    if payload.challenge:
        logger.info("Respondiendo a challenge de verificación de Smartsheet")
        return WebhookResponse(
            success=True,
            message="Challenge accepted",
            smartsheetHookResponse=payload.challenge,
        )

    # Procesar eventos
    if not payload.events:
        return WebhookResponse(success=True, message="No events to process")

    sheet_id = payload.scopeObjectId or settings.SMARTSHEET_INVOICES_SHEET_ID
    events_processed = 0

    for event in payload.events:
        event_type = event.get("eventType")
        object_type = event.get("objectType")

        logger.debug(f"Evento recibido: {event_type} - {object_type}")

        # Solo procesar cambios en filas
        if event_type in ("created", "updated") and object_type == "row":
            row_id = event.get("rowId") or event.get("id")

            if not row_id:
                continue

            # Verificar si el estado es "Facturar"
            try:
                ss_service = SmartsheetService()
                row_data = ss_service.get_row(sheet_id, row_id)
                estado = row_data.get("Estado", "")

                if estado == "Facturar":
                    logger.info(f"Disparando facturación para fila {row_id}")
                    background_tasks.add_task(run_invoice_processing, sheet_id, row_id)
                    events_processed += 1
                else:
                    logger.debug(f"Fila {row_id} no tiene estado 'Facturar', ignorando")

            except Exception as e:
                logger.error(f"Error procesando evento para fila {row_id}: {e}")

    return WebhookResponse(
        success=True,
        message=f"Processed {events_processed} invoice requests",
    )


@app.post("/sync/inventory", response_model=SyncResponse)
async def trigger_inventory_sync(background_tasks: BackgroundTasks):
    """Dispara sincronización manual de inventario."""
    logger.info("Sincronización de inventario disparada manualmente")

    background_tasks.add_task(run_inventory_sync)

    return SyncResponse(
        success=True,
        timestamp=datetime.now().isoformat(),
        message="Sincronización de inventario iniciada en background",
    )


@app.get("/sync/inventory/status", response_model=SyncResponse)
async def inventory_sync_status():
    """Obtiene estado de la última sincronización de inventario."""
    job = scheduler.get_job("sync_inventory")

    if job:
        next_run = job.next_run_time.isoformat() if job.next_run_time else None
        return SyncResponse(
            success=True,
            timestamp=datetime.now().isoformat(),
            message="Scheduler activo",
            details={
                "next_run": next_run,
                "interval_minutes": settings.SYNC_INVENTORY_INTERVAL_MINUTES,
            },
        )

    return SyncResponse(
        success=False,
        timestamp=datetime.now().isoformat(),
        message="Scheduler no activo",
    )


@app.post("/sync/invoices", response_model=SyncResponse)
async def trigger_invoices_sync(background_tasks: BackgroundTasks):
    """Dispara sincronización manual de facturas Bind -> Smartsheet."""
    logger.info("Sincronización de facturas disparada manualmente")

    background_tasks.add_task(run_invoices_sync)

    return SyncResponse(
        success=True,
        timestamp=datetime.now().isoformat(),
        message="Sincronización de facturas iniciada en background",
    )


@app.get("/sync/invoices/status", response_model=SyncResponse)
async def invoices_sync_status():
    """Obtiene estado del scheduler de sincronización de facturas."""
    job = scheduler.get_job("sync_invoices")

    if job:
        next_run = job.next_run_time.isoformat() if job.next_run_time else None
        return SyncResponse(
            success=True,
            timestamp=datetime.now().isoformat(),
            message="Scheduler de facturas activo",
            details={
                "next_run": next_run,
                "interval_minutes": settings.SYNC_INVOICES_INTERVAL_MINUTES,
            },
        )

    return SyncResponse(
        success=False,
        timestamp=datetime.now().isoformat(),
        message="Scheduler de facturas no activo",
    )


@app.post("/invoice/process/{sheet_id}/{row_id}")
async def process_invoice_manual(
    sheet_id: int,
    row_id: int,
    background_tasks: BackgroundTasks,
):
    """
    Endpoint para disparar facturación manualmente (útil para testing/debug).

    Args:
        sheet_id: ID de la hoja de Smartsheet
        row_id: ID de la fila a procesar
    """
    logger.info(f"Facturación manual disparada: sheet={sheet_id}, row={row_id}")

    background_tasks.add_task(run_invoice_processing, sheet_id, row_id)

    return {
        "success": True,
        "message": f"Procesamiento de factura iniciado para fila {row_id}",
    }


@app.get("/scheduler/jobs")
async def list_scheduler_jobs():
    """Lista los jobs programados en el scheduler."""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        })

    return {"jobs": jobs}


# ========== MAIN ==========

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG_MODE,
        log_level=settings.LOG_LEVEL.lower(),
    )
