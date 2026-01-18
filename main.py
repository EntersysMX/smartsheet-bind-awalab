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
from zoneinfo import ZoneInfo

# Zona horaria de Ciudad de México
CDMX_TZ = ZoneInfo("America/Mexico_City")

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from pathlib import Path

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

# ========== HISTORIAL DE EJECUCIONES (debe estar antes de las funciones que lo usan) ==========

job_history: list[dict] = []
MAX_HISTORY = 100


def add_to_history(job_id: str, job_name: str, status: str, details: dict = None):
    """Agrega una entrada al historial de ejecuciones."""
    entry = {
        "timestamp": datetime.now(CDMX_TZ).isoformat(),
        "job_id": job_id,
        "job_name": job_name,
        "status": status,
        "details": details or {},
    }
    job_history.insert(0, entry)
    if len(job_history) > MAX_HISTORY:
        job_history.pop()


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
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, sync_inventory)
        logger.info(f"Sincronización completada: {result}")
        # Registrar en historial
        add_to_history("sync_inventory", "Sincronización de Inventario",
                      "completed" if result.get("success") else "failed", result)
        return result
    except Exception as e:
        logger.error(f"Error en sincronización de inventario: {e}")
        add_to_history("sync_inventory", "Sincronización de Inventario", "failed", {"error": str(e)})
        raise


async def run_invoices_sync():
    """Ejecuta la sincronización de facturas Bind -> Smartsheet."""
    logger.info("Ejecutando sincronización programada de facturas...")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, sync_invoices_from_bind)
        logger.info(f"Sincronización de facturas completada: {result}")
        # Registrar en historial
        add_to_history("sync_invoices", "Sincronización de Facturas",
                      "completed" if result.get("success") else "failed", result)
        return result
    except Exception as e:
        logger.error(f"Error en sincronización de facturas: {e}")
        add_to_history("sync_invoices", "Sincronización de Facturas", "failed", {"error": str(e)})
        raise


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
        timestamp=datetime.now(CDMX_TZ).isoformat(),
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
        timestamp=datetime.now(CDMX_TZ).isoformat(),
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
        timestamp=datetime.now(CDMX_TZ).isoformat(),
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
            timestamp=datetime.now(CDMX_TZ).isoformat(),
            message="Scheduler activo",
            details={
                "next_run": next_run,
                "interval_minutes": settings.SYNC_INVENTORY_INTERVAL_MINUTES,
            },
        )

    return SyncResponse(
        success=False,
        timestamp=datetime.now(CDMX_TZ).isoformat(),
        message="Scheduler no activo",
    )


