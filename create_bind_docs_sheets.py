"""
Script para crear hojas de documentación de Bind ERP en Smartsheet.
"""

import smartsheet
from config import settings

WORKSPACE_ID = 75095659046788

WEB_SERVICES = {
    "Warehouses": {
        "name": "API Bind - Warehouses (Almacenes)",
        "endpoint": "/Warehouses",
        "methods": ["GET"],
        "description": "Obtiene la lista de almacenes configurados en Bind ERP",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único del almacén"},
            {"name": "Name", "type": "String", "description": "Nombre del almacén"},
            {"name": "LocationID", "type": "UUID", "description": "ID de la ubicación/sucursal"},
            {"name": "AvailableInOtherLoc", "type": "Boolean", "description": "Disponible en otras ubicaciones"},
        ],
        "filters": [],
    },
    "Clients": {
        "name": "API Bind - Clients (Clientes)",
        "endpoint": "/Clients",
        "methods": ["GET", "POST", "PUT"],
        "description": "Gestiona el catálogo de clientes",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único del cliente"},
            {"name": "Number", "type": "Integer", "description": "Número de cliente interno"},
            {"name": "ClientName", "type": "String", "description": "Nombre comercial"},
            {"name": "LegalName", "type": "String", "description": "Razón social"},
            {"name": "RFC", "type": "String", "description": "RFC del cliente"},
            {"name": "Email", "type": "String", "description": "Correo electrónico"},
            {"name": "Phone", "type": "String", "description": "Teléfono"},
            {"name": "RegimenFiscal", "type": "String", "description": "Código de régimen fiscal SAT"},
        ],
        "filters": ["RFC eq 'RFC_CLIENTE'", "ModificationDate gt DateTime'FECHA'"],
    },
    "Products": {
        "name": "API Bind - Products (Productos)",
        "endpoint": "/Products",
        "methods": ["GET", "POST", "PUT"],
        "description": "Gestiona el catálogo de productos con inventario actual",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único"},
            {"name": "Code", "type": "String", "description": "Código del producto"},
            {"name": "Title", "type": "String", "description": "Nombre del producto"},
            {"name": "Description", "type": "String", "description": "Descripción detallada"},
            {"name": "Cost", "type": "Decimal", "description": "Costo del producto"},
            {"name": "SKU", "type": "String", "description": "SKU del producto"},
            {"name": "CurrentInventory", "type": "Decimal", "description": "Inventario actual"},
            {"name": "Unit", "type": "String", "description": "Unidad de medida"},
            {"name": "CurrencyCode", "type": "String", "description": "Código de moneda (MXN, USD)"},
        ],
        "filters": ["Code eq 'CODIGO'", "ModificationDate gt DateTime'FECHA'"],
    },
    "Invoices": {
        "name": "API Bind - Invoices (Facturas)",
        "endpoint": "/Invoices",
        "methods": ["GET", "POST"],
        "description": "Gestiona facturas (CFDI) emitidas",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único de Bind"},
            {"name": "Serie", "type": "String", "description": "Serie de la factura"},
            {"name": "Number", "type": "Integer", "description": "Folio de la factura"},
            {"name": "UUID", "type": "UUID", "description": "UUID del CFDI (SAT)"},
            {"name": "Date", "type": "DateTime", "description": "Fecha de emisión"},
            {"name": "ClientName", "type": "String", "description": "Nombre del cliente"},
            {"name": "RFC", "type": "String", "description": "RFC del cliente"},
            {"name": "Subtotal", "type": "Decimal", "description": "Subtotal sin IVA"},
            {"name": "VAT", "type": "Decimal", "description": "Monto de IVA"},
            {"name": "Total", "type": "Decimal", "description": "Total de la factura"},
            {"name": "Status", "type": "Integer", "description": "0=Vigente, 1=Pagada, 2=Cancelada"},
            {"name": "PurchaseOrder", "type": "String", "description": "Orden de compra"},
        ],
        "filters": ["Date gt DateTime'FECHA'", "RFC eq 'RFC'"],
    },
    "Orders": {
        "name": "API Bind - Orders (Pedidos)",
        "endpoint": "/Orders",
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "description": "Gestiona pedidos de venta",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único"},
            {"name": "Number", "type": "Integer", "description": "Número de pedido"},
            {"name": "ClientName", "type": "String", "description": "Nombre del cliente"},
            {"name": "OrderDate", "type": "DateTime", "description": "Fecha del pedido"},
            {"name": "PurchaseOrder", "type": "String", "description": "Orden de compra"},
            {"name": "Status", "type": "Integer", "description": "0=Activo, 1=Parcial, 2=Completo"},
            {"name": "Total", "type": "Decimal", "description": "Total del pedido"},
        ],
        "filters": ["OrderDate gt DateTime'FECHA'"],
    },
    "Quotes": {
        "name": "API Bind - Quotes (Cotizaciones)",
        "endpoint": "/Quotes",
        "methods": ["GET", "POST", "PUT"],
        "description": "Gestiona cotizaciones emitidas a clientes",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único"},
            {"name": "Number", "type": "String", "description": "Número de cotización"},
            {"name": "ClientName", "type": "String", "description": "Nombre del cliente"},
            {"name": "CreationDate", "type": "DateTime", "description": "Fecha de creación"},
            {"name": "Total", "type": "Decimal", "description": "Total"},
            {"name": "Status", "type": "Integer", "description": "0=Activa, 1=Aceptada, 2=Rechazada"},
        ],
        "filters": ["CreationDate gt DateTime'FECHA'"],
    },
    "Providers": {
        "name": "API Bind - Providers (Proveedores)",
        "endpoint": "/Providers",
        "methods": ["GET", "POST", "PUT"],
        "description": "Gestiona el catálogo de proveedores",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único"},
            {"name": "Number", "type": "Integer", "description": "Número de proveedor"},
            {"name": "ProviderName", "type": "String", "description": "Nombre comercial"},
            {"name": "LegalName", "type": "String", "description": "Razón social"},
            {"name": "RFC", "type": "String", "description": "RFC del proveedor"},
        ],
        "filters": ["RFC eq 'RFC'"],
    },
    "Users": {
        "name": "API Bind - Users (Usuarios)",
        "endpoint": "/Users",
        "methods": ["GET"],
        "description": "Obtiene los usuarios del sistema Bind ERP",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único"},
            {"name": "FullName", "type": "String", "description": "Nombre completo"},
            {"name": "Email", "type": "String", "description": "Correo electrónico"},
            {"name": "UserName", "type": "String", "description": "Nombre de usuario"},
        ],
        "filters": [],
    },
    "Currencies": {
        "name": "API Bind - Currencies (Monedas)",
        "endpoint": "/Currencies",
        "methods": ["GET"],
        "description": "Obtiene las monedas con tipo de cambio actual",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único"},
            {"name": "Name", "type": "String", "description": "Nombre de la moneda"},
            {"name": "Code", "type": "String", "description": "Código ISO (MXN, USD)"},
            {"name": "ExchangeRate", "type": "Decimal", "description": "Tipo de cambio"},
        ],
        "filters": [],
    },
    "PriceLists": {
        "name": "API Bind - PriceLists (Listas de Precios)",
        "endpoint": "/PriceLists",
        "methods": ["GET"],
        "description": "Obtiene las listas de precios configuradas",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único"},
            {"name": "Name", "type": "String", "description": "Nombre de la lista"},
        ],
        "filters": [],
    },
    "BankAccounts": {
        "name": "API Bind - BankAccounts (Cuentas Bancarias)",
        "endpoint": "/BankAccounts",
        "methods": ["GET"],
        "description": "Obtiene las cuentas bancarias de la empresa",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único"},
            {"name": "Name", "type": "String", "description": "Nombre de la cuenta"},
            {"name": "Balance", "type": "Decimal", "description": "Saldo actual"},
            {"name": "TypeText", "type": "String", "description": "Crédito o Débito"},
            {"name": "CurrencyCode", "type": "String", "description": "Código de moneda"},
        ],
        "filters": [],
    },
    "Banks": {
        "name": "API Bind - Banks (Bancos)",
        "endpoint": "/Banks",
        "methods": ["GET"],
        "description": "Catálogo de instituciones bancarias",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único"},
            {"name": "Name", "type": "String", "description": "Nombre del banco"},
        ],
        "filters": [],
    },
    "Locations": {
        "name": "API Bind - Locations (Ubicaciones)",
        "endpoint": "/Locations",
        "methods": ["GET"],
        "description": "Sucursales/ubicaciones de la empresa",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único"},
            {"name": "Name", "type": "String", "description": "Nombre"},
            {"name": "Street", "type": "String", "description": "Calle"},
            {"name": "City", "type": "String", "description": "Ciudad"},
            {"name": "State", "type": "String", "description": "Estado"},
            {"name": "ZipCode", "type": "String", "description": "Código postal"},
        ],
        "filters": [],
    },
    "Categories": {
        "name": "API Bind - Categories (Categorías)",
        "endpoint": "/Categories",
        "methods": ["GET"],
        "description": "Árbol de categorías de productos (3 niveles)",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único"},
            {"name": "Name", "type": "String", "description": "Nombre de la categoría"},
            {"name": "SubCategories", "type": "Array", "description": "Subcategorías"},
        ],
        "filters": [],
    },
    "Accounts": {
        "name": "API Bind - Accounts (Cuentas Contables)",
        "endpoint": "/Accounts",
        "methods": ["GET"],
        "description": "Catálogo de cuentas contables",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único"},
            {"name": "Number", "type": "String", "description": "Número de cuenta"},
            {"name": "Description", "type": "String", "description": "Descripción"},
            {"name": "GLGroup", "type": "String", "description": "Grupo mayor"},
        ],
        "filters": [],
    },
    "AccountingJournals": {
        "name": "API Bind - AccountingJournals (Pólizas)",
        "endpoint": "/AccountingJournals",
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "description": "Gestiona las pólizas contables",
        "fields": [
            {"name": "ID", "type": "UUID", "description": "Identificador único"},
            {"name": "Number", "type": "Integer", "description": "Número de póliza"},
            {"name": "Type", "type": "String", "description": "Tipo de póliza"},
            {"name": "ApplicationDate", "type": "DateTime", "description": "Fecha de aplicación"},
            {"name": "Items", "type": "Array", "description": "Movimientos"},
        ],
        "filters": ["ApplicationDate gt DateTime'FECHA'"],
    },
}

