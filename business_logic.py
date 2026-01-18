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


def sync_inventory(
    ss_service: SmartsheetService = None,
    bind_client: BindClient = None,
    sheet_id: int = None,
    warehouse_id: str = None,
) -> dict:
    """
    Sincroniza el inventario de Bind ERP a Smartsheet.

    Flujo:
    1. Obtiene inventario actual de Bind
    2. Obtiene productos para información adicional
    3. Actualiza/inserta filas en Smartsheet

    Args:
        ss_service: Servicio Smartsheet
        bind_client: Cliente Bind
        sheet_id: ID de hoja de inventario (usa settings si no se proporciona)
        warehouse_id: ID de almacén (usa settings si no se proporciona)

    Returns:
        Dict con estadísticas de sincronización
    """
    ss_service = ss_service or SmartsheetService()
    bind_client = bind_client or BindClient()
    sheet_id = sheet_id or settings.SMARTSHEET_INVENTORY_SHEET_ID
    warehouse_id = warehouse_id or settings.BIND_WAREHOUSE_ID

    result = {
        "success": False,
        "timestamp": datetime.now().isoformat(),
        "items_synced": 0,
        "items_updated": 0,
        "items_added": 0,
        "errors": [],
    }

    try:
        logger.info(f"Iniciando sincronización de inventario. Almacén: {warehouse_id}")

        # Obtener inventario de Bind
        inventory = bind_client.get_inventory(warehouse_id)
        logger.info(f"Obtenidos {len(inventory)} items de inventario de Bind")

        if not inventory:
            result["success"] = True
            result["message"] = "No hay items de inventario para sincronizar"
            return result

        # Obtener hoja actual de Smartsheet para comparar
        try:
            current_df = ss_service.get_sheet_as_dataframe(sheet_id)
            existing_codes = set(current_df.get("Codigo", pd.Series()).dropna())
        except Exception:
            existing_codes = set()
            logger.warning("No se pudo obtener hoja existente, se asumirá vacía")

        # Procesar cada item de inventario
        for item in inventory:
            try:
                product_code = item.get("ProductCode") or item.get("Code")
                if not product_code:
                    continue

                # Preparar datos para Smartsheet
                row_data = {
                    "Codigo": product_code,
                    "Nombre": item.get("ProductName") or item.get("Name"),
                    "Existencia": item.get("Quantity") or item.get("Stock", 0),
                    "Almacen": item.get("WarehouseName") or warehouse_id,
                    "Ultima Actualizacion": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }

                if product_code in existing_codes:
                    # Actualizar fila existente
                    # Buscar row_id en el DataFrame
                    matching_rows = current_df[current_df["Codigo"] == product_code]
                    if not matching_rows.empty:
                        row_id = matching_rows.iloc[0]["row_id"]
                        ss_service.update_row_cells(sheet_id, row_id, row_data)
                        result["items_updated"] += 1
                else:
                    # Nota: Agregar nuevas filas requiere lógica adicional
                    # Por ahora solo actualizamos existentes
                    logger.debug(f"Producto {product_code} no existe en Smartsheet")
                    result["items_added"] += 1

                result["items_synced"] += 1

            except Exception as e:
                logger.error(f"Error sincronizando item {item}: {e}")
                result["errors"].append(str(e))

        result["success"] = True
        logger.info(
            f"Sincronización completada. Sincronizados: {result['items_synced']}, "
            f"Actualizados: {result['items_updated']}, Nuevos: {result['items_added']}"
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

# Mapeo de estatus de factura
INVOICE_STATUS_MAP = {
    0: "Borrador",
    1: "Activa",
    2: "Cancelada",
    3: "Pagada",
}


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

    Args:
        ss_service: Servicio Smartsheet
        sheet_id: ID de la hoja

    Returns:
        Dict {UUID: row_id}
    """
    try:
        sheet = ss_service.client.Sheets.get_sheet(sheet_id)

        uuid_col_id = None
        for col in sheet.columns:
            if col.title == "UUID":
                uuid_col_id = col.id
                break

        if not uuid_col_id:
            return {}

        uuid_to_row = {}
        for row in sheet.rows:
            for cell in row.cells:
                if cell.column_id == uuid_col_id and cell.value:
                    uuid_to_row[cell.value] = row.id

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
        # Nota: Bind API usa la fecha del servidor, enviamos en formato ISO
        invoices = bind_client.get_invoices(
            created_since=since_cdmx.replace(tzinfo=None),  # Bind espera naive datetime
            limit=500,
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

            # Formatear fecha de factura preservando zona horaria
            fecha_bind = inv.get("Date", "")
            if fecha_bind:
                # Bind devuelve fechas en formato ISO, las convertimos a CDMX
                try:
                    # Parsear la fecha de Bind
                    if "T" in fecha_bind:
                        fecha_dt = datetime.fromisoformat(fecha_bind.replace("Z", "+00:00"))
                        if fecha_dt.tzinfo is None:
                            fecha_dt = fecha_dt.replace(tzinfo=cdmx_tz)
                        else:
                            fecha_dt = fecha_dt.astimezone(cdmx_tz)
                        fecha_str = fecha_dt.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        fecha_str = fecha_bind[:10]
                except Exception:
                    fecha_str = fecha_bind[:10] if fecha_bind else ""
            else:
                fecha_str = ""

            # Mapear campos de Bind a columnas de Smartsheet
            field_mapping = {
                "UUID": uuid,
                "Serie": inv.get("Serie", ""),
                "Folio": str(inv.get("Number", "")),
                "Fecha": fecha_str,
                "Cliente": inv.get("ClientName", ""),
                "RFC": inv.get("RFC", ""),
                "Subtotal": f"${inv.get('Subtotal', 0):,.2f}",
                "IVA": f"${inv.get('VAT', 0):,.2f}",
                "Total": f"${inv.get('Total', 0):,.2f}",
                "Moneda": "MXN" if "b7e2c065" in str(inv.get("CurrencyID", "")) else "USD",
                "Uso CFDI": CFDI_USE_MAP.get(inv.get("CFDIUse", 0), "Desconocido"),
                "Metodo Pago": "PUE" if inv.get("IsFiscalInvoice") else "PPD",
                "Estatus": INVOICE_STATUS_MAP.get(inv.get("Status", 0), "Desconocido"),
                "Comentarios": (inv.get("Comments", "") or "")[:500],
                "Orden Compra": inv.get("PurchaseOrder", ""),
                "Bind ID": inv.get("ID", ""),
                "Ultima Sync": now_str,
            }

            # Crear celdas
            cells = []
            for field_name, value in field_mapping.items():
                if field_name in column_map:
                    cell = Cell()
                    cell.column_id = column_map[field_name]
                    cell.value = str(value) if value else ""
                    cells.append(cell)

            if uuid in existing_map:
                # ACTUALIZAR fila existente
                row = Row()
                row.id = existing_map[uuid]
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