@app.post("/sync/invoices", response_model=SyncResponse)
async def trigger_invoices_sync(background_tasks: BackgroundTasks):
    """Dispara sincronización manual de facturas Bind -> Smartsheet."""
    logger.info("Sincronización de facturas disparada manualmente")

    background_tasks.add_task(run_invoices_sync)

    return SyncResponse(
        success=True,
        timestamp=datetime.now(CDMX_TZ).isoformat(),
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
            timestamp=datetime.now(CDMX_TZ).isoformat(),
            message="Scheduler de facturas activo",
            details={
                "next_run": next_run,
                "interval_minutes": settings.SYNC_INVOICES_INTERVAL_MINUTES,
            },
        )

    return SyncResponse(
        success=False,
        timestamp=datetime.now(CDMX_TZ).isoformat(),
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


# ========== ENDPOINTS DE ADMINISTRACIÓN ==========

# Metadatos de jobs (descripciones, configuración, última ejecución)
JOB_METADATA = {
    "sync_invoices": {
        "name": "Sincronización de Facturas",
        "description": "Sincroniza facturas de Bind ERP a Smartsheet automáticamente",
        "short_desc": "Bind ERP → Smartsheet | Facturas CFDI",
        "icon": "invoice",
        "details": f"""
<div class="space-y-4">
    <div class="bg-blue-900/30 border border-blue-700 rounded-lg p-4">
        <h4 class="font-semibold text-blue-300 mb-2 flex items-center">
            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            ¿Qué hace este proceso?
        </h4>
        <p class="text-gray-300">Extrae todas las facturas CFDI emitidas en <strong>Bind ERP</strong> y las registra automáticamente en una hoja de <strong>Smartsheet</strong>, evitando duplicados mediante verificación de UUID.</p>
    </div>

    <div>
        <h4 class="font-semibold mb-3 flex items-center text-green-400">
            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
            </svg>
            Flujo de Sincronización
        </h4>
        <div class="space-y-2 ml-2">
            <div class="flex items-start">
                <span class="bg-green-600 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center mr-3 mt-0.5 flex-shrink-0">1</span>
                <span class="text-gray-300">Consulta facturas de los <strong>últimos 10 minutos</strong> en Bind ERP (zona horaria CDMX)</span>
            </div>
            <div class="flex items-start">
                <span class="bg-green-600 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center mr-3 mt-0.5 flex-shrink-0">2</span>
                <span class="text-gray-300">Obtiene el mapa UUID → row_id de facturas existentes en Smartsheet</span>
            </div>
            <div class="flex items-start">
                <span class="bg-green-600 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center mr-3 mt-0.5 flex-shrink-0">3</span>
                <span class="text-gray-300"><strong>UPSERT:</strong> Si UUID existe → actualiza fila; Si no → inserta nueva</span>
            </div>
            <div class="flex items-start">
                <span class="bg-green-600 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center mr-3 mt-0.5 flex-shrink-0">4</span>
                <span class="text-gray-300">Ejecuta operaciones en lotes de 100 (optimizado para API Smartsheet)</span>
            </div>
        </div>
        <div class="mt-3 p-2 bg-blue-900/20 border border-blue-700/50 rounded text-xs text-blue-300">
            <strong>Zona Horaria:</strong> America/Mexico_City (CDMX) - Las fechas se convierten automáticamente
        </div>
    </div>

    <div>
        <h4 class="font-semibold mb-3 flex items-center text-purple-400">
            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2 1 3 3 3h10c2 0 3-1 3-3V7c0-2-1-3-3-3H7C5 4 4 5 4 7z"></path>
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6M9 16h6"></path>
            </svg>
            Campos Sincronizados (16 columnas)
        </h4>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">UUID</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Serie</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Folio</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Fecha</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Cliente</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">RFC</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Subtotal</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">IVA</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Total</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Moneda</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Uso CFDI</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Método Pago</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Estatus</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Comentarios</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Orden Compra</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Bind ID</span>
        </div>
    </div>

    <div class="bg-gray-700/30 rounded-lg p-4">
        <h4 class="font-semibold mb-3 flex items-center text-cyan-400">
            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path>
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
            </svg>
            Configuración Actual
        </h4>
        <div class="space-y-2 text-sm">
            <div class="flex flex-col sm:flex-row sm:justify-between">
                <span class="text-gray-400">Hoja Smartsheet:</span>
                <span class="font-mono text-blue-400">{settings.SMARTSHEET_INVOICES_SHEET_ID}</span>
            </div>
            <div class="flex flex-col sm:flex-row sm:justify-between">
                <span class="text-gray-400">URL Smartsheet:</span>
                <a href="https://app.smartsheet.com/sheets/{settings.SMARTSHEET_INVOICES_SHEET_ID}" target="_blank" class="text-blue-400 hover:underline truncate">Abrir hoja ↗</a>
            </div>
            <div class="flex flex-col sm:flex-row sm:justify-between">
                <span class="text-gray-400">Endpoint Bind:</span>
                <span class="font-mono text-green-400">GET /api/Invoices</span>
            </div>
            <div class="flex flex-col sm:flex-row sm:justify-between">
                <span class="text-gray-400">Paginación:</span>
                <span class="text-gray-300">OData ($top, $skip, $orderby)</span>
            </div>
            <div class="flex flex-col sm:flex-row sm:justify-between">
                <span class="text-gray-400">Detección duplicados:</span>
                <span class="text-gray-300">Por UUID de factura CFDI</span>
            </div>
        </div>
    </div>
</div>
""",
        "source": "Bind ERP → Smartsheet",
        "endpoint": "GET /api/Invoices",
        "sheet_var": "SMARTSHEET_INVOICES_SHEET_ID",
        "sheet_id": settings.SMARTSHEET_INVOICES_SHEET_ID,
    },
    "sync_inventory": {
        "name": "Sincronización de Inventario",
        "description": "Sincroniza existencias de productos desde Bind ERP",
        "short_desc": "Bind ERP → Smartsheet | Stock de almacén",
        "icon": "inventory",
        "details": f"""
<div class="space-y-4">
    <div class="bg-amber-900/30 border border-amber-700 rounded-lg p-4">
        <h4 class="font-semibold text-amber-300 mb-2 flex items-center">
            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            ¿Qué hace este proceso?
        </h4>
        <p class="text-gray-300">Obtiene las <strong>existencias actuales</strong> del almacén configurado en Bind ERP y actualiza la hoja de inventario en Smartsheet con las cantidades en stock.</p>
    </div>

    <div>
        <h4 class="font-semibold mb-3 flex items-center text-green-400">
            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
            </svg>
            Flujo de Sincronización
        </h4>
        <div class="space-y-2 ml-2">
            <div class="flex items-start">
                <span class="bg-green-600 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center mr-3 mt-0.5 flex-shrink-0">1</span>
                <span class="text-gray-300">Consulta el inventario del almacén en Bind ERP</span>
            </div>
            <div class="flex items-start">
                <span class="bg-green-600 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center mr-3 mt-0.5 flex-shrink-0">2</span>
                <span class="text-gray-300">Obtiene los productos existentes en la hoja de Smartsheet</span>
            </div>
            <div class="flex items-start">
                <span class="bg-green-600 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center mr-3 mt-0.5 flex-shrink-0">3</span>
                <span class="text-gray-300">Actualiza existencias de productos ya registrados</span>
            </div>
            <div class="flex items-start">
                <span class="bg-green-600 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center mr-3 mt-0.5 flex-shrink-0">4</span>
                <span class="text-gray-300">Registra la fecha/hora de última actualización</span>
            </div>
        </div>
    </div>

    <div>
        <h4 class="font-semibold mb-3 flex items-center text-purple-400">
            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2 1 3 3 3h10c2 0 3-1 3-3V7c0-2-1-3-3-3H7C5 4 4 5 4 7z"></path>
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6M9 16h6"></path>
            </svg>
            Campos Sincronizados (5 columnas)
        </h4>
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-2 text-sm">
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Código</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Nombre</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Existencia</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Almacén</span>
            <span class="bg-gray-700/50 px-2 py-1 rounded text-gray-300">Última Actualización</span>
        </div>
    </div>

    <div class="bg-gray-700/30 rounded-lg p-4">
        <h4 class="font-semibold mb-3 flex items-center text-cyan-400">
            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path>
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
            </svg>
            Configuración Actual
        </h4>
        <div class="space-y-2 text-sm">
            <div class="flex flex-col sm:flex-row sm:justify-between">
                <span class="text-gray-400">Hoja Smartsheet:</span>
                <span class="font-mono {'text-yellow-400' if settings.SMARTSHEET_INVENTORY_SHEET_ID == 0 else 'text-blue-400'}">{settings.SMARTSHEET_INVENTORY_SHEET_ID if settings.SMARTSHEET_INVENTORY_SHEET_ID != 0 else 'No configurada'}</span>
            </div>
            <div class="flex flex-col sm:flex-row sm:justify-between">
                <span class="text-gray-400">ID Almacén Bind:</span>
                <span class="font-mono text-green-400 truncate">{settings.BIND_WAREHOUSE_ID or 'No configurado'}</span>
            </div>
            <div class="flex flex-col sm:flex-row sm:justify-between">
                <span class="text-gray-400">Endpoint Bind:</span>
                <span class="font-mono text-green-400">GET /api/Inventory</span>
            </div>
        </div>
    </div>

    {'<div class="bg-yellow-900/30 border border-yellow-600 rounded-lg p-4"><p class="text-yellow-300 text-sm flex items-start"><svg class="w-5 h-5 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg><span><strong>Proceso inactivo:</strong> La hoja de inventario no está configurada (SMARTSHEET_INVENTORY_SHEET_ID=0). Configure el ID de la hoja en las variables de entorno para activar este proceso.</span></p></div>' if settings.SMARTSHEET_INVENTORY_SHEET_ID == 0 else ''}
</div>
""",
        "source": "Bind ERP → Smartsheet",
        "endpoint": "GET /api/Inventory",
        "sheet_var": "SMARTSHEET_INVENTORY_SHEET_ID",
        "sheet_id": settings.SMARTSHEET_INVENTORY_SHEET_ID,
    },
}

# Última ejecución de cada job
job_last_run: dict[str, dict] = {}


@app.get("/api/admin/jobs")
async def admin_list_jobs():
    """Lista detallada de todos los jobs para el panel de administración."""
    jobs = []
    for job in scheduler.get_jobs():
        # Obtener información del trigger
        trigger_info = {}
        if hasattr(job.trigger, 'interval'):
            trigger_info["type"] = "interval"
            trigger_info["interval_seconds"] = job.trigger.interval.total_seconds()
            trigger_info["interval_minutes"] = job.trigger.interval.total_seconds() / 60

        # Obtener metadatos del job
        metadata = JOB_METADATA.get(job.id, {})
        last_run = job_last_run.get(job.id, {})

        jobs.append({
            "id": job.id,
            "name": job.name,
            "description": metadata.get("description", ""),
            "source": metadata.get("source", ""),
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": trigger_info,
            "pending": job.pending,
            "last_run": last_run,
        })

    return {
        "success": True,
        "timestamp": datetime.now(CDMX_TZ).isoformat(),
        "scheduler_running": scheduler.running,
        "jobs": jobs,
    }


@app.get("/api/admin/jobs/{job_id}/details")
async def admin_get_job_details(job_id: str):
    """Obtiene los detalles completos de un job."""
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' no encontrado")

    metadata = JOB_METADATA.get(job_id, {})
    last_run = job_last_run.get(job_id, {})

    # Obtener historial reciente de este job
    recent_history = [h for h in job_history if h["job_id"] == job_id][:10]

    # Información del trigger
    trigger_info = {}
    if hasattr(job.trigger, 'interval'):
        trigger_info["type"] = "interval"
        trigger_info["interval_seconds"] = job.trigger.interval.total_seconds()
        trigger_info["interval_minutes"] = job.trigger.interval.total_seconds() / 60

    return {
        "success": True,
        "job": {
            "id": job.id,
            "name": job.name,
            "description": metadata.get("description", "Sin descripción"),
            "details_html": metadata.get("details", "<p>Sin detalles disponibles</p>"),
            "source": metadata.get("source", ""),
            "endpoint": metadata.get("endpoint", ""),
            "sheet_var": metadata.get("sheet_var", ""),
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": trigger_info,
            "pending": job.pending,
            "paused": job.next_run_time is None,
        },
        "last_run": last_run,
        "recent_history": recent_history,
    }


@app.get("/api/admin/history")
async def admin_get_history(limit: int = 50):
    """Obtiene el historial de ejecuciones."""
    return {
        "success": True,
        "timestamp": datetime.now(CDMX_TZ).isoformat(),
        "history": job_history[:limit],
    }


@app.post("/api/admin/jobs/{job_id}/pause")
async def admin_pause_job(job_id: str):
    """Pausa un job programado."""
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' no encontrado")

    scheduler.pause_job(job_id)
    add_to_history(job_id, job.name, "paused")
    logger.info(f"Job '{job_id}' pausado")

    return {
        "success": True,
        "message": f"Job '{job_id}' pausado",
        "timestamp": datetime.now(CDMX_TZ).isoformat(),
    }


@app.post("/api/admin/jobs/{job_id}/resume")
async def admin_resume_job(job_id: str):
    """Reanuda un job pausado."""
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' no encontrado")

    scheduler.resume_job(job_id)
    add_to_history(job_id, job.name, "resumed")
    logger.info(f"Job '{job_id}' reanudado")

    return {
        "success": True,
        "message": f"Job '{job_id}' reanudado",
        "timestamp": datetime.now(CDMX_TZ).isoformat(),
    }


@app.post("/api/admin/jobs/{job_id}/run")
async def admin_run_job_now(job_id: str, background_tasks: BackgroundTasks):
    """Ejecuta un job inmediatamente."""
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' no encontrado")

    # Ejecutar según el tipo de job
    if job_id == "sync_inventory":
        background_tasks.add_task(run_inventory_sync)
    elif job_id == "sync_invoices":
        background_tasks.add_task(run_invoices_sync)
    else:
        raise HTTPException(status_code=400, detail=f"Job '{job_id}' no puede ejecutarse manualmente")

    add_to_history(job_id, job.name, "manual_run")
    logger.info(f"Job '{job_id}' ejecutado manualmente")

    return {
        "success": True,
        "message": f"Job '{job_id}' iniciado",
        "timestamp": datetime.now(CDMX_TZ).isoformat(),
    }


@app.put("/api/admin/jobs/{job_id}/interval")
async def admin_update_interval(job_id: str, minutes: int):
    """Actualiza el intervalo de un job."""
    if minutes < 1:
        raise HTTPException(status_code=400, detail="El intervalo mínimo es 1 minuto")
    if minutes > 1440:
        raise HTTPException(status_code=400, detail="El intervalo máximo es 1440 minutos (24 horas)")

    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' no encontrado")

    # Reschedular con nuevo intervalo
    scheduler.reschedule_job(job_id, trigger=IntervalTrigger(minutes=minutes))
    add_to_history(job_id, job.name, "interval_changed", {"new_interval": minutes})
    logger.info(f"Job '{job_id}' reprogramado a cada {minutes} minutos")

    return {
        "success": True,
        "message": f"Job '{job_id}' reprogramado a cada {minutes} minutos",
        "timestamp": datetime.now(CDMX_TZ).isoformat(),
    }


@app.get("/api/admin/stats")
async def admin_get_stats():
    """Obtiene estadísticas generales del sistema."""
    bind_ok = None
    smartsheet_ok = None

    try:
        if settings.BIND_API_KEY:
            bind_client = BindClient()
            bind_ok = bind_client.health_check()
    except Exception:
        bind_ok = False

    try:
        if settings.SMARTSHEET_ACCESS_TOKEN:
            ss_service = SmartsheetService()
            smartsheet_ok = ss_service.health_check()
    except Exception:
        smartsheet_ok = False

    # Contar ejecuciones exitosas/fallidas
    successful = sum(1 for h in job_history if h["status"] in ["completed", "manual_run"])
    failed = sum(1 for h in job_history if h["status"] == "failed")

    return {
        "success": True,
        "timestamp": datetime.now(CDMX_TZ).isoformat(),
        "connections": {
            "bind": bind_ok,
            "smartsheet": smartsheet_ok,
        },
        "scheduler": {
            "running": scheduler.running,
            "job_count": len(scheduler.get_jobs()),
        },
        "history": {
            "total": len(job_history),
            "successful": successful,
            "failed": failed,
        },
    }


# ========== DASHBOARD WEB ==========

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard():
    """Sirve el dashboard de administración."""
    dashboard_path = Path(__file__).parent / "static" / "dashboard.html"
    if dashboard_path.exists():
        return FileResponse(dashboard_path, media_type="text/html")
    else:
        # Fallback: servir dashboard embebido
        return HTMLResponse(content=get_embedded_dashboard(), status_code=200)


def get_embedded_dashboard() -> str:
    """Retorna el HTML del dashboard embebido."""
    return '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panel de Administración - Smartsheet-Bind</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
        .animate-pulse-slow { animation: pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
    </style>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    <!-- Header -->
    <header class="bg-gray-800 border-b border-gray-700 px-4 sm:px-6 py-3 sm:py-4">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between max-w-7xl mx-auto gap-3 sm:gap-0">
            <div class="flex items-center space-x-3">
                <div class="w-8 h-8 sm:w-10 sm:h-10 bg-blue-600 rounded-lg flex items-center justify-center flex-shrink-0">
                    <svg class="w-5 h-5 sm:w-6 sm:h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
                    </svg>
                </div>
                <div>
                    <h1 class="text-lg sm:text-xl font-bold">Smartsheet-Bind ERP</h1>
                    <p class="text-xs sm:text-sm text-gray-400">Panel de Administración</p>
                </div>
            </div>
            <div class="flex items-center justify-between sm:justify-end space-x-3 sm:space-x-4">
                <div id="connection-status" class="flex items-center space-x-2">
                    <span class="text-xs sm:text-sm text-gray-400">Cargando...</span>
                </div>
                <button onclick="refreshAll()" class="bg-blue-600 hover:bg-blue-700 px-3 sm:px-4 py-2 rounded-lg text-xs sm:text-sm font-medium transition">
                    Actualizar
                </button>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 py-4 sm:py-8">
        <!-- Stats Cards -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-6 mb-6 sm:mb-8">
            <div class="bg-gray-800 rounded-xl p-3 sm:p-6 border border-gray-700">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-xs sm:text-sm text-gray-400">Jobs Activos</p>
                        <p id="stat-jobs" class="text-xl sm:text-3xl font-bold mt-1">-</p>
                    </div>
                    <div class="w-8 h-8 sm:w-12 sm:h-12 bg-blue-600/20 rounded-lg flex items-center justify-center">
                        <svg class="w-4 h-4 sm:w-6 sm:h-6 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                    </div>
                </div>
            </div>
            <div class="bg-gray-800 rounded-xl p-3 sm:p-6 border border-gray-700">
                <div class="flex items-center justify-between">
                    <div class="min-w-0 flex-1">
                        <p class="text-xs sm:text-sm text-gray-400">Bind ERP</p>
                        <p id="stat-bind" class="text-sm sm:text-xl font-bold mt-1 truncate">-</p>
                    </div>
                    <div id="bind-icon" class="w-8 h-8 sm:w-12 sm:h-12 bg-gray-600/20 rounded-lg flex items-center justify-center flex-shrink-0 ml-2">
                        <svg class="w-4 h-4 sm:w-6 sm:h-6 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M12 5l7 7-7 7"></path>
                        </svg>
                    </div>
                </div>
            </div>
            <div class="bg-gray-800 rounded-xl p-3 sm:p-6 border border-gray-700">
                <div class="flex items-center justify-between">
                    <div class="min-w-0 flex-1">
                        <p class="text-xs sm:text-sm text-gray-400">Smartsheet</p>
                        <p id="stat-smartsheet" class="text-sm sm:text-xl font-bold mt-1 truncate">-</p>
                    </div>
                    <div id="smartsheet-icon" class="w-8 h-8 sm:w-12 sm:h-12 bg-gray-600/20 rounded-lg flex items-center justify-center flex-shrink-0 ml-2">
                        <svg class="w-4 h-4 sm:w-6 sm:h-6 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2"></path>
                        </svg>
                    </div>
                </div>
            </div>
            <div class="bg-gray-800 rounded-xl p-3 sm:p-6 border border-gray-700">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-xs sm:text-sm text-gray-400">Ejecuciones</p>
                        <p id="stat-executions" class="text-xl sm:text-3xl font-bold mt-1">-</p>
                    </div>
                    <div class="w-8 h-8 sm:w-12 sm:h-12 bg-green-600/20 rounded-lg flex items-center justify-center">
                        <svg class="w-4 h-4 sm:w-6 sm:h-6 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                    </div>
                </div>
            </div>
        </div>

        <!-- Jobs Section -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6 mb-6 sm:mb-8">
            <div class="bg-gray-800 rounded-xl border border-gray-700">
                <div class="px-4 sm:px-6 py-3 sm:py-4 border-b border-gray-700">
                    <h2 class="text-base sm:text-lg font-semibold">Procesos Programados</h2>
                </div>
                <div id="jobs-container" class="p-3 sm:p-6 space-y-3 sm:space-y-4">
                    <p class="text-gray-400 text-sm">Cargando jobs...</p>
                </div>
            </div>

            <div class="bg-gray-800 rounded-xl border border-gray-700">
                <div class="px-4 sm:px-6 py-3 sm:py-4 border-b border-gray-700">
                    <h2 class="text-base sm:text-lg font-semibold">Historial de Ejecuciones</h2>
                </div>
                <div id="history-container" class="p-3 sm:p-6 max-h-80 sm:max-h-96 overflow-y-auto">
                    <p class="text-gray-400 text-sm">Cargando historial...</p>
                </div>
            </div>
        </div>

        <!-- Interval Modal -->
        <div id="interval-modal" class="fixed inset-0 bg-black/50 hidden items-center justify-center z-50 p-4">
            <div class="bg-gray-800 rounded-xl p-4 sm:p-6 w-full max-w-md mx-auto border border-gray-700">
                <h3 class="text-base sm:text-lg font-semibold mb-3 sm:mb-4">Cambiar Intervalo</h3>
                <p id="modal-job-name" class="text-sm text-gray-400 mb-3 sm:mb-4"></p>
                <div class="mb-4">
                    <label class="block text-xs sm:text-sm text-gray-400 mb-2">Intervalo (minutos)</label>
                    <input type="number" id="interval-input" min="1" max="1440"
                           class="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 sm:px-4 py-2 text-white text-sm sm:text-base focus:outline-none focus:border-blue-500">
                </div>
                <div class="flex space-x-3">
                    <button onclick="closeModal()" class="flex-1 bg-gray-700 hover:bg-gray-600 px-3 sm:px-4 py-2 rounded-lg transition text-sm sm:text-base">
                        Cancelar
                    </button>
                    <button onclick="saveInterval()" class="flex-1 bg-blue-600 hover:bg-blue-700 px-3 sm:px-4 py-2 rounded-lg transition text-sm sm:text-base">
                        Guardar
                    </button>
                </div>
            </div>
        </div>

        <!-- Details Modal -->
        <div id="details-modal" class="fixed inset-0 bg-black/50 hidden items-center justify-center z-50 overflow-y-auto p-2 sm:p-4">
            <div class="bg-gray-800 rounded-xl w-full max-w-2xl mx-auto my-4 sm:my-8 border border-gray-700">
                <div class="flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 border-b border-gray-700">
                    <div class="min-w-0 flex-1 pr-4">
                        <h3 id="details-title" class="text-base sm:text-lg font-semibold truncate">Detalles del Proceso</h3>
                        <p id="details-subtitle" class="text-xs sm:text-sm text-gray-400 truncate"></p>
                    </div>
                    <button onclick="closeDetailsModal()" class="text-gray-400 hover:text-white transition flex-shrink-0">
                        <svg class="w-5 h-5 sm:w-6 sm:h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                        </svg>
                    </button>
                </div>
                <div class="p-4 sm:p-6">
                    <!-- Status Badge -->
                    <div class="flex flex-wrap items-center gap-2 sm:gap-4 mb-4 sm:mb-6">
                        <span id="details-status" class="px-2 sm:px-3 py-1 rounded-full text-xs sm:text-sm font-medium"></span>
                        <span id="details-source" class="text-xs sm:text-sm text-gray-400"></span>
                    </div>

                    <!-- Info Grid -->
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4 mb-4 sm:mb-6 p-3 sm:p-4 bg-gray-700/30 rounded-lg">
                        <div>
                            <p class="text-xs text-gray-400 uppercase">Intervalo</p>
                            <p id="details-interval" class="font-semibold text-sm sm:text-base"></p>
                        </div>
                        <div>
                            <p class="text-xs text-gray-400 uppercase">Próxima Ejecución</p>
                            <p id="details-next-run" class="font-semibold text-sm sm:text-base"></p>
                        </div>
                        <div>
                            <p class="text-xs text-gray-400 uppercase">Endpoint API</p>
                            <p id="details-endpoint" class="font-mono text-xs sm:text-sm text-blue-400 break-all"></p>
                        </div>
                        <div>
                            <p class="text-xs text-gray-400 uppercase">Variable Config</p>
                            <p id="details-sheet-var" class="font-mono text-xs sm:text-sm text-purple-400 break-all"></p>
                        </div>
                    </div>

                    <!-- Details Content -->
                    <div id="details-content" class="prose prose-invert prose-sm sm:prose max-w-none text-sm sm:text-base">
                        <p class="text-gray-400">Cargando detalles...</p>
                    </div>

                    <!-- Recent History -->
                    <div class="mt-4 sm:mt-6 pt-4 sm:pt-6 border-t border-gray-700">
                        <h4 class="font-semibold text-sm sm:text-base mb-2 sm:mb-3">Historial Reciente</h4>
                        <div id="details-history" class="space-y-2 max-h-32 sm:max-h-40 overflow-y-auto">
                            <p class="text-gray-400 text-xs sm:text-sm">Sin historial</p>
                        </div>
                    </div>
                </div>
                <div class="px-4 sm:px-6 py-3 sm:py-4 border-t border-gray-700 flex justify-end">
                    <button onclick="closeDetailsModal()" class="bg-gray-700 hover:bg-gray-600 px-4 sm:px-6 py-2 rounded-lg transition text-sm sm:text-base">
                        Cerrar
                    </button>
                </div>
            </div>
        </div>
    </main>

    <script>
        let currentJobId = null;

        // Formatear fecha
        function formatDate(isoString) {
            if (!isoString) return '-';
            const date = new Date(isoString);
            return date.toLocaleString('es-MX', {
                day: '2-digit',
                month: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        }

        // Cargar estadísticas
        async function loadStats() {
            try {
                const res = await fetch('/api/admin/stats');
                const data = await res.json();

                document.getElementById('stat-jobs').textContent = data.scheduler.job_count;
                document.getElementById('stat-executions').textContent = data.history.total;

                // Bind status
                const bindStatus = data.connections.bind;
                document.getElementById('stat-bind').textContent = bindStatus ? 'Conectado' : 'Error';
                document.getElementById('stat-bind').className = `text-xl font-bold mt-1 ${bindStatus ? 'text-green-400' : 'text-red-400'}`;
                document.getElementById('bind-icon').className = `w-12 h-12 ${bindStatus ? 'bg-green-600/20' : 'bg-red-600/20'} rounded-lg flex items-center justify-center`;

                // Smartsheet status
                const ssStatus = data.connections.smartsheet;
                document.getElementById('stat-smartsheet').textContent = ssStatus ? 'Conectado' : 'Error';
                document.getElementById('stat-smartsheet').className = `text-xl font-bold mt-1 ${ssStatus ? 'text-green-400' : 'text-red-400'}`;
                document.getElementById('smartsheet-icon').className = `w-12 h-12 ${ssStatus ? 'bg-green-600/20' : 'bg-red-600/20'} rounded-lg flex items-center justify-center`;

                // Connection status header
                const statusHtml = `
                    <span class="w-2 h-2 rounded-full ${bindStatus && ssStatus ? 'bg-green-500' : 'bg-yellow-500'}"></span>
                    <span class="text-sm ${bindStatus && ssStatus ? 'text-green-400' : 'text-yellow-400'}">
                        ${bindStatus && ssStatus ? 'Sistemas operativos' : 'Conexión parcial'}
                    </span>
                `;
                document.getElementById('connection-status').innerHTML = statusHtml;
            } catch (e) {
                console.error('Error loading stats:', e);
            }
        }

        // Cargar jobs
        async function loadJobs() {
            try {
                const res = await fetch('/api/admin/jobs');
                const data = await res.json();

                const container = document.getElementById('jobs-container');

                if (data.jobs.length === 0) {
                    container.innerHTML = '<p class="text-gray-400">No hay jobs configurados</p>';
                    return;
                }

                container.innerHTML = data.jobs.map(job => {
                    const isPaused = !job.next_run;
                    const intervalMin = job.trigger.interval_minutes ? Math.round(job.trigger.interval_minutes) : '-';
                    const jobIcon = job.id === 'sync_invoices' ?
                        '<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>' :
                        '<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"></path></svg>';

                    return `
                        <div class="bg-gray-700/50 rounded-lg border border-gray-600 overflow-hidden">
                            <!-- Header con icono y estado -->
                            <div class="p-3 sm:p-4 border-b border-gray-600">
                                <div class="flex items-start gap-3">
                                    <div class="w-10 h-10 sm:w-12 sm:h-12 ${job.id === 'sync_invoices' ? 'bg-blue-600/20 text-blue-400' : 'bg-amber-600/20 text-amber-400'} rounded-lg flex items-center justify-center flex-shrink-0">
                                        ${jobIcon}
                                    </div>
                                    <div class="flex-1 min-w-0">
                                        <div class="flex items-center justify-between gap-2">
                                            <h3 class="font-semibold text-sm sm:text-base">${job.name}</h3>
                                            <span class="px-2 py-0.5 rounded-full text-xs font-medium flex-shrink-0 ${isPaused ? 'bg-yellow-600/20 text-yellow-400' : 'bg-green-600/20 text-green-400'}">
                                                ${isPaused ? 'Pausado' : 'Activo'}
                                            </span>
                                        </div>
                                        <p class="text-xs text-gray-400 mt-0.5">${job.description || ''}</p>
                                        ${job.source ? `<p class="text-xs text-blue-400 mt-1">${job.source}</p>` : ''}
                                    </div>
                                </div>
                            </div>

                            <!-- Info de tiempos -->
                            <div class="px-3 sm:px-4 py-2 bg-gray-800/30 grid grid-cols-2 gap-2 text-xs sm:text-sm">
                                <div>
                                    <span class="text-gray-500">Intervalo:</span>
                                    <span class="font-medium ml-1">${intervalMin} min</span>
                                </div>
                                <div>
                                    <span class="text-gray-500">Próxima:</span>
                                    <span class="font-medium ml-1">${formatDate(job.next_run)}</span>
                                </div>
                            </div>

                            <!-- BOTÓN VER DETALLES PROMINENTE -->
                            <button onclick="openDetailsModal('${job.id}')"
                                    class="w-full bg-gradient-to-r ${job.id === 'sync_invoices' ? 'from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500' : 'from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500'} px-4 py-3 text-sm font-medium transition flex items-center justify-center gap-2">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                                </svg>
                                <span>VER DETALLES DEL PROCESO</span>
                            </button>

                            <!-- Botones de acciones -->
                            <div class="p-3 sm:p-4 flex flex-wrap gap-2">
                                <button onclick="runJob('${job.id}')"
                                        class="flex-1 min-w-[80px] bg-gray-600 hover:bg-gray-500 px-3 py-2 rounded-lg text-xs sm:text-sm transition flex items-center justify-center gap-1">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path>
                                    </svg>
                                    Ejecutar
                                </button>
                                ${isPaused ? `
                                    <button onclick="resumeJob('${job.id}')"
                                            class="flex-1 min-w-[80px] bg-green-600 hover:bg-green-500 px-3 py-2 rounded-lg text-xs sm:text-sm transition flex items-center justify-center gap-1">
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path>
                                        </svg>
                                        Reanudar
                                    </button>
                                ` : `
                                    <button onclick="pauseJob('${job.id}')"
                                            class="flex-1 min-w-[80px] bg-yellow-600 hover:bg-yellow-500 px-3 py-2 rounded-lg text-xs sm:text-sm transition flex items-center justify-center gap-1">
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                                        </svg>
                                        Pausar
                                    </button>
                                `}
                                <button onclick="openIntervalModal('${job.id}', '${job.name}', ${intervalMin})"
                                        class="bg-gray-600 hover:bg-gray-500 px-2 sm:px-3 py-2 rounded-lg text-xs sm:text-sm transition flex items-center justify-center">
                                    <svg class="w-3 h-3 sm:w-4 sm:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                                    </svg>
                                    <span class="ml-1 sm:hidden">Tiempo</span>
                                </button>
                            </div>
                        </div>
                    `;
                }).join('');
            } catch (e) {
                console.error('Error loading jobs:', e);
                document.getElementById('jobs-container').innerHTML = '<p class="text-red-400">Error cargando jobs</p>';
            }
        }

        // Cargar historial
        async function loadHistory() {
            try {
                const res = await fetch('/api/admin/history?limit=20');
                const data = await res.json();

                const container = document.getElementById('history-container');

                if (data.history.length === 0) {
                    container.innerHTML = `
                        <div class="text-center py-6">
                            <svg class="w-12 h-12 mx-auto text-gray-600 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                            </svg>
                            <p class="text-gray-400 text-sm mb-2">Sin ejecuciones registradas</p>
                            <p class="text-gray-500 text-xs">El historial aparecerá cuando los procesos se ejecuten automáticamente o de forma manual.</p>
                            <p class="text-gray-500 text-xs mt-2">Los procesos se ejecutan cada <strong class="text-gray-400">2 min</strong> (facturas) y <strong class="text-gray-400">60 min</strong> (inventario).</p>
                        </div>
                    `;
                    return;
                }

                container.innerHTML = data.history.map(entry => {
                    const statusColors = {
                        'completed': 'bg-green-600/20 text-green-400',
                        'manual_run': 'bg-blue-600/20 text-blue-400',
                        'paused': 'bg-yellow-600/20 text-yellow-400',
                        'resumed': 'bg-green-600/20 text-green-400',
                        'interval_changed': 'bg-purple-600/20 text-purple-400',
                        'failed': 'bg-red-600/20 text-red-400',
                    };
                    const statusLabels = {
                        'completed': 'Completado',
                        'manual_run': 'Ejecutado',
                        'paused': 'Pausado',
                        'resumed': 'Reanudado',
                        'interval_changed': 'Intervalo cambiado',
                        'failed': 'Fallido',
                    };

                    return `
                        <div class="flex items-center justify-between py-2 border-b border-gray-700 last:border-0 gap-2">
                            <div class="min-w-0 flex-1">
                                <p class="text-xs sm:text-sm font-medium truncate">${entry.job_name}</p>
                                <p class="text-xs text-gray-400">${formatDate(entry.timestamp)}</p>
                            </div>
                            <span class="px-2 py-1 rounded text-xs flex-shrink-0 ${statusColors[entry.status] || 'bg-gray-600 text-gray-300'}">
                                ${statusLabels[entry.status] || entry.status}
                            </span>
                        </div>
                    `;
                }).join('');
            } catch (e) {
                console.error('Error loading history:', e);
            }
        }

        // Acciones de jobs
        async function runJob(jobId) {
            try {
                const res = await fetch(`/api/admin/jobs/${jobId}/run`, { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    showNotification('Job iniciado correctamente', 'success');
                    refreshAll();
                }
            } catch (e) {
                showNotification('Error al ejecutar job', 'error');
            }
        }

        async function pauseJob(jobId) {
            try {
                const res = await fetch(`/api/admin/jobs/${jobId}/pause`, { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    showNotification('Job pausado', 'success');
                    refreshAll();
                }
            } catch (e) {
                showNotification('Error al pausar job', 'error');
            }
        }

        async function resumeJob(jobId) {
            try {
                const res = await fetch(`/api/admin/jobs/${jobId}/resume`, { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    showNotification('Job reanudado', 'success');
                    refreshAll();
                }
            } catch (e) {
                showNotification('Error al reanudar job', 'error');
            }
        }

        // Modal de intervalo
        function openIntervalModal(jobId, jobName, currentInterval) {
            currentJobId = jobId;
            document.getElementById('modal-job-name').textContent = jobName;
            document.getElementById('interval-input').value = currentInterval;
            document.getElementById('interval-modal').classList.remove('hidden');
            document.getElementById('interval-modal').classList.add('flex');
        }

        function closeModal() {
            document.getElementById('interval-modal').classList.add('hidden');
            document.getElementById('interval-modal').classList.remove('flex');
            currentJobId = null;
        }

        async function saveInterval() {
            const minutes = parseInt(document.getElementById('interval-input').value);
            if (isNaN(minutes) || minutes < 1 || minutes > 1440) {
                showNotification('Intervalo inválido (1-1440 min)', 'error');
                return;
            }

            try {
                const res = await fetch(`/api/admin/jobs/${currentJobId}/interval?minutes=${minutes}`, { method: 'PUT' });
                const data = await res.json();
                if (data.success) {
                    showNotification('Intervalo actualizado', 'success');
                    closeModal();
                    refreshAll();
                }
            } catch (e) {
                showNotification('Error al actualizar intervalo', 'error');
            }
        }

        // Modal de detalles
        async function openDetailsModal(jobId) {
            const modal = document.getElementById('details-modal');
            modal.classList.remove('hidden');
            modal.classList.add('flex');

            // Mostrar loading
            document.getElementById('details-content').innerHTML = '<p class="text-gray-400">Cargando detalles...</p>';

            try {
                const res = await fetch(`/api/admin/jobs/${jobId}/details`);
                const data = await res.json();

                if (data.success) {
                    const job = data.job;

                    // Actualizar título
                    document.getElementById('details-title').textContent = job.name;
                    document.getElementById('details-subtitle').textContent = job.description;

                    // Status badge
                    const statusEl = document.getElementById('details-status');
                    if (job.paused) {
                        statusEl.textContent = 'Pausado';
                        statusEl.className = 'px-3 py-1 rounded-full text-sm font-medium bg-yellow-600/20 text-yellow-400';
                    } else {
                        statusEl.textContent = 'Activo';
                        statusEl.className = 'px-3 py-1 rounded-full text-sm font-medium bg-green-600/20 text-green-400';
                    }

                    // Source
                    document.getElementById('details-source').textContent = job.source || '';

                    // Info grid
                    const intervalMin = job.trigger.interval_minutes ? Math.round(job.trigger.interval_minutes) : '-';
                    document.getElementById('details-interval').textContent = intervalMin + ' minutos';
                    document.getElementById('details-next-run').textContent = formatDate(job.next_run);
                    document.getElementById('details-endpoint').textContent = job.endpoint || '-';
                    document.getElementById('details-sheet-var').textContent = job.sheet_var || '-';

                    // Details HTML
                    document.getElementById('details-content').innerHTML = job.details_html;

                    // Recent history
                    const historyEl = document.getElementById('details-history');
                    if (data.recent_history && data.recent_history.length > 0) {
                        const statusColors = {
                            'completed': 'bg-green-600/20 text-green-400',
                            'manual_run': 'bg-blue-600/20 text-blue-400',
                            'paused': 'bg-yellow-600/20 text-yellow-400',
                            'resumed': 'bg-green-600/20 text-green-400',
                            'interval_changed': 'bg-purple-600/20 text-purple-400',
                            'failed': 'bg-red-600/20 text-red-400',
                        };
                        const statusLabels = {
                            'completed': 'Completado',
                            'manual_run': 'Ejecutado',
                            'paused': 'Pausado',
                            'resumed': 'Reanudado',
                            'interval_changed': 'Intervalo cambiado',
                            'failed': 'Fallido',
                        };

                        historyEl.innerHTML = data.recent_history.map(entry => `
                            <div class="flex items-center justify-between text-sm py-1">
                                <span class="text-gray-400">${formatDate(entry.timestamp)}</span>
                                <span class="px-2 py-0.5 rounded text-xs ${statusColors[entry.status] || 'bg-gray-600 text-gray-300'}">
                                    ${statusLabels[entry.status] || entry.status}
                                </span>
                            </div>
                        `).join('');
                    } else {
                        historyEl.innerHTML = '<p class="text-gray-400 text-sm">Sin historial de ejecuciones</p>';
                    }
                }
            } catch (e) {
                console.error('Error loading job details:', e);
                document.getElementById('details-content').innerHTML = '<p class="text-red-400">Error cargando detalles</p>';
            }
        }

        function closeDetailsModal() {
            const modal = document.getElementById('details-modal');
            modal.classList.add('hidden');
            modal.classList.remove('flex');
        }

        // Notificaciones
        function showNotification(message, type) {
            const colors = {
                'success': 'bg-green-600',
                'error': 'bg-red-600',
                'info': 'bg-blue-600'
            };

            const notification = document.createElement('div');
            notification.className = `fixed bottom-4 right-4 ${colors[type]} px-6 py-3 rounded-lg shadow-lg z-50 animate-fade-in`;
            notification.textContent = message;
            document.body.appendChild(notification);

            setTimeout(() => {
                notification.remove();
            }, 3000);
        }

        // Refresh all
        function refreshAll() {
            loadStats();
            loadJobs();
            loadHistory();
        }

        // Auto refresh cada 30 segundos
        setInterval(refreshAll, 30000);

        // Cargar al inicio
        refreshAll();
    </script>
</body>
</html>'''


# ========== MAIN ==========

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG_MODE,
        log_level=settings.LOG_LEVEL.lower(),
    )