WEBHOOKS = [
    {"id": "Add_Activity", "name": "Agregar Actividad", "description": "Se dispara cuando se crea una actividad"},
    {"id": "Add_Client", "name": "Agregar Cliente", "description": "Se dispara cuando se crea un cliente nuevo"},
    {"id": "Add_Comment", "name": "Agregar Comentario", "description": "Se dispara cuando se genera un comentario"},
    {"id": "Add_Invoice", "name": "Agregar Factura", "description": "Se dispara cuando se crea una factura"},
    {"id": "Add_Order", "name": "Agregar Pedido", "description": "Se dispara cuando se genera un pedido"},
    {"id": "Add_Product", "name": "Agregar Producto", "description": "Se dispara cuando se crea un producto"},
    {"id": "Add_Prospect", "name": "Agregar Prospecto", "description": "Se dispara cuando se agrega un prospecto"},
    {"id": "Add_Quote", "name": "Agregar Cotización", "description": "Se dispara cuando se crea una cotización"},
    {"id": "Delete_Activity", "name": "Eliminar Actividad", "description": "Se dispara cuando se elimina una actividad"},
    {"id": "Delete_Comment", "name": "Eliminar Comentario", "description": "Se dispara cuando se elimina un comentario"},
    {"id": "Delete_Order", "name": "Eliminar Pedido", "description": "Se dispara cuando se elimina un pedido"},
    {"id": "Delete_Product", "name": "Eliminar Producto", "description": "Se dispara cuando se elimina un producto"},
    {"id": "Update_Activity", "name": "Actualizar Actividad", "description": "Se dispara cuando se actualiza una actividad"},
    {"id": "Update_Inventory", "name": "Actualizar Inventario", "description": "Se dispara cuando cambia el inventario"},
    {"id": "Update_Product", "name": "Actualizar Producto", "description": "Se dispara cuando se modifica un producto"},
]


