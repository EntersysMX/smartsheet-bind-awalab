"""
sync_bind_catalogs.py - Sincroniza catálogos de Bind ERP a Smartsheet.
Crea hojas con datos reales y las mantiene actualizadas.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import smartsheet
from smartsheet.models import Cell, Row

from bind_client import BindClient
from config import settings

logger = logging.getLogger(__name__)
CDMX_TZ = ZoneInfo("America/Mexico_City")
WORKSPACE_ID = 75095659046788

# Días hacia atrás para filtrar registros con fecha (orders, quotes)
DAYS_LOOKBACK = 7  # Solo registros de la última semana

# Definición de catálogos a sincronizar
CATALOG_CONFIGS = {
    "warehouses": {
        "sheet_name": "Bind - Almacenes",
        "bind_method": "get_warehouses",
        "columns": [
            {"title": "ID", "type": "TEXT_NUMBER", "width": 300},
            {"title": "Nombre", "type": "TEXT_NUMBER", "width": 150},
            {"title": "LocationID", "type": "TEXT_NUMBER", "width": 300},
            {"title": "Disponible Otras Ubicaciones", "type": "CHECKBOX", "width": 100},
            {"title": "Última Actualización", "type": "TEXT_NUMBER", "width": 150},
        ],
        "field_mapping": {
            "ID": "ID",
            "Nombre": "Name",
            "LocationID": "LocationID",
            "Disponible Otras Ubicaciones": "AvailableInOtherLoc",
        },
        "primary_key": "ID",
    },
    "clients": {
        "sheet_name": "Bind - Clientes",
        "bind_method": "get_clients",
        "columns": [
            {"title": "ID", "type": "TEXT_NUMBER", "width": 300},
            {"title": "Número", "type": "TEXT_NUMBER", "width": 80},
            {"title": "Nombre Comercial", "type": "TEXT_NUMBER", "width": 200},
            {"title": "Razón Social", "type": "TEXT_NUMBER", "width": 250},
            {"title": "RFC", "type": "TEXT_NUMBER", "width": 130},
            {"title": "Email", "type": "TEXT_NUMBER", "width": 200},
            {"title": "Teléfono", "type": "TEXT_NUMBER", "width": 120},
            {"title": "Régimen Fiscal", "type": "TEXT_NUMBER", "width": 100},
            {"title": "Última Actualización", "type": "TEXT_NUMBER", "width": 150},
        ],
        "field_mapping": {
            "ID": "ID",
            "Número": "Number",
            "Nombre Comercial": "ClientName",
            "Razón Social": "LegalName",
            "RFC": "RFC",
            "Email": "Email",
            "Teléfono": "Phone",
            "Régimen Fiscal": "RegimenFiscal",
        },
        "primary_key": "ID",
    },
    "products": {
        "sheet_name": "Bind - Productos",
        "bind_method": "get_products",
        "max_records": 5000,  # Limitar para evitar problemas de memoria
        "columns": [
            {"title": "ID", "type": "TEXT_NUMBER", "width": 300},
            {"title": "Código", "type": "TEXT_NUMBER", "width": 150},
            {"title": "Nombre", "type": "TEXT_NUMBER", "width": 300},
            {"title": "SKU", "type": "TEXT_NUMBER", "width": 150},
            {"title": "Costo", "type": "TEXT_NUMBER", "width": 100},
            {"title": "Inventario Actual", "type": "TEXT_NUMBER", "width": 100},
            {"title": "Unidad", "type": "TEXT_NUMBER", "width": 80},
            {"title": "Moneda", "type": "TEXT_NUMBER", "width": 60},
            {"title": "Tipo", "type": "TEXT_NUMBER", "width": 150},
            {"title": "Última Actualización", "type": "TEXT_NUMBER", "width": 150},
        ],
        "field_mapping": {
            "ID": "ID",
            "Código": "Code",
            "Nombre": "Title",
            "SKU": "SKU",
            "Costo": "Cost",
            "Inventario Actual": "CurrentInventory",
            "Unidad": "Unit",
            "Moneda": "CurrencyCode",
            "Tipo": "TypeText",
        },
        "primary_key": "ID",
    },
    "providers": {
        "sheet_name": "Bind - Proveedores",
        "bind_method": "get_providers",
        "max_records": 3000,
        "columns": [
            {"title": "ID", "type": "TEXT_NUMBER", "width": 300},
            {"title": "Número", "type": "TEXT_NUMBER", "width": 80},
            {"title": "Nombre", "type": "TEXT_NUMBER", "width": 200},
            {"title": "Razón Social", "type": "TEXT_NUMBER", "width": 250},
            {"title": "RFC", "type": "TEXT_NUMBER", "width": 130},
            {"title": "Email", "type": "TEXT_NUMBER", "width": 200},
            {"title": "Teléfono", "type": "TEXT_NUMBER", "width": 120},
            {"title": "Ciudad", "type": "TEXT_NUMBER", "width": 120},
            {"title": "Última Actualización", "type": "TEXT_NUMBER", "width": 150},
        ],
        "field_mapping": {
            "ID": "ID",
            "Número": "Number",
            "Nombre": "ProviderName",
            "Razón Social": "LegalName",
            "RFC": "RFC",
            "Email": "Email",
            "Teléfono": "Phone",
            "Ciudad": "City",
        },
        "primary_key": "ID",
    },
    "users": {
        "sheet_name": "Bind - Usuarios",
        "bind_method": "get_users",
        "columns": [
            {"title": "ID", "type": "TEXT_NUMBER", "width": 300},
            {"title": "Nombre Completo", "type": "TEXT_NUMBER", "width": 200},
            {"title": "Puesto", "type": "TEXT_NUMBER", "width": 150},
            {"title": "Email", "type": "TEXT_NUMBER", "width": 200},
            {"title": "Usuario", "type": "TEXT_NUMBER", "width": 150},
            {"title": "Última Actualización", "type": "TEXT_NUMBER", "width": 150},
        ],
        "field_mapping": {
            "ID": "ID",
            "Nombre Completo": "FullName",
            "Puesto": "JobPosition",
            "Email": "Email",
            "Usuario": "UserName",
        },
        "primary_key": "ID",
    },
    "currencies": {
        "sheet_name": "Bind - Monedas",
        "bind_method": "get_currencies",
        "columns": [
            {"title": "ID", "type": "TEXT_NUMBER", "width": 300},
            {"title": "Nombre", "type": "TEXT_NUMBER", "width": 200},
            {"title": "Código", "type": "TEXT_NUMBER", "width": 80},
            {"title": "Tipo de Cambio", "type": "TEXT_NUMBER", "width": 120},
            {"title": "Última Actualización", "type": "TEXT_NUMBER", "width": 150},
        ],
        "field_mapping": {
            "ID": "ID",
            "Nombre": "Name",
            "Código": "Code",
            "Tipo de Cambio": "ExchangeRate",
        },
        "primary_key": "ID",
    },
    "pricelists": {
        "sheet_name": "Bind - Listas de Precios",
        "bind_method": "get_price_lists",
        "columns": [
            {"title": "ID", "type": "TEXT_NUMBER", "width": 300},
            {"title": "Nombre", "type": "TEXT_NUMBER", "width": 300},
            {"title": "Última Actualización", "type": "TEXT_NUMBER", "width": 150},
        ],
        "field_mapping": {
            "ID": "ID",
            "Nombre": "Name",
        },
        "primary_key": "ID",
    },
    "bankaccounts": {
        "sheet_name": "Bind - Cuentas Bancarias",
        "bind_method": "get_bank_accounts",
        "columns": [
            {"title": "ID", "type": "TEXT_NUMBER", "width": 300},
            {"title": "Nombre", "type": "TEXT_NUMBER", "width": 200},
            {"title": "Tipo", "type": "TEXT_NUMBER", "width": 100},
            {"title": "Banco", "type": "TEXT_NUMBER", "width": 150},
            {"title": "Saldo", "type": "TEXT_NUMBER", "width": 150},
            {"title": "Moneda", "type": "TEXT_NUMBER", "width": 60},
            {"title": "Última Actualización", "type": "TEXT_NUMBER", "width": 150},
        ],
        "field_mapping": {
            "ID": "ID",
            "Nombre": "Name",
            "Tipo": "TypeText",
            "Banco": "BankName",
            "Saldo": "Balance",
            "Moneda": "CurrencyCode",
        },
        "primary_key": "ID",
    },
    "banks": {
        "sheet_name": "Bind - Bancos",
        "bind_method": "get_banks",
        "columns": [
            {"title": "ID", "type": "TEXT_NUMBER", "width": 300},
            {"title": "Nombre", "type": "TEXT_NUMBER", "width": 300},
            {"title": "Última Actualización", "type": "TEXT_NUMBER", "width": 150},
        ],
        "field_mapping": {
            "ID": "ID",
            "Nombre": "Name",
        },
        "primary_key": "ID",
    },
    "locations": {
        "sheet_name": "Bind - Ubicaciones",
        "bind_method": "get_locations",
        "columns": [
            {"title": "ID", "type": "TEXT_NUMBER", "width": 300},
            {"title": "Nombre", "type": "TEXT_NUMBER", "width": 150},
            {"title": "Calle", "type": "TEXT_NUMBER", "width": 200},
            {"title": "Número Ext", "type": "TEXT_NUMBER", "width": 80},
            {"title": "Colonia", "type": "TEXT_NUMBER", "width": 150},
            {"title": "Ciudad", "type": "TEXT_NUMBER", "width": 150},
            {"title": "Estado", "type": "TEXT_NUMBER", "width": 100},
            {"title": "CP", "type": "TEXT_NUMBER", "width": 80},
            {"title": "Última Actualización", "type": "TEXT_NUMBER", "width": 150},
        ],
        "field_mapping": {
            "ID": "ID",
            "Nombre": "Name",
            "Calle": "Street",
            "Número Ext": "ExtNumber",
            "Colonia": "Colonia",
            "Ciudad": "City",
            "Estado": "State",
            "CP": "ZipCode",
        },
        "primary_key": "ID",
    },
    "orders": {
        "sheet_name": "Bind - Pedidos",
        "bind_method": "get_orders",
        "max_records": 2000,
        "filter_by_date": True,  # Filtrar por fecha para obtener solo recientes
        "date_field": "OrderDate",  # Campo de fecha en Bind
        "columns": [
            {"title": "ID", "type": "TEXT_NUMBER", "width": 300},
            {"title": "Número", "type": "TEXT_NUMBER", "width": 100},
            {"title": "Serie", "type": "TEXT_NUMBER", "width": 100},
            {"title": "Fecha", "type": "TEXT_NUMBER", "width": 150},
            {"title": "Cliente", "type": "TEXT_NUMBER", "width": 200},
            {"title": "RFC", "type": "TEXT_NUMBER", "width": 130},
            {"title": "Orden Compra", "type": "TEXT_NUMBER", "width": 150},
            {"title": "Total", "type": "TEXT_NUMBER", "width": 120},
            {"title": "Moneda", "type": "TEXT_NUMBER", "width": 80},
            {"title": "Estado", "type": "TEXT_NUMBER", "width": 100},
            {"title": "Vendedor", "type": "TEXT_NUMBER", "width": 150},
            {"title": "Última Actualización", "type": "TEXT_NUMBER", "width": 150},
        ],
        "field_mapping": {
            "ID": "ID",
            "Número": "Number",
            "Serie": "Serie",
            "Fecha": "OrderDate",
            "Cliente": "ClientName",
            "RFC": "RFC",
            "Orden Compra": "PurchaseOrder",
            "Total": "Total",
            "Moneda": "CurrencyName",
            "Estado": "Status",
            "Vendedor": "EmployeeName",
        },
        "primary_key": "ID",
    },
    "quotes": {
        "sheet_name": "Bind - Cotizaciones",
        "bind_method": "get_quotes",
        "max_records": 2000,
        "filter_by_date": True,  # Filtrar por fecha para obtener solo recientes
        "date_field": "CreationDate",  # Campo de fecha en Bind
        "columns": [
            {"title": "ID", "type": "TEXT_NUMBER", "width": 300},
            {"title": "Número", "type": "TEXT_NUMBER", "width": 100},
            {"title": "Fecha", "type": "TEXT_NUMBER", "width": 150},
            {"title": "Cliente", "type": "TEXT_NUMBER", "width": 200},
            {"title": "Ubicación", "type": "TEXT_NUMBER", "width": 150},
            {"title": "Total", "type": "TEXT_NUMBER", "width": 120},
            {"title": "Moneda", "type": "TEXT_NUMBER", "width": 100},
            {"title": "Estado", "type": "TEXT_NUMBER", "width": 100},
            {"title": "Comentarios", "type": "TEXT_NUMBER", "width": 200},
            {"title": "Última Actualización", "type": "TEXT_NUMBER", "width": 150},
        ],
        "field_mapping": {
            "ID": "ID",
            "Número": "Number",
            "Fecha": "CreationDate",
            "Cliente": "ClientName",
            "Ubicación": "Locations",
            "Total": "Total",
            "Moneda": "Currency",
            "Estado": "StatusText",
            "Comentarios": "Comments",
        },
        "primary_key": "ID",
    },
}


class BindCatalogSync:
    """Clase para sincronizar catálogos de Bind a Smartsheet."""

    def __init__(self):
        self.bind_client = BindClient()
        self.ss_client = smartsheet.Smartsheet(settings.SMARTSHEET_ACCESS_TOKEN)
        self.ss_client.errors_as_exceptions(True)
        self._sheet_cache = {}  # {catalog_name: sheet_id}

    def _get_or_create_sheet(self, catalog_name: str, config: dict) -> int:
        """Obtiene o crea la hoja para un catálogo."""
        # Buscar en cache
        if catalog_name in self._sheet_cache:
            return self._sheet_cache[catalog_name]

        # Buscar en workspace
        try:
            ws = self.ss_client.Workspaces.get_workspace(WORKSPACE_ID)
            for sheet in ws.sheets:
                if sheet.name == config["sheet_name"]:
                    self._sheet_cache[catalog_name] = sheet.id
                    return sheet.id
        except Exception as e:
            logger.warning(f"Error buscando workspace: {e}")

        # Crear la hoja
        columns = []
        for i, col in enumerate(config["columns"]):
            col_spec = {
                "title": col["title"],
                "type": col["type"],
                "width": col.get("width", 150),
            }
            if i == 0:
                col_spec["primary"] = True
            columns.append(col_spec)

        sheet_spec = {"name": config["sheet_name"], "columns": columns}

        try:
            response = self.ss_client.Workspaces.create_sheet_in_workspace(
                WORKSPACE_ID, sheet_spec
            )
            sheet_id = response.result.id
            self._sheet_cache[catalog_name] = sheet_id
            logger.info(f"Hoja creada: {config['sheet_name']} (ID: {sheet_id})")
            return sheet_id
        except Exception as e:
            logger.error(f"Error creando hoja {config['sheet_name']}: {e}")
            raise

    def _get_column_map(self, sheet_id: int) -> dict:
        """Obtiene mapeo de nombre de columna a ID."""
        sheet = self.ss_client.Sheets.get_sheet(sheet_id, page_size=1)
        return {col.title: col.id for col in sheet.columns}

    def _get_existing_rows(self, sheet_id: int, primary_key_col: str) -> dict:
        """Obtiene las filas existentes indexadas por primary key."""
        sheet = self.ss_client.Sheets.get_sheet(sheet_id)
        col_map = {col.id: col.title for col in sheet.columns}
        pk_col_id = None
        for col in sheet.columns:
            if col.title == primary_key_col:
                pk_col_id = col.id
                break

        existing = {}
        for row in sheet.rows:
            pk_value = None
            for cell in row.cells:
                if cell.column_id == pk_col_id:
                    pk_value = cell.value
                    break
            if pk_value:
                existing[pk_value] = row.id

        return existing

    def _fetch_bind_data(self, catalog_name: str, config: dict, use_date_filter: bool = True) -> list:
        """Obtiene datos desde Bind ERP.

        Args:
            catalog_name: Nombre del catálogo
            config: Configuración del catálogo
            use_date_filter: Si True y el catálogo lo soporta, filtra por fecha.
                           Si False, obtiene todos los registros (carga inicial).
        """
        method_name = config["bind_method"]
        max_records = config.get("max_records")

        # Calcular filtro de fecha si aplica y está habilitado
        date_filter = None
        if use_date_filter and config.get("filter_by_date") and config.get("date_field"):
            since_date = datetime.now(CDMX_TZ) - timedelta(days=DAYS_LOOKBACK)
            date_field = config["date_field"]
            date_str = since_date.strftime("%Y-%m-%dT%H:%M:%S")
            date_filter = f"{date_field} gt DateTime'{date_str}'"
            logger.info(f"  Filtrando por {date_field} > {since_date.strftime('%Y-%m-%d')} (últimos {DAYS_LOOKBACK} días)")
        elif config.get("filter_by_date"):
            logger.info(f"  Carga inicial: obteniendo TODOS los registros (sin filtro de fecha)")

        # Construir params con filtro si existe
        params = {}
        if date_filter:
            params["$filter"] = date_filter

        # Mapeo de métodos a endpoints
        endpoint_map = {
            "get_warehouses": "/Warehouses",
            "get_clients": "/Clients",
            "get_products": "/Products",
            "get_providers": "/Providers",
            "get_users": "/Users",
            "get_currencies": "/Currencies",
            "get_price_lists": "/PriceLists",
            "get_bank_accounts": "/BankAccounts",
            "get_banks": "/Banks",
            "get_locations": "/Locations",
            "get_orders": "/Orders",
            "get_quotes": "/Quotes",
        }

        if method_name in endpoint_map:
            endpoint = endpoint_map[method_name]
            return self.bind_client._paginated_get(
                endpoint,
                params=params if params else None,
                max_records=max_records
            )
        else:
            logger.error(f"Método no encontrado: {method_name}")
            return []

    def sync_catalog(self, catalog_name: str, force_full_load: bool = False) -> dict:
        """Sincroniza un catálogo específico.

        Args:
            catalog_name: Nombre del catálogo a sincronizar
            force_full_load: Si True, obtiene todos los registros sin filtro de fecha
        """
        if catalog_name not in CATALOG_CONFIGS:
            return {"success": False, "error": f"Catálogo desconocido: {catalog_name}"}

        config = CATALOG_CONFIGS[catalog_name]
        logger.info(f"Iniciando sincronización de {catalog_name}...")

        try:
            # Obtener o crear hoja
            sheet_id = self._get_or_create_sheet(catalog_name, config)
            col_map = self._get_column_map(sheet_id)

            # Obtener filas existentes
            existing_rows = self._get_existing_rows(sheet_id, config["primary_key"])
            existing_count = len(existing_rows)

            # Determinar si usar filtro de fecha:
            # - Si force_full_load=True, NO usar filtro (carga completa)
            # - Si la hoja está vacía o tiene pocos registros (<10), NO usar filtro (carga inicial)
            # - Si la hoja tiene datos, usar filtro (sincronización incremental)
            use_date_filter = not force_full_load and existing_count >= 10

            if existing_count < 10:
                logger.info(f"  Hoja con {existing_count} registros - ejecutando CARGA INICIAL COMPLETA")
            elif force_full_load:
                logger.info(f"  Forzando carga completa (force_full_load=True)")
            else:
                logger.info(f"  Hoja con {existing_count} registros - sincronización INCREMENTAL")

            # Obtener datos de Bind
            bind_data = self._fetch_bind_data(catalog_name, config, use_date_filter=use_date_filter)
            logger.info(f"  Registros obtenidos de Bind: {len(bind_data)}")

            # Preparar timestamp
            timestamp = datetime.now(CDMX_TZ).strftime("%Y-%m-%d %H:%M")

            # Preparar filas para insertar/actualizar
            rows_to_add = []
            rows_to_update = []

            for record in bind_data:
                pk_value = str(record.get(config["field_mapping"][config["primary_key"]], ""))
                if not pk_value:
                    continue

                # Construir celdas
                cells = []
                for col_title, bind_field in config["field_mapping"].items():
                    if col_title in col_map:
                        value = record.get(bind_field)
                        if value is None:
                            value = ""
                        elif isinstance(value, bool):
                            value = value
                        elif isinstance(value, (int, float)):
                            value = value
                        else:
                            value = str(value)[:4000]  # Limite de Smartsheet
                        cells.append({"column_id": col_map[col_title], "value": value})

                # Agregar timestamp
                if "Última Actualización" in col_map:
                    cells.append({"column_id": col_map["Última Actualización"], "value": timestamp})

                if pk_value in existing_rows:
                    # Actualizar fila existente
                    row = Row()
                    row.id = existing_rows[pk_value]
                    row.cells = [Cell(c) for c in cells]
                    rows_to_update.append(row)
                else:
                    # Nueva fila
                    row = Row()
                    row.to_bottom = True
                    row.cells = [Cell(c) for c in cells]
                    rows_to_add.append(row)

            # Ejecutar operaciones en lotes
            added = 0
            updated = 0

            if rows_to_add:
                for i in range(0, len(rows_to_add), 100):
                    batch = rows_to_add[i : i + 100]
                    self.ss_client.Sheets.add_rows(sheet_id, batch)
                    added += len(batch)

            if rows_to_update:
                for i in range(0, len(rows_to_update), 100):
                    batch = rows_to_update[i : i + 100]
                    self.ss_client.Sheets.update_rows(sheet_id, batch)
                    updated += len(batch)

            sync_mode = "initial" if existing_count < 10 or force_full_load else "incremental"
            logger.info(f"  Sincronización completada: {added} nuevos, {updated} actualizados (modo: {sync_mode})")

            return {
                "success": True,
                "catalog": catalog_name,
                "sheet_id": sheet_id,
                "sync_mode": sync_mode,
                "existing_records": existing_count,
                "total_records": len(bind_data),
                "inserted": added,
                "updated": updated,
                "timestamp": timestamp,
            }

        except Exception as e:
            logger.error(f"Error sincronizando {catalog_name}: {e}")
            return {"success": False, "catalog": catalog_name, "error": str(e)}

    def sync_all_catalogs(self) -> dict:
        """Sincroniza todos los catálogos."""
        results = {}
        for catalog_name in CATALOG_CONFIGS:
            results[catalog_name] = self.sync_catalog(catalog_name)
        return results


def sync_bind_catalog(catalog_name: str, force_full_load: bool = False) -> dict:
    """Función pública para sincronizar un catálogo.

    Args:
        catalog_name: Nombre del catálogo a sincronizar
        force_full_load: Si True, obtiene todos los registros ignorando el filtro de fecha

    Comportamiento:
        - Si la hoja tiene <10 registros: CARGA INICIAL (todos los datos)
        - Si la hoja tiene >=10 registros: INCREMENTAL (solo últimos 7 días con UPSERT)
        - Si force_full_load=True: CARGA COMPLETA (todos los datos, ignorando registros existentes)
    """
    syncer = BindCatalogSync()
    return syncer.sync_catalog(catalog_name, force_full_load=force_full_load)


def sync_all_bind_catalogs() -> dict:
    """Función pública para sincronizar todos los catálogos."""
    syncer = BindCatalogSync()
    return syncer.sync_all_catalogs()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Sincronizando todos los catálogos...")
    results = sync_all_bind_catalogs()
    for name, result in results.items():
        if result.get("success"):
            print(f"  {name}: OK ({result.get('total_records', 0)} registros)")
        else:
            print(f"  {name}: ERROR - {result.get('error')}")
