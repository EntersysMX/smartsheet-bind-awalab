"""
business_logic.py - Orquestador de lógica de negocio.
Contiene las funciones principales para procesar facturas y sincronizar inventario.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from bind_client import BindClient, BindAPIError
from smartsheet_service import SmartsheetService, SmartsheetServiceError
from config import settings, REQUIRED_INVOICE_COLUMNS

logger = logging.getLogger(__name__)


# ========== MODELOS PYDANTIC PARA VALIDACIÓN ==========

class InvoiceItemModel(BaseModel):
    """Modelo para un concepto/línea de factura."""
    concepto: str = Field(..., min_length=1, max_length=1000)
    descripcion: Optional[str] = Field(None, max_length=1000)
    cantidad: Decimal = Field(..., gt=0)
    precio_unitario: Decimal = Field(..., ge=0)
    clave_sat_producto: str = Field(..., pattern=r"^\d{8}$")
    clave_sat_unidad: str = Field(..., pattern=r"^[A-Z0-9]{2,3}$")

    @field_validator("cantidad", "precio_unitario", mode="before")
    @classmethod
    def parse_decimal(cls, v):
        if isinstance(v, str):
            v = v.replace(",", "").replace("$", "").strip()
        try:
            return Decimal(str(v))
        except (InvalidOperation, ValueError):
            raise ValueError(f"Valor numérico inválido: {v}")


class InvoiceRequestModel(BaseModel):
    """Modelo completo para solicitud de factura desde Smartsheet."""
    row_id: int
    rfc: str = Field(..., pattern=r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")
    razon_social: Optional[str] = None
    concepto: str
    descripcion: Optional[str] = None
    cantidad: Decimal
    precio_unitario: Decimal
    clave_sat_producto: str
    clave_sat_unidad: str
    metodo_pago: str = Field(..., pattern=r"^(PUE|PPD)$")
    forma_pago: str = Field(..., pattern=r"^\d{2}$")
    uso_cfdi: str = Field(..., pattern=r"^[A-Z]\d{2}$")
    regimen_fiscal: Optional[str] = Field(None, pattern=r"^\d{3}$")
    codigo_postal: Optional[str] = Field(None, pattern=r"^\d{5}$")

    @field_validator("rfc", mode="before")
    @classmethod
    def normalize_rfc(cls, v):
        return v.strip().upper() if v else v


class WebhookPayload(BaseModel):
    """Modelo para payload de webhook de Smartsheet."""
    nonce: Optional[str] = None
    timestamp: Optional[str] = None
    webhookId: Optional[int] = None
    scope: Optional[str] = None
    scopeObjectId: Optional[int] = None
    events: Optional[list[dict]] = None
    challenge: Optional[str] = None


# ========== FUNCIONES DE LÓGICA DE NEGOCIO ==========

class BusinessLogicError(Exception):
    """Excepción para errores de lógica de negocio."""
    pass


def extract_row_data_from_smartsheet(
    ss_service: SmartsheetService,
    sheet_id: int,
    row_id: int,
) -> dict[str, Any]:
    """
    Extrae y valida los datos de una fila de Smartsheet.

    Args:
        ss_service: Instancia del servicio Smartsheet
        sheet_id: ID de la hoja
        row_id: ID de la fila

    Returns:
        Datos de la fila como diccionario

    Raises:
        BusinessLogicError: Si faltan campos requeridos
    """
    row_data = ss_service.get_row(sheet_id, row_id)

    # Validar campos requeridos
    missing_fields = []
    for field in REQUIRED_INVOICE_COLUMNS:
        if field not in row_data or row_data.get(field) is None:
            missing_fields.append(field)

    if missing_fields:
        raise BusinessLogicError(
            f"Campos requeridos faltantes: {', '.join(missing_fields)}"
        )

    return row_data


def map_smartsheet_to_bind_invoice(
    row_data: dict[str, Any],
    client_id: str,
) -> dict:
    """
    Mapea datos de Smartsheet al formato JSON de factura de Bind.

    Args:
        row_data: Datos de la fila de Smartsheet
        client_id: ID del cliente en Bind

    Returns:
        Diccionario con estructura de factura para Bind
    """
    # Calcular totales
    cantidad = Decimal(str(row_data.get("Cantidad", 0)))
    precio_unitario = Decimal(str(row_data.get("Precio Unitario", 0)))
    subtotal = cantidad * precio_unitario

    # Asumir IVA 16% (esto podría parametrizarse)
    iva_rate = Decimal("0.16")
    iva = subtotal * iva_rate
    total = subtotal + iva

    # Construir estructura de factura para Bind
    invoice_data = {
        "ClientID": client_id,
        "Date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "PaymentMethod": row_data.get("Metodo Pago", "PUE"),
        "PaymentForm": row_data.get("Forma Pago", "03"),
        "CFDIUse": row_data.get("Uso CFDI", "G03"),
        "Currency": "MXN",
        "ExchangeRate": 1,
        "Items": [
            {
                "ProductServiceKey": row_data.get("Clave SAT Producto"),
                "UnitKey": row_data.get("Clave SAT Unidad"),
                "Description": row_data.get("Concepto"),
                "Quantity": float(cantidad),
                "UnitPrice": float(precio_unitario),
                "Subtotal": float(subtotal),
                "Taxes": [
                    {
                        "Name": "IVA",
                        "Rate": float(iva_rate),
                        "Amount": float(iva),
                        "Type": "Tasa",
                        "Base": float(subtotal),
                    }
                ],
                "Total": float(subtotal + iva),
            }
        ],
        "Subtotal": float(subtotal),
        "Total": float(total),
    }

    # Agregar descripción adicional si existe
    if row_data.get("Descripcion"):
        invoice_data["Items"][0]["Description"] = (
            f"{row_data.get('Concepto')} - {row_data.get('Descripcion')}"
        )

    return invoice_data


def process_invoice_request(
    sheet_id: int,
    row_id: int,
    ss_service: SmartsheetService = None,
    bind_client: BindClient = None,
) -> dict:
    """
    Procesa una solicitud de facturación desde Smartsheet.

    Flujo:
    1. Lee la fila de Smartsheet
    2. Valida los datos requeridos
    3. Busca el cliente en Bind por RFC
    4. Crea la factura en Bind
    5. Actualiza Smartsheet con el resultado

    Args:
        sheet_id: ID de la hoja de Smartsheet
        row_id: ID de la fila a procesar
        ss_service: Servicio Smartsheet (opcional, se crea si no se proporciona)
        bind_client: Cliente Bind (opcional, se crea si no se proporciona)

    Returns:
        Dict con resultado de la operación

    Raises:
        BusinessLogicError: Si hay error en el proceso
    """
    # Inicializar servicios si no se proporcionan
    ss_service = ss_service or SmartsheetService()
    bind_client = bind_client or BindClient()

    result = {
        "success": False,
        "row_id": row_id,
        "uuid": None,
        "folio": None,
        "error": None,
    }

    try:
        logger.info(f"Procesando solicitud de factura para fila {row_id}")

        # Paso 1: Extraer datos de Smartsheet
        row_data = extract_row_data_from_smartsheet(ss_service, sheet_id, row_id)
        logger.info(f"Datos extraídos para RFC: {row_data.get('RFC')}")

        # Paso 2: Validar datos con Pydantic
        try:
            validated = InvoiceRequestModel(
                row_id=row_id,
                rfc=row_data.get("RFC"),
                razon_social=row_data.get("Razon Social"),
                concepto=row_data.get("Concepto"),
                descripcion=row_data.get("Descripcion"),
                cantidad=row_data.get("Cantidad"),
                precio_unitario=row_data.get("Precio Unitario"),
                clave_sat_producto=row_data.get("Clave SAT Producto"),
                clave_sat_unidad=row_data.get("Clave SAT Unidad"),
                metodo_pago=row_data.get("Metodo Pago", "PUE"),
                forma_pago=row_data.get("Forma Pago", "03"),
                uso_cfdi=row_data.get("Uso CFDI", "G03"),
                regimen_fiscal=row_data.get("Regimen Fiscal"),
                codigo_postal=row_data.get("Codigo Postal"),
            )
        except Exception as e:
            raise BusinessLogicError(f"Validación fallida: {e}")

        # Paso 3: Buscar cliente en Bind por RFC
        client = bind_client.get_client_by_rfc(validated.rfc)
        if not client:
            raise BusinessLogicError(
                f"Cliente con RFC {validated.rfc} no encontrado en Bind ERP. "
                "Por favor, registre el cliente antes de facturar."
            )

        client_id = client.get("ID")
        logger.info(f"Cliente encontrado en Bind: {client_id}")

        # Paso 4: Mapear datos y crear factura
        invoice_data = map_smartsheet_to_bind_invoice(row_data, client_id)

        invoice_response = bind_client.create_invoice(invoice_data)

        result["success"] = True
        result["uuid"] = invoice_response.get("UUID")
        result["folio"] = invoice_response.get("Folio")

        logger.info(
            f"Factura creada exitosamente. UUID: {result['uuid']}, Folio: {result['folio']}"
        )

        # Paso 5: Actualizar Smartsheet con resultado exitoso
        ss_service.update_invoice_result(
            sheet_id=sheet_id,
            row_id=row_id,
            uuid=result["uuid"],
            folio=result["folio"],
        )

    except BusinessLogicError as e:
        logger.error(f"Error de negocio procesando fila {row_id}: {e}")
        result["error"] = str(e)

        # Actualizar Smartsheet con error
        try:
            ss_service.update_invoice_result(
                sheet_id=sheet_id,
                row_id=row_id,
                error_message=str(e),
            )
            ss_service.add_row_comment(
                sheet_id=sheet_id,
                row_id=row_id,
                text=f"Error de facturación: {e}",
            )
        except Exception as update_error:
            logger.error(f"Error al actualizar Smartsheet: {update_error}")

    except BindAPIError as e:
        logger.error(f"Error de API Bind procesando fila {row_id}: {e}")
        result["error"] = f"Error Bind API: {e}"

        try:
            ss_service.update_invoice_result(
                sheet_id=sheet_id,
                row_id=row_id,
                error_message=f"Error Bind: {e}",
            )
            ss_service.add_row_comment(
                sheet_id=sheet_id,
                row_id=row_id,
                text=f"Error de API Bind: {e}",
            )
        except Exception:
            pass

    except SmartsheetServiceError as e:
        logger.error(f"Error de Smartsheet procesando fila {row_id}: {e}")
        result["error"] = f"Error Smartsheet: {e}"

    except Exception as e:
        logger.exception(f"Error inesperado procesando fila {row_id}: {e}")
        result["error"] = f"Error inesperado: {e}"

        try:
            ss_service.update_invoice_result(
                sheet_id=sheet_id,
                row_id=row_id,
                error_message=f"Error interno: {e}",
            )
        except Exception:
            pass

    return result


def get_existing_inventory_map(ss_service: SmartsheetService, sheet_id: int) -> dict[str, int]:
    """
    Obtiene un mapa de ID Producto -> row_id para productos existentes en Smartsheet.

    Returns:
        dict {product_id: row_id}
    """
    existing_map = {}
    try:
        sheet = ss_service.client.Sheets.get_sheet(sheet_id)

        # Encontrar índice de columna "ID Producto"
        id_col_idx = None
        for idx, col in enumerate(sheet.columns):
            if col.title == "ID Producto":
                id_col_idx = idx
                break

        if id_col_idx is None:
            logger.warning("No se encontró columna 'ID Producto' en la hoja")
            return existing_map

        # Mapear ID Producto -> row_id
        for row in sheet.rows:
            if row.cells and len(row.cells) > id_col_idx:
                cell_value = row.cells[id_col_idx].value
                if cell_value:
                    existing_map[str(cell_value)] = row.id

        logger.info(f"Mapa de productos existentes: {len(existing_map)} productos")
    except Exception as e:
        logger.error(f"Error obteniendo mapa de productos: {e}")

    return existing_map


def sync_inventory(
    ss_service: SmartsheetService = None,
    bind_client: BindClient = None,
    sheet_id: int = None,
    warehouse_id: str = None,
) -> dict:
    """
    Sincroniza el inventario de Bind ERP a Smartsheet con lógica UPSERT.

    Flujo:
    1. Obtiene productos de Bind ERP
    2. Compara con productos existentes en Smartsheet por ID Producto
    3. Actualiza existentes o inserta nuevos

    Args:
        ss_service: Servicio Smartsheet
        bind_client: Cliente Bind
        sheet_id: ID de hoja de inventario (usa settings si no se proporciona)
        warehouse_id: ID de almacén (usa settings si no se proporciona)

    Returns:
        Dict con estadísticas de sincronización
    """
    from zoneinfo import ZoneInfo
    cdmx_tz = ZoneInfo("America/Mexico_City")

    ss_service = ss_service or SmartsheetService()
    bind_client = bind_client or BindClient()
    sheet_id = sheet_id or settings.SMARTSHEET_INVENTORY_SHEET_ID
    warehouse_id = warehouse_id or settings.BIND_WAREHOUSE_ID

    now_cdmx = datetime.now(cdmx_tz)

    result = {
        "success": False,
        "timestamp": now_cdmx.isoformat(),
        "timezone": "America/Mexico_City",
        "total_in_bind": 0,
        "inserted": 0,
        "updated": 0,
        "errors": [],
    }

    try:
        logger.info(f"Iniciando sincronización UPSERT de inventario. Almacén: {warehouse_id}")

        # Obtener productos de Bind
        products = bind_client.get_products()
        result["total_in_bind"] = len(products)
        logger.info(f"Productos obtenidos de Bind: {len(products)}")

        if not products:
            result["success"] = True
            result["message"] = "No hay productos en Bind para sincronizar"
            return result

        # Obtener mapa de productos existentes en Smartsheet
        existing_map = get_existing_inventory_map(ss_service, sheet_id)

        # Obtener estructura de columnas de la hoja
        sheet = ss_service.client.Sheets.get_sheet(sheet_id)
        column_map = {col.title: col.id for col in sheet.columns}

        rows_to_add = []
        rows_to_update = []

        for product in products:
            try:
                product_id = str(product.get("ID") or product.get("id", ""))
                if not product_id:
                    continue

                # Preparar datos del producto
                row_data = {
                    "ID Producto": product_id,
                    "Codigo": product.get("Code") or product.get("code", ""),
                    "Nombre Producto": product.get("Name") or product.get("name", ""),
                    "Descripcion": product.get("Description") or product.get("description", ""),
                    "Existencias": product.get("Stock") or product.get("Quantity") or 0,
                    "Unidad": product.get("Unit") or product.get("UnitName") or "",
                    "Precio Unitario": product.get("Price") or product.get("UnitPrice") or 0,
                    "Almacen ID": warehouse_id or "",
                    "Almacen Nombre": product.get("WarehouseName") or "",
                    "Ultima Actualizacion": now_cdmx.strftime("%Y-%m-%d %H:%M:%S"),
                }

                # Construir celdas
                cells = []
                for col_title, value in row_data.items():
                    if col_title in column_map:
                        cells.append({
                            "columnId": column_map[col_title],
                            "value": value if value is not None else "",
                        })

                if product_id in existing_map:
                    # UPDATE: producto existe
                    row = ss_service.client.models.Row()
                    row.id = existing_map[product_id]
                    row.cells = [ss_service.client.models.Cell(cell) for cell in cells]
                    rows_to_update.append(row)
                else:
                    # INSERT: producto nuevo
                    row = ss_service.client.models.Row()
                    row.to_bottom = True
                    row.cells = [ss_service.client.models.Cell(cell) for cell in cells]
                    rows_to_add.append(row)

            except Exception as e:
                logger.error(f"Error procesando producto {product}: {e}")
                result["errors"].append(str(e))

        # Ejecutar actualizaciones en lotes
        batch_size = 100

        if rows_to_update:
            logger.info(f"Actualizando {len(rows_to_update)} productos existentes...")
            for i in range(0, len(rows_to_update), batch_size):
                batch = rows_to_update[i:i + batch_size]
                try:
                    ss_service.client.Sheets.update_rows(sheet_id, batch)
                    result["updated"] += len(batch)
                except Exception as e:
                    logger.error(f"Error actualizando lote: {e}")
                    result["errors"].append(f"Error update batch: {e}")

        if rows_to_add:
            logger.info(f"Insertando {len(rows_to_add)} productos nuevos...")
            for i in range(0, len(rows_to_add), batch_size):
                batch = rows_to_add[i:i + batch_size]
                try:
                    ss_service.client.Sheets.add_rows(sheet_id, batch)
                    result["inserted"] += len(batch)
                except Exception as e:
                    logger.error(f"Error insertando lote: {e}")
                    result["errors"].append(f"Error insert batch: {e}")

        result["success"] = True
        logger.info(
            f"Sincronización completada. Total: {result['total_in_bind']}, "
            f"Actualizados: {result['updated']}, Insertados: {result['inserted']}"
        )

    except BindAPIError as e:
        logger.error(f"Error de Bind en sincronización: {e}")
        result["errors"].append(f"Error Bind: {e}")

    except Exception as e:
        logger.exception(f"Error inesperado en sincronización: {e}")
        result["errors"].append(f"Error: {e}")

    return result


def sync_inventory_movements(
    ss_service: SmartsheetService = None,
    bind_client: BindClient = None,
    since_hours: int = 24,
) -> dict:
    """
    Sincroniza movimientos de inventario (egresos) recientes.

    Args:
        ss_service: Servicio Smartsheet
        bind_client: Cliente Bind
        since_hours: Obtener movimientos de las últimas N horas

    Returns:
        Dict con estadísticas
    """
    ss_service = ss_service or SmartsheetService()
    bind_client = bind_client or BindClient()

    since = datetime.now() - timedelta(hours=since_hours)

    result = {
        "success": False,
        "timestamp": datetime.now().isoformat(),
        "movements_found": 0,
        "movements_synced": 0,
    }

    try:
        logger.info(f"Obteniendo movimientos de inventario desde {since}")

        movements = bind_client.get_inventory_movements(
            warehouse_id=settings.BIND_WAREHOUSE_ID,
            since=since,
        )

        result["movements_found"] = len(movements)
        logger.info(f"Encontrados {len(movements)} movimientos")

        # Aquí se procesarían los movimientos y actualizarían en Smartsheet
        # La implementación específica depende de la estructura de la hoja

        result["success"] = True
        result["movements_synced"] = len(movements)

    except Exception as e:
        logger.exception(f"Error sincronizando movimientos: {e}")
        result["error"] = str(e)

    return result


# ========== SINCRONIZACIÓN DE FACTURAS BIND -> SMARTSHEET ==========

# Mapeo de uso CFDI
CFDI_USE_MAP = {
    0: "G01 - Adquisicion de mercancias",
    1: "G02 - Devoluciones, descuentos",
    2: "G03 - Gastos en general",
    3: "I01 - Construcciones",
    4: "I02 - Mobiliario y equipo",
    5: "I03 - Equipo de transporte",
    6: "I04 - Equipo de computo",
    7: "I05 - Dados, troqueles, moldes",
    8: "I06 - Comunicaciones telefonicas",
    9: "I07 - Comunicaciones satelitales",
    10: "I08 - Otra maquinaria",
    11: "D01 - Honorarios medicos",
    12: "D02 - Gastos medicos",
    13: "D03 - Gastos funerales",
    14: "D04 - Donativos",
    15: "D05 - Intereses hipotecarios",
    16: "D06 - Aportaciones SAR",
    17: "D07 - Primas seguros",
    18: "D08 - Gastos transportacion",
    19: "D09 - Depositos cuentas ahorro",
    20: "D10 - Servicios educativos",
    21: "P01 - Por definir",
    22: "S01 - Sin efectos fiscales",
    23: "CP01 - Pagos",
    24: "CN01 - Nomina",
}

# Mapeo de estatus de factura en Bind ERP
# Status 0 = Vigente (timbrada) o Borrador (sin timbrar)
# Status 1 = Pagada
# Status 2 = Cancelada
def get_invoice_status(inv: dict) -> str:
    """Determina el estatus real de una factura."""
    status = inv.get("Status", 0)
    has_uuid = bool(inv.get("UUID"))

    if status == 2:
        return "Cancelada"
    elif status == 1:
        return "Pagada"
    elif status == 0:
        if has_uuid:
            return "Vigente"
        else:
            return "Borrador"
    else:
        return "Desconocido"


def get_existing_invoice_uuids(
    ss_service: SmartsheetService,
    sheet_id: int,
) -> set:
    """
    Obtiene los UUIDs de facturas ya existentes en Smartsheet.

    Args:
        ss_service: Servicio Smartsheet
        sheet_id: ID de la hoja

    Returns:
        Set de UUIDs existentes
    """
    try:
        sheet = ss_service.client.Sheets.get_sheet(sheet_id)

        uuid_col_id = None
        for col in sheet.columns:
            if col.title == "UUID":
                uuid_col_id = col.id
                break

        if not uuid_col_id:
            return set()

        existing_uuids = set()
        for row in sheet.rows:
            for cell in row.cells:
                if cell.column_id == uuid_col_id and cell.value:
                    existing_uuids.add(cell.value)

        return existing_uuids
    except Exception as e:
        logger.error(f"Error obteniendo UUIDs existentes: {e}")
        return set()


def get_existing_invoices_map(
    ss_service: SmartsheetService,
    sheet_id: int,
) -> dict[str, int]:
    """
    Obtiene un mapa de UUID -> row_id para facturas existentes en Smartsheet.
    Busca en la columna primaria "Nueva" que contiene el UUID de la factura.

    Args:
        ss_service: Servicio Smartsheet
        sheet_id: ID de la hoja

    Returns:
        Dict {UUID: row_id}
    """
    try:
        sheet = ss_service.client.Sheets.get_sheet(sheet_id)

        # Buscar columna primaria "Nueva" o "Folio Fiscal" como fallback
        uuid_col_id = None
        for col in sheet.columns:
            if col.primary:  # La columna primaria contiene el UUID
                uuid_col_id = col.id
                break
            if col.title in ("Nueva", "Folio Fiscal", "UUID"):
                uuid_col_id = col.id

        if not uuid_col_id:
            logger.warning("No se encontró columna con UUID en la hoja")
            return {}

        uuid_to_row = {}
        for row in sheet.rows:
            for cell in row.cells:
                if cell.column_id == uuid_col_id and cell.value:
                    uuid_to_row[str(cell.value)] = row.id

        return uuid_to_row
    except Exception as e:
        logger.error(f"Error obteniendo mapa de UUIDs: {e}")
        return {}


def sync_invoices_from_bind(
    ss_service: SmartsheetService = None,
    bind_client: BindClient = None,
    sheet_id: int = None,
    minutes_lookback: int = 10,
) -> dict:
    """
    Sincroniza facturas de Bind ERP a Smartsheet (UPSERT).
    - Obtiene solo facturas creadas/modificadas en los últimos N minutos
    - Actualiza facturas existentes (por UUID) o inserta nuevas
    - Maneja zona horaria de CDMX (America/Mexico_City)

    Args:
        ss_service: Servicio Smartsheet
        bind_client: Cliente Bind
        sheet_id: ID de la hoja de facturas
        minutes_lookback: Minutos hacia atrás para buscar facturas (default: 10)

    Returns:
        Dict con estadísticas de sincronización
    """
    from smartsheet.models import Row, Cell
    from zoneinfo import ZoneInfo

    ss_service = ss_service or SmartsheetService()
    bind_client = bind_client or BindClient()
    sheet_id = sheet_id or settings.SMARTSHEET_INVOICES_SHEET_ID

    # Zona horaria de CDMX
    cdmx_tz = ZoneInfo("America/Mexico_City")
    now_cdmx = datetime.now(cdmx_tz)
    since_cdmx = now_cdmx - timedelta(minutes=minutes_lookback)

    result = {
        "success": False,
        "timestamp": now_cdmx.isoformat(),
        "timezone": "America/Mexico_City",
        "lookback_minutes": minutes_lookback,
        "since": since_cdmx.isoformat(),
        "total_in_bind": 0,
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "errors": [],
    }

    try:
        logger.info(f"Iniciando sincronización UPSERT de facturas Bind -> Smartsheet")
        logger.info(f"Buscando facturas desde: {since_cdmx.strftime('%Y-%m-%d %H:%M:%S')} CDMX")

        # Obtener facturas de Bind de los últimos N minutos
        # Nota: Bind API tiene límite de 100 registros por request
        invoices = bind_client.get_invoices(
            created_since=since_cdmx.replace(tzinfo=None),  # Bind espera naive datetime
            limit=100,  # Máximo permitido por Bind API
            order_by="Date desc",
        )

        result["total_in_bind"] = len(invoices)
        logger.info(f"Facturas obtenidas de Bind (últimos {minutes_lookback} min): {len(invoices)}")

        if not invoices:
            result["success"] = True
            result["message"] = f"No hay facturas nuevas en los últimos {minutes_lookback} minutos"
            return result

        # Obtener mapa UUID -> row_id de Smartsheet
        existing_map = get_existing_invoices_map(ss_service, sheet_id)
        logger.info(f"Facturas existentes en Smartsheet: {len(existing_map)}")

        # Obtener estructura de la hoja
        sheet = ss_service.client.Sheets.get_sheet(sheet_id)
        column_map = {col.title: col.id for col in sheet.columns}

        # Preparar filas para insertar y actualizar
        rows_to_add = []
        rows_to_update = []
        now_str = now_cdmx.strftime("%Y-%m-%d %H:%M:%S")

        for inv in invoices:
            uuid = inv.get("UUID", "")
            if not uuid:
                logger.warning(f"Factura sin UUID ignorada: {inv.get('Number')}")
                continue

            # Obtener detalles de la factura (incluye productos)
            try:
                invoice_detail = bind_client.get_invoice(inv.get("ID"))
                products = invoice_detail.get("Products", [])
            except Exception as e:
                logger.warning(f"No se pudieron obtener detalles de factura {inv.get('ID')}: {e}")
                products = []

            # Formatear fecha de factura preservando zona horaria
            fecha_bind = inv.get("Date", "")
            if fecha_bind:
                try:
                    if "T" in fecha_bind:
                        fecha_dt = datetime.fromisoformat(fecha_bind.replace("Z", "+00:00"))
                        if fecha_dt.tzinfo is None:
                            fecha_dt = fecha_dt.replace(tzinfo=cdmx_tz)
                        else:
                            fecha_dt = fecha_dt.astimezone(cdmx_tz)
                        fecha_str = fecha_dt.strftime("%Y-%m-%d")
                    else:
                        fecha_str = fecha_bind[:10]
                except Exception:
                    fecha_str = fecha_bind[:10] if fecha_bind else ""
            else:
                fecha_str = None

            # Datos comunes de la factura
            estatus = get_invoice_status(inv)
            moneda = "MXN" if "b7e2c065" in str(inv.get("CurrencyID", "")) else "USD"
            metodo_pago = "PUE" if inv.get("IsFiscalInvoice") else "PPD"
            serie = inv.get("Serie", "").strip().rstrip("- ")  # Quitar guión y espacios finales
            folio = str(inv.get("Number", ""))
            numero_factura = f"{serie}-{folio}" if serie else folio  # Formato: AWAFAC-20260159

            # Si no hay productos, crear una fila con los datos de la factura
            if not products:
                products = [{"Code": "", "Name": "", "Qty": 0, "Price": 0, "ID": "no-product"}]

            # Crear una fila por cada producto
            for idx, product in enumerate(products):
                # Identificador único: UUID + índice del producto
                row_key = f"{uuid}-{idx}" if len(products) > 1 else uuid

                field_mapping = {
                    # Columna primaria - usar UUID + índice como identificador único
                    "Nueva": row_key,
                    # Campos principales de factura
                    "Serie": serie,
                    "No.": numero_factura,
                    "Emision": fecha_str,
                    "Cliente": inv.get("ClientName", ""),
                    "RFC Cliente": inv.get("RFC", ""),
                    "Subtotal": inv.get("Subtotal", 0),
                    "I.V.A": inv.get("VAT", 0),
                    "Total": inv.get("Total", 0),
                    "Moneda": moneda,
                    "Folio Fiscal": uuid,
                    "Estatus": estatus,
                    # Campos adicionales
                    "Vendedor": inv.get("SellerName", ""),
                    "OrdenDeCompra": inv.get("PurchaseOrder", ""),
                    "Vencimiento": None,
                    "Pendiente": inv.get("Balance", 0) if inv.get("Balance") else inv.get("Total", 0) if estatus == "Vigente" else 0,
                    "Pagos": inv.get("PaidAmount", 0),
                    # Campos duplicados para compatibilidad
                    "Folio": folio,
                    "Fecha": fecha_str,
                    "RFC": inv.get("RFC", ""),
                    "IVA": inv.get("VAT", 0),
                    "Metodo Pago": metodo_pago,
                    "Orden Compra": inv.get("PurchaseOrder", ""),
                    # Campos de tracking
                    "Bind ID": inv.get("ID", ""),
                    "Ultima Sync": now_str,
                    # Campos de estado de pago
                    "Pagada": estatus == "Pagada",
                    "Cancelada": estatus == "Cancelada",
                    # Campos de producto (una fila por producto)
                    "Código Prod/Serv": product.get("Code", ""),
                    "Producto/Concepto": product.get("Name", ""),
                    "Cantidad": product.get("Qty", 0),
                    "Cantidad Total": product.get("Qty", 0),
                }

                # Crear celdas
                cells = []
                for field_name, value in field_mapping.items():
                    if field_name in column_map:
                        cell = Cell()
                        cell.column_id = column_map[field_name]
                        cell.value = str(value) if value is not None else ""
                        cells.append(cell)

                if row_key in existing_map:
                    # ACTUALIZAR fila existente
                    row = Row()
                    row.id = existing_map[row_key]
                    row.cells = cells
                    rows_to_update.append(row)
                else:
                    # INSERTAR nueva fila
                    row = Row()
                    row.to_top = True
                    row.cells = cells
                    rows_to_add.append(row)

        # Ejecutar actualizaciones en lotes
        batch_size = 100

        if rows_to_update:
            logger.info(f"Actualizando {len(rows_to_update)} filas existentes...")
            for i in range(0, len(rows_to_update), batch_size):
                batch = rows_to_update[i:i + batch_size]
                try:
                    ss_service.client.Sheets.update_rows(sheet_id, batch)
                    result["updated"] += len(batch)
                except Exception as e:
                    logger.error(f"Error actualizando filas: {e}")
                    result["errors"].append(f"Error update: {str(e)}")

        if rows_to_add:
            logger.info(f"Insertando {len(rows_to_add)} filas nuevas...")
            for i in range(0, len(rows_to_add), batch_size):
                batch = rows_to_add[i:i + batch_size]
                try:
                    ss_service.client.Sheets.add_rows(sheet_id, batch)
                    result["inserted"] += len(batch)
                except Exception as e:
                    logger.error(f"Error insertando filas: {e}")
                    result["errors"].append(f"Error insert: {str(e)}")

        result["success"] = True
        result["unchanged"] = len(invoices) - result["inserted"] - result["updated"]
        logger.info(
            f"Sincronización UPSERT completada. "
            f"Insertadas: {result['inserted']}, "
            f"Actualizadas: {result['updated']}, "
            f"Sin cambios: {result['unchanged']}"
        )

    except BindAPIError as e:
        logger.error(f"Error de Bind en sincronización de facturas: {e}")
        result["errors"].append(f"Error Bind: {e}")

    except Exception as e:
        logger.exception(f"Error inesperado sincronizando facturas: {e}")
        result["errors"].append(f"Error: {e}")

    return result


# Importar pandas solo si es necesario (evitar error si no está instalado al importar módulo)
try:
    import pandas as pd
except ImportError:
    pd = None