def create_service_sheet(client, workspace_id, service_key, service_data):
    columns = [
        {"title": "Campo", "type": "TEXT_NUMBER", "primary": True, "width": 200},
        {"title": "Tipo", "type": "TEXT_NUMBER", "width": 100},
        {"title": "Descripción", "type": "TEXT_NUMBER", "width": 400},
    ]
    sheet_spec = {"name": service_data["name"], "columns": columns}
    response = client.Workspaces.create_sheet_in_workspace(workspace_id, sheet_spec)
    sheet_id = response.result.id
    cols = {c.title: c.id for c in response.result.columns}
    print(f"  Creada: {service_data['name']}")

    rows = []
    # Info del endpoint
    r = smartsheet.models.Row()
    r.to_bottom = True
    r.cells = [
        {"column_id": cols["Campo"], "value": f"ENDPOINT: {service_data['endpoint']}"},
        {"column_id": cols["Tipo"], "value": ", ".join(service_data['methods'])},
        {"column_id": cols["Descripción"], "value": service_data['description']},
    ]
    rows.append(r)

    if service_data['filters']:
        r = smartsheet.models.Row()
        r.to_bottom = True
        r.cells = [
            {"column_id": cols["Campo"], "value": "FILTROS ODATA"},
            {"column_id": cols["Tipo"], "value": "$filter"},
            {"column_id": cols["Descripción"], "value": " | ".join(service_data['filters'])},
        ]
        rows.append(r)

    r = smartsheet.models.Row()
    r.to_bottom = True
    r.cells = [{"column_id": cols["Campo"], "value": "--- CAMPOS ---"}]
    rows.append(r)

    for field in service_data['fields']:
        r = smartsheet.models.Row()
        r.to_bottom = True
        r.cells = [
            {"column_id": cols["Campo"], "value": field['name']},
            {"column_id": cols["Tipo"], "value": field['type']},
            {"column_id": cols["Descripción"], "value": field['description']},
        ]
        rows.append(r)

    client.Sheets.add_rows(sheet_id, rows)
    return sheet_id


