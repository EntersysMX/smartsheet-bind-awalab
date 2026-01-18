"""
sync_invoices_from_bind.py - Sincroniza facturas de Bind ERP a Smartsheet.
Flujo: Bind -> Smartsheet (Pull)
"""

import requests
import smartsheet
from smartsheet.models import Row, Cell
from datetime import datetime
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuracion
BIND_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1bmlxdWVfbmFtZSI6Im1lam9yYSBhd2FsYWJ8NDM5NjUiLCJJbnRlcm5hbElEIjoiMWE4MzQ1N2MtYzQ5My00OTUyLTkyMmEtMzcwOTIwMzVkMTJkIiwibmJmIjoxNzQ3MDYzODg4LCJleHAiOjE3Nzg1OTk4ODgsImlhdCI6MTc0NzA2Mzg4OCwiaXNzIjoiTWlubnRfU29sdXRpb25zX1NBX0RFX0NWIiwiYXVkIjoiQmluZF9FUlBfQVBJX1VzZXJzIn0.-Tn0_a-pXX3nYw5kXJ_Su6HGS2z9ibEBgm7_eLjQJM0"
BIND_API_URL = "https://api.bind.com.mx/api"
SMARTSHEET_TOKEN = "rVcpRyiLctXXwjnmh09dEpPiZfzrodlTUdBWd"
SHEET_ID = 4956740131966852

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

# Mapeo de estatus
STATUS_MAP = {
    0: "Borrador",
    1: "Activa",
    2: "Cancelada",
    3: "Pagada",
}


def get_bind_invoices(limit: int = 100, skip: int = 0, since: Optional[datetime] = None) -> list:
    """Obtiene facturas de Bind ERP."""
    headers = {
        "Authorization": f"Bearer {BIND_API_KEY}",
        "Content-Type": "application/json",
    }

    params = {
        "$top": limit,
        "$skip": skip,
        "$orderby": "Date desc",
    }

    if since:
        date_str = since.strftime("%Y-%m-%dT%H:%M:%S")
        params["$filter"] = f"Date gt DateTime'{date_str}'"

    response = requests.get(
        f"{BIND_API_URL}/Invoices",
        headers=headers,
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    return data.get("value", [])


def get_all_bind_invoices(max_records: int = 1000) -> list:
    """Obtiene todas las facturas con paginacion."""
    all_invoices = []
    skip = 0
    page_size = 100

    while len(all_invoices) < max_records:
        invoices = get_bind_invoices(limit=page_size, skip=skip)
        if not invoices:
            break
        all_invoices.extend(invoices)
        skip += page_size
        logger.info(f"Obtenidas {len(all_invoices)} facturas...")

    return all_invoices[:max_records]


def get_existing_uuids(client: smartsheet.Smartsheet, sheet_id: int) -> set:
    """Obtiene los UUIDs ya existentes en Smartsheet."""
    sheet = client.Sheets.get_sheet(sheet_id)

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


def sync_invoices_to_smartsheet(invoices: list, client: smartsheet.Smartsheet, sheet_id: int) -> dict:
    """Sincroniza facturas a Smartsheet."""

    # Obtener estructura de la hoja
    sheet = client.Sheets.get_sheet(sheet_id)
    column_map = {col.title: col.id for col in sheet.columns}

    # Obtener UUIDs existentes
    existing_uuids = get_existing_uuids(client, sheet_id)
    logger.info(f"UUIDs existentes en Smartsheet: {len(existing_uuids)}")

    # Filtrar facturas nuevas
    new_invoices = [inv for inv in invoices if inv.get("UUID") not in existing_uuids]
    logger.info(f"Facturas nuevas a sincronizar: {len(new_invoices)}")

    if not new_invoices:
        return {"added": 0, "skipped": len(invoices)}

    # Crear filas para Smartsheet
    rows_to_add = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for inv in new_invoices:
        row = Row()
        row.to_top = True  # Nuevas arriba
        row.cells = []

        # Mapear campos de Bind a columnas de Smartsheet
        field_mapping = {
            "UUID": inv.get("UUID", ""),
            "Serie": inv.get("Serie", ""),
            "Folio": str(inv.get("Number", "")),
            "Fecha": inv.get("Date", "")[:10] if inv.get("Date") else "",
            "Cliente": inv.get("ClientName", ""),
            "RFC": inv.get("RFC", ""),
            "Subtotal": f"${inv.get('Subtotal', 0):,.2f}",
            "IVA": f"${inv.get('VAT', 0):,.2f}",
            "Total": f"${inv.get('Total', 0):,.2f}",
            "Moneda": "MXN" if "b7e2c065" in str(inv.get("CurrencyID", "")) else "USD",
            "Uso CFDI": CFDI_USE_MAP.get(inv.get("CFDIUse", 0), "Desconocido"),
            "Metodo Pago": "PUE" if inv.get("IsFiscalInvoice") else "PPD",
            "Estatus": STATUS_MAP.get(inv.get("Status", 0), "Desconocido"),
            "Comentarios": (inv.get("Comments", "") or "")[:500],
            "Orden Compra": inv.get("PurchaseOrder", ""),
            "Bind ID": inv.get("ID", ""),
            "Ultima Sync": now,
        }

        for field_name, value in field_mapping.items():
            if field_name in column_map:
                cell = Cell()
                cell.column_id = column_map[field_name]
                cell.value = str(value) if value else ""
                row.cells.append(cell)

        rows_to_add.append(row)

    # Agregar filas en lotes de 100
    added = 0
    batch_size = 100

    for i in range(0, len(rows_to_add), batch_size):
        batch = rows_to_add[i:i + batch_size]
        try:
            result = client.Sheets.add_rows(sheet_id, batch)
            added += len(result.result)
            logger.info(f"Agregadas {added} filas...")
        except Exception as e:
            logger.error(f"Error agregando filas: {e}")

    return {
        "added": added,
        "skipped": len(invoices) - len(new_invoices),
        "total_in_bind": len(invoices),
    }


def main():
    """Funcion principal de sincronizacion."""
    logger.info("=== SINCRONIZACION BIND -> SMARTSHEET ===")
    logger.info(f"Fecha: {datetime.now()}")

    # Inicializar cliente Smartsheet
    client = smartsheet.Smartsheet(SMARTSHEET_TOKEN)
    client.errors_as_exceptions(True)

    # Obtener facturas de Bind
    logger.info("Obteniendo facturas de Bind ERP...")
    invoices = get_all_bind_invoices(max_records=500)
    logger.info(f"Total facturas en Bind: {len(invoices)}")

    # Sincronizar a Smartsheet
    logger.info("Sincronizando a Smartsheet...")
    result = sync_invoices_to_smartsheet(invoices, client, SHEET_ID)

    logger.info("=== RESULTADO ===")
    logger.info(f"Facturas agregadas: {result['added']}")
    logger.info(f"Facturas ya existentes (omitidas): {result['skipped']}")
    logger.info(f"URL: https://app.smartsheet.com/sheets/{SHEET_ID}")

    return result


if __name__ == "__main__":
    main()