def create_webhooks_sheet(client, workspace_id):
    columns = [
        {"title": "Event ID", "type": "TEXT_NUMBER", "primary": True, "width": 180},
        {"title": "Nombre", "type": "TEXT_NUMBER", "width": 200},
        {"title": "Descripción", "type": "TEXT_NUMBER", "width": 400},
    ]
    sheet_spec = {"name": "API Bind - WebHooks (Eventos)", "columns": columns}
    response = client.Workspaces.create_sheet_in_workspace(workspace_id, sheet_spec)
    sheet_id = response.result.id
    cols = {c.title: c.id for c in response.result.columns}
    print(f"  Creada: API Bind - WebHooks")

    rows = []
    # Info de endpoints
    r = smartsheet.models.Row()
    r.to_bottom = True
    r.cells = [
        {"column_id": cols["Event ID"], "value": "ENDPOINTS"},
        {"column_id": cols["Descripción"], "value": "GET /WebHooks | GET /WebHookSubscriptions | POST /WebHookSubscriptions"},
    ]
    rows.append(r)

    r = smartsheet.models.Row()
    r.to_bottom = True
    r.cells = [
        {"column_id": cols["Event ID"], "value": "CÓMO SUSCRIBIRSE"},
        {"column_id": cols["Descripción"], "value": "POST /WebHookSubscriptions con {EventID, TargetURL}. Bind enviará POST a tu URL."},
    ]
    rows.append(r)

    r = smartsheet.models.Row()
    r.to_bottom = True
    r.cells = [{"column_id": cols["Event ID"], "value": "--- EVENTOS ---"}]
    rows.append(r)

    for wh in WEBHOOKS:
        r = smartsheet.models.Row()
        r.to_bottom = True
        r.cells = [
            {"column_id": cols["Event ID"], "value": wh['id']},
            {"column_id": cols["Nombre"], "value": wh['name']},
            {"column_id": cols["Descripción"], "value": wh['description']},
        ]
        rows.append(r)

    client.Sheets.add_rows(sheet_id, rows)
    return sheet_id


def main():
    print("Creando hojas de documentación Bind ERP...")
    client = smartsheet.Smartsheet(settings.SMARTSHEET_ACCESS_TOKEN)
    client.errors_as_exceptions(True)

    for service_key, service_data in WEB_SERVICES.items():
        try:
            create_service_sheet(client, WORKSPACE_ID, service_key, service_data)
        except Exception as e:
            print(f"  ERROR {service_data['name']}: {e}")

    try:
        create_webhooks_sheet(client, WORKSPACE_ID)
    except Exception as e:
        print(f"  ERROR WebHooks: {e}")

    print("Proceso completado.")


if __name__ == "__main__":
    main()
