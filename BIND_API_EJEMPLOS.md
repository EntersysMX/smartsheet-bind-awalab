# API de Bind ERP - Ejemplos Reales de Ejecucion

**Fecha de ejecucion:** 2026-01-20
**Empresa:** AWALab de Mexico
**Base URL:** `https://api.bind.com.mx/api`

---

## Resumen de Datos en Bind ERP

| Recurso | Total de Registros | Endpoint |
|---------|-------------------|----------|
| Almacenes | 6 | `/Warehouses` |
| Clientes | 800 | `/Clients` |
| Productos | 20,041 | `/Products` |
| Proveedores | 2,900+ | `/Providers` |
| Facturas | Variable | `/Invoices` |
| Pedidos | Variable | `/Orders` |
| Cotizaciones | Variable | `/Quotes` |
| Usuarios | 15+ | `/Users` |
| Monedas | 2 | `/Currencies` |
| Listas de Precios | 2 | `/PriceLists` |
| Cuentas Bancarias | 10+ | `/BankAccounts` |
| Bancos | 50+ | `/Banks` |
| Ubicaciones | 1 | `/Locations` |
| Categorias | 11 | `/Categories` |
| Cuentas Contables | 200+ | `/Accounts` |
| Polizas Contables | Variable | `/AccountingJournals` |
| WebHooks | 20+ eventos | `/WebHooks` |

## Endpoints Disponibles

### Endpoints Funcionales (Probados)
| Endpoint | Descripcion |
|----------|-------------|
| `GET /Warehouses` | Almacenes |
| `GET /Clients` | Clientes |
| `GET /Products` | Productos |
| `GET /Invoices` | Facturas |
| `GET /Orders` | Pedidos de venta |
| `GET /Quotes` | Cotizaciones |
| `GET /Providers` | Proveedores |
| `GET /Users` | Usuarios del sistema |
| `GET /UserProfile` | Perfil del usuario actual |
| `GET /Currencies` | Monedas |
| `GET /PriceLists` | Listas de precios |
| `GET /BankAccounts` | Cuentas bancarias |
| `GET /Banks` | Catalogo de bancos |
| `GET /Locations` | Ubicaciones/Sucursales |
| `GET /Categories` | Categorias de productos |
| `GET /Accounts` | Cuentas contables |
| `GET /AccountCategories` | Catalogo de cuentas SAT |
| `GET /AccountingJournals` | Polizas contables |
| `GET /WebHooks` | Eventos disponibles |
| `GET /WebHookSubscriptions` | Suscripciones activas |

### Endpoints No Disponibles (404)
| Endpoint | Nota |
|----------|------|
| `/Inventory` | Usar `/Products` con `CurrentInventory` |
| `/InventoryMovements` | No disponible |
| `/PaymentMethods` | No disponible |
| `/PaymentForms` | No disponible |
| `/CFDIUses` | No disponible |
| `/Taxes` | No disponible |
| `/Units` | No disponible |

---

## 1. Health Check

Verifica la conectividad con la API de Bind.

### Metodo del Cliente
```python
from bind_client import BindClient

client = BindClient()
result = client.health_check()
print(result)  # True
```

### Resultado Real
```
Conectado: True
```

---

## 2. Almacenes (Warehouses)

Obtiene la lista de almacenes configurados en Bind ERP.

### Endpoint
```
GET /Warehouses
```

### Metodo del Cliente
```python
warehouses = client.get_warehouses()
```

### Respuesta Real (6 almacenes)
```json
[
  {
    "ID": "eb3d48b5-d556-412b-8635-126798d89e81",
    "Name": "GDL",
    "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
    "AvailableInOtherLoc": true
  },
  {
    "ID": "e3a96c34-7aba-4886-9da6-2ac7901fee03",
    "Name": "GDL WH",
    "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
    "AvailableInOtherLoc": false
  },
  {
    "ID": "f1eeff32-69e4-4e02-b449-831edb38e0d9",
    "Name": "PPM",
    "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
    "AvailableInOtherLoc": true
  },
  {
    "ID": "8f1e24e6-548d-4531-9976-8d1d62e5a641",
    "Name": "Xico",
    "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
    "AvailableInOtherLoc": true
  },
  {
    "ID": "07059d9b-b0e1-47cc-b93c-c1048603f20a",
    "Name": "Matriz",
    "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
    "AvailableInOtherLoc": true
  },
  {
    "ID": "f76bf017-677d-4bcc-b08b-ca96104ab423",
    "Name": "MTY",
    "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
    "AvailableInOtherLoc": true
  }
]
```

### Campos del Almacen

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `ID` | UUID | Identificador unico del almacen |
| `Name` | String | Nombre del almacen |
| `LocationID` | UUID | ID de la ubicacion/sucursal |
| `AvailableInOtherLoc` | Boolean | Si esta disponible en otras ubicaciones |

---

## 3. Clientes (Clients)

Obtiene la lista de clientes registrados.

### Endpoint
```
GET /Clients
GET /Clients?$filter=RFC eq 'RFC_CLIENTE'
```

### Metodo del Cliente
```python
# Obtener todos los clientes
clients = client.get_clients()

# Buscar cliente por RFC
client_data = client.get_client_by_rfc("IGQ090730V23")
```

### Respuesta Real (muestra de 5 clientes)
```json
{
  "value": [
    {
      "ID": "c9f5a151-eb03-4629-b20b-001cc519bb25",
      "Number": 1656,
      "ClientName": "QUALITY",
      "LegalName": "INNO - QUALITY",
      "RFC": "IGQ090730V23",
      "Email": "m.olmedo@innofoods.mx",
      "Phone": "5556047481",
      "NextContactDate": null,
      "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
      "RegimenFiscal": "601"
    },
    {
      "ID": "2fca7d65-4814-4e80-a7c9-002a3f877579",
      "Number": 1242,
      "ClientName": "PTI",
      "LegalName": "PROMOTORA TECNICA INDUSTRIAL",
      "RFC": "PTI820402RJ6",
      "Email": "cesar.mendoza@ultraquimia.com",
      "Phone": null,
      "NextContactDate": null,
      "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
      "RegimenFiscal": "601"
    },
    {
      "ID": "b80b7047-2b31-42de-a7e2-00427bd8d0b8",
      "Number": 1417,
      "ClientName": "IDESA",
      "LegalName": "INDUSTRIAS DERIVADAS DEL ETILENO SA DE CV",
      "RFC": "IDE811214RH3",
      "Email": "",
      "Phone": null,
      "NextContactDate": null,
      "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
      "RegimenFiscal": "601"
    },
    {
      "ID": "8b42ef0d-8451-43cf-97b6-00731e1d2f8f",
      "Number": 1014,
      "ClientName": "Water Technologies de Mexico S.A de C.V.",
      "LegalName": "Water Technologies de Mexico S.A de C.V.",
      "RFC": "WTM9412025E7",
      "Email": "monica@tratamientosdeagua.com",
      "Phone": "8344-0300",
      "NextContactDate": null,
      "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
      "RegimenFiscal": null
    },
    {
      "ID": "88c0cf85-d98a-451d-ad23-013fac170e9b",
      "Number": 1577,
      "ClientName": "AQILAB",
      "LegalName": "LABORATORIO AQI",
      "RFC": "LAQ200427LF1",
      "Email": "compras@aqilab.com.mx",
      "Phone": "6566160106",
      "NextContactDate": null,
      "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
      "RegimenFiscal": "601"
    }
  ],
  "nextLink": null,
  "count": 5
}
```

### Campos del Cliente

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `ID` | UUID | Identificador unico del cliente |
| `Number` | Integer | Numero de cliente interno |
| `ClientName` | String | Nombre comercial |
| `LegalName` | String | Razon social |
| `RFC` | String | RFC del cliente |
| `Email` | String | Correo electronico |
| `Phone` | String | Telefono |
| `NextContactDate` | DateTime | Fecha de proximo contacto |
| `LocationID` | UUID | ID de la ubicacion |
| `RegimenFiscal` | String | Codigo de regimen fiscal SAT |

### Codigos de Regimen Fiscal

| Codigo | Descripcion |
|--------|-------------|
| 601 | General de Ley Personas Morales |
| 603 | Personas Morales con Fines no Lucrativos |
| 612 | Personas Fisicas con Actividades Empresariales |

---

## 4. Productos (Products)

Obtiene el catalogo de productos.

### Endpoint
```
GET /Products
GET /Products?$filter=Code eq 'CODIGO'
```

### Metodo del Cliente
```python
# Obtener todos los productos (paginado automaticamente)
products = client.get_products()

# Buscar producto por codigo
product = client.get_product_by_code("SI-221279-500G")
```

### Respuesta Real (muestra de 5 productos)
```json
{
  "value": [
    {
      "ID": "ed5e0c93-1fd1-4812-8449-0000ddfba72b",
      "Code": "SI-221279-500G",
      "Title": "Manganese(II) chloride tetrahydrate ACS reagent, >=98%",
      "Description": null,
      "CreationDate": "2018-08-16T12:42:53.06",
      "Cost": 2255.3,
      "SKU": "SI-221279-500G",
      "Comments": "",
      "CostType": 2,
      "CostTypeText": "Promedio",
      "Category1ID": "001409d4-64ae-43f2-b483-6ac75bf91a8b",
      "Category2ID": "946c55b7-719a-42c4-a92e-553d2ebda429",
      "Category3ID": "61d2513f-be52-4a6d-9578-360f8ae0472a",
      "CurrentInventory": 0.0,
      "ChargeVAT": false,
      "Number": 4403,
      "PricingType": 0,
      "PricingTypeText": "Listas",
      "Unit": "pz",
      "CurrencyID": "b7e2c065-bd52-40ca-b508-3accdd538860",
      "CurrencyCode": "MXN",
      "PurchaseType": 0,
      "PurchaseTypeText": "Regular",
      "IEPSRate": 0.0,
      "Type": 0,
      "TypeText": "Producto Terminado",
      "ProductionAuto": false,
      "Volume": 0.0,
      "Weight": 0.0
    },
    {
      "ID": "6a58d253-57c1-47cc-8cd3-000242d397f6",
      "Code": "CT-0017",
      "Title": "Oxoid Colistin Antimicrobial Susceptibility Disks.",
      "Description": null,
      "CreationDate": "2020-09-24T13:03:24.68",
      "Cost": 190.0,
      "SKU": "CT-0017",
      "CostTypeText": "Promedio",
      "CurrentInventory": 0.0,
      "Unit": "PZ",
      "CurrencyCode": "USD",
      "TypeText": "Producto Terminado"
    },
    {
      "ID": "e2842a4a-83ae-4259-a500-00035106b7cb",
      "Code": "ABUS-87151-1",
      "Title": "V500 BLOQUEO PARA VALVULA ABUS",
      "Description": "V500 BLOQUEO PARA VALVULA ABUS",
      "CreationDate": "2025-08-06T12:28:01.163",
      "Cost": 369.781,
      "Unit": "PIEZA",
      "CurrencyCode": "MXN"
    },
    {
      "ID": "f51adc48-595a-46ec-baa5-00040afb7a4a",
      "Code": "A1015-1.0",
      "Title": "ACEITE MINERAL, BLANCO, N.F. FRASCO DE 1 L MARCA HYGH PURITY",
      "Description": "(INOLORO E INCOLORO, SE OBTIENE DEL PETROLEO)",
      "Cost": 71.4,
      "Unit": "PZ",
      "CurrencyCode": "MXN"
    },
    {
      "ID": "39fbd7de-40d0-4151-a251-0005fc1ccac5",
      "Code": "CRM-2028E",
      "Title": "Vaso graduado tipo Jarra de 1000ml. Modelo CRM-2028E",
      "Description": "Graduacion en relieve, reborde y pico. Fabricado en polipropileno irrompible.",
      "Cost": 109.06,
      "Unit": "PZ",
      "CurrencyCode": "MXN"
    }
  ],
  "nextLink": null,
  "count": 5
}
```

### Campos del Producto

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `ID` | UUID | Identificador unico |
| `Code` | String | Codigo del producto |
| `Title` | String | Nombre/Titulo del producto |
| `Description` | String | Descripcion detallada |
| `CreationDate` | DateTime | Fecha de creacion |
| `Cost` | Decimal | Costo del producto |
| `SKU` | String | SKU del producto |
| `CostType` | Integer | Tipo de costeo (0=Ultimo, 2=Promedio) |
| `CostTypeText` | String | Descripcion del tipo de costeo |
| `Category1ID` | UUID | Categoria nivel 1 |
| `Category2ID` | UUID | Categoria nivel 2 |
| `Category3ID` | UUID | Categoria nivel 3 |
| `CurrentInventory` | Decimal | Inventario actual |
| `ChargeVAT` | Boolean | Cobra IVA |
| `Number` | Integer | Numero interno |
| `PricingType` | Integer | Tipo de precio |
| `Unit` | String | Unidad de medida |
| `CurrencyCode` | String | Codigo de moneda (MXN, USD) |
| `IEPSRate` | Decimal | Tasa de IEPS |
| `Type` | Integer | Tipo de producto |
| `TypeText` | String | "Producto Terminado", "Materia Prima", etc. |
| `Volume` | Decimal | Volumen |
| `Weight` | Decimal | Peso |

---

## 5. Facturas (Invoices)

Obtiene las facturas emitidas.

### Endpoint
```
GET /Invoices
GET /Invoices?$filter=Date gt DateTime'2026-01-13T00:00:00'
GET /Invoices/{invoice_id}
POST /Invoices
```

### Metodo del Cliente
```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CDMX_TZ = ZoneInfo("America/Mexico_City")

# Obtener facturas de los ultimos 7 dias
since = datetime.now(CDMX_TZ) - timedelta(days=7)
invoices = client.get_invoices(created_since=since, limit=10)

# Obtener una factura especifica
invoice = client.get_invoice("c58f032d-f46a-40bd-8d3b-d2202e911248")

# Crear una factura
new_invoice = client.create_invoice(invoice_data)
```

### Respuesta Real (facturas del 19 de enero 2026)
```json
{
  "value": [
    {
      "ID": "c58f032d-f46a-40bd-8d3b-d2202e911248",
      "Serie": "AWAFAC -",
      "Date": "2026-01-19T19:34:15.903",
      "Number": 20260159,
      "UUID": "65491c47-94e5-4da0-a8ef-9510a562e226",
      "ExpirationDate": "2026-03-20T19:34:15.903",
      "ClientID": "b7426b2c-dd8c-4f65-bd9b-44746e088209",
      "ClientName": "DEREMATE.COM DE MEXICO",
      "RFC": "DCM991109KR2",
      "Cost": 227962.4,
      "Subtotal": 373360.0,
      "Discount": 0.0,
      "VAT": 59737.6,
      "IEPS": 0.0,
      "ISRRet": 0.0,
      "VATRet": 0.0,
      "Total": 433097.6,
      "Payments": 0.0,
      "CreditNotes": 0.0,
      "CurrencyID": "b7e2c065-bd52-40ca-b508-3accdd538860",
      "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
      "WarehouseID": "07059d9b-b0e1-47cc-b93c-c1048603f20a",
      "PriceListID": "a9e04a3d-23c5-4658-ab6e-8eb03c41f498",
      "CFDIUse": 1,
      "ExchangeRate": 1.0,
      "VATRetRate": 0.0,
      "Comments": "MXJC02 | DANIELA HERNANDEZ Cel. 55 4466 3639...",
      "VATRate": 0.16,
      "PurchaseOrder": "4300462131",
      "IsFiscalInvoice": true,
      "ShowIEPS": true,
      "Status": 0
    },
    {
      "ID": "c4db9805-3081-4f06-8ced-3106caad1050",
      "Serie": "AWAFAC -",
      "Date": "2026-01-19T17:59:58.8",
      "Number": 20260158,
      "UUID": "74dc4ab3-4b74-4a64-ab86-7565088e798c",
      "ClientName": "GEODIS MEXICO",
      "RFC": "GWM790307NB0",
      "Subtotal": 16798.0,
      "VAT": 2687.68,
      "Total": 19485.68,
      "PurchaseOrder": "GPO00516650",
      "IsFiscalInvoice": true,
      "Status": 0
    },
    {
      "ID": "260d3ead-a6de-4f13-8f8c-22ab095143e3",
      "Serie": "AWAFAC -",
      "Date": "2026-01-19T17:36:24.04",
      "Number": 20260157,
      "UUID": "3d12f74b-29cf-48c4-97d8-1cce96a8e174",
      "ClientName": "GEODIS MEXICO",
      "RFC": "GWM790307NB0",
      "Total": 6124.8,
      "PurchaseOrder": "GPO00508720",
      "Status": 0
    },
    {
      "ID": "9391a8c7-4829-464c-8e92-2957ded11c1a",
      "Serie": "AWAFAC -",
      "Date": "2026-01-19T17:35:51.03",
      "Number": 20260156,
      "UUID": "69128d1c-64f4-4444-a7c5-d6c200b842d5",
      "ClientName": "DEREMATE.COM DE MEXICO",
      "RFC": "DCM991109KR2",
      "Total": 9133.84,
      "PurchaseOrder": "4300483031",
      "Status": 0
    },
    {
      "ID": "16f62bbb-1bc6-411c-81fe-f1775266e6a5",
      "Serie": "AWAFAC -",
      "Date": "2026-01-19T17:31:58.55",
      "Number": 20260155,
      "UUID": "18e2892f-fe30-4b7a-9893-4059b0f2753b",
      "ClientName": "PROPIMEX",
      "RFC": "PRO840423SG8",
      "Total": 75578.64,
      "PurchaseOrder": "8331153488",
      "Status": 0
    }
  ],
  "nextLink": null,
  "count": 5
}
```

### Campos de la Factura

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `ID` | UUID | Identificador unico de Bind |
| `Serie` | String | Serie de la factura |
| `Date` | DateTime | Fecha de emision |
| `Number` | Integer | Folio de la factura |
| `UUID` | UUID | UUID del CFDI (SAT) |
| `ExpirationDate` | DateTime | Fecha de vencimiento |
| `ClientID` | UUID | ID del cliente |
| `ClientName` | String | Nombre del cliente |
| `RFC` | String | RFC del cliente |
| `Cost` | Decimal | Costo total |
| `Subtotal` | Decimal | Subtotal sin IVA |
| `Discount` | Decimal | Descuento aplicado |
| `VAT` | Decimal | Monto de IVA |
| `IEPS` | Decimal | Monto de IEPS |
| `ISRRet` | Decimal | Retencion de ISR |
| `VATRet` | Decimal | Retencion de IVA |
| `Total` | Decimal | Total de la factura |
| `Payments` | Decimal | Pagos aplicados |
| `CreditNotes` | Decimal | Notas de credito aplicadas |
| `CurrencyID` | UUID | ID de la moneda |
| `LocationID` | UUID | ID de la ubicacion |
| `WarehouseID` | UUID | ID del almacen |
| `PriceListID` | UUID | ID de la lista de precios |
| `CFDIUse` | Integer | Codigo de uso de CFDI |
| `ExchangeRate` | Decimal | Tipo de cambio |
| `VATRate` | Decimal | Tasa de IVA (0.16 = 16%) |
| `VATRetRate` | Decimal | Tasa de retencion de IVA |
| `Comments` | String | Comentarios/Notas |
| `PurchaseOrder` | String | Orden de compra del cliente |
| `IsFiscalInvoice` | Boolean | Es factura fiscal (CFDI) |
| `ShowIEPS` | Boolean | Mostrar IEPS |
| `Status` | Integer | Estado de la factura |

### Estados de Factura (Status)

| Valor | Descripcion | Condicion |
|-------|-------------|-----------|
| 0 | **Vigente** | Si tiene UUID (timbrada) |
| 0 | **Borrador** | Si no tiene UUID (sin timbrar) |
| 1 | **Pagada** | Factura pagada completamente |
| 2 | **Cancelada** | Factura cancelada |

### Logica para determinar el estado real:
```python
def get_invoice_status(invoice: dict) -> str:
    status = invoice.get("Status", 0)
    has_uuid = bool(invoice.get("UUID"))

    if status == 2:
        return "Cancelada"
    elif status == 1:
        return "Pagada"
    elif status == 0:
        if has_uuid:
            return "Vigente"  # Timbrada, no pagada
        else:
            return "Borrador"  # Sin timbrar
    else:
        return "Desconocido"
```

---

## 6. Paginacion OData

La API de Bind soporta paginacion OData con los siguientes parametros:

### Parametros
- `$skip`: Numero de registros a saltar
- `$top`: Numero maximo de registros a obtener (max 100)
- `$filter`: Filtro OData
- `$orderby`: Ordenamiento

### Ejemplo de Paginacion
```python
# Primera pagina (registros 0-99)
page1 = client._request('GET', '/Products', params={'$skip': 0, '$top': 100})

# Segunda pagina (registros 100-199)
page2 = client._request('GET', '/Products', params={'$skip': 100, '$top': 100})
```

### Filtros OData Comunes

```python
# Filtrar por RFC
params = {"$filter": "RFC eq 'DCM991109KR2'"}

# Filtrar por fecha
params = {"$filter": "Date gt DateTime'2026-01-19T00:00:00'"}

# Filtrar por codigo de producto
params = {"$filter": "Code eq 'SI-221279-500G'"}

# Ordenar por fecha descendente
params = {"$orderby": "Date desc"}

# Combinar filtro y orden
params = {
    "$filter": "Date gt DateTime'2026-01-01T00:00:00'",
    "$orderby": "Date desc",
    "$top": 50
}
```

---

## 7. Manejo de Errores

### Codigos de Error

| Codigo | Descripcion | Accion |
|--------|-------------|--------|
| 200 | Exito | Procesar respuesta |
| 201 | Creado | Recurso creado exitosamente |
| 204 | Sin contenido | Operacion exitosa sin respuesta |
| 400 | Bad Request | Verificar parametros |
| 401 | No autorizado | Verificar API Key |
| 404 | No encontrado | El recurso no existe |
| 429 | Rate limit | Esperar y reintentar |
| 500 | Error del servidor | Reintentar con backoff |

### Ejemplo de Manejo de Errores
```python
from bind_client import BindClient, BindAPIError

client = BindClient()

try:
    invoice = client.get_invoice("uuid-invalido")
except BindAPIError as e:
    print(f"Error {e.status_code}: {e}")
    if e.response_body:
        print(f"Detalle: {e.response_body}")
```

---

## 8. Configuracion del Cliente

### Variables de Entorno Requeridas
```env
BIND_API_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
BIND_API_BASE_URL=https://api.bind.com.mx/api
BIND_WAREHOUSE_ID=07059d9b-b0e1-47cc-b93c-c1048603f20a
```

### Inicializacion
```python
from bind_client import BindClient

# Usando variables de entorno (recomendado)
client = BindClient()

# O especificando credenciales
client = BindClient(
    api_key="tu_api_key",
    base_url="https://api.bind.com.mx/api"
)
```

### Configuracion de Reintentos
```python
# En config.py
BIND_MAX_RETRIES = 3
BIND_INITIAL_BACKOFF = 1.0  # segundos
```

---

## 9. Ejemplos de Uso Completo

### Sincronizar Facturas a Smartsheet
```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bind_client import BindClient
from smartsheet_service import SmartsheetService

CDMX_TZ = ZoneInfo("America/Mexico_City")

def sync_recent_invoices():
    bind = BindClient()
    ss = SmartsheetService()

    # Obtener facturas de los ultimos 10 minutos
    since = datetime.now(CDMX_TZ) - timedelta(minutes=10)
    invoices = bind.get_invoices(created_since=since)

    print(f"Facturas encontradas: {len(invoices)}")

    for inv in invoices:
        # Determinar estado
        status = "Vigente" if inv.get("UUID") else "Borrador"
        if inv.get("Status") == 1:
            status = "Pagada"
        elif inv.get("Status") == 2:
            status = "Cancelada"

        # Preparar datos para Smartsheet
        row_data = {
            "UUID": inv.get("UUID", ""),
            "Serie": inv.get("Serie", ""),
            "Folio": inv.get("Number"),
            "Fecha": inv.get("Date"),
            "Cliente": inv.get("ClientName"),
            "RFC": inv.get("RFC"),
            "Subtotal": inv.get("Subtotal", 0),
            "IVA": inv.get("VAT", 0),
            "Total": inv.get("Total", 0),
            "Estatus": status,
            "Orden Compra": inv.get("PurchaseOrder", ""),
        }

        # UPSERT en Smartsheet
        ss.upsert_row(sheet_id, row_data, key_column="UUID")

    return {"synced": len(invoices)}
```

### Buscar Cliente y Crear Factura
```python
def create_invoice_for_client(rfc: str, products: list):
    bind = BindClient()

    # Buscar cliente
    client = bind.get_client_by_rfc(rfc)
    if not client:
        raise ValueError(f"Cliente con RFC {rfc} no encontrado")

    # Preparar datos de factura
    invoice_data = {
        "ClientID": client["ID"],
        "Date": datetime.now(CDMX_TZ).isoformat(),
        "Items": products,
        "CFDIUse": 3,  # Gastos en general
        "PaymentMethod": "PUE",  # Pago en una sola exhibicion
        "PaymentForm": "03",  # Transferencia
    }

    # Crear factura
    result = bind.create_invoice(invoice_data)
    print(f"Factura creada: {result.get('UUID')}")

    return result
```

---

## Notas Importantes

1. **Zona Horaria**: Todas las fechas en la API estan en formato ISO 8601. Se recomienda usar `America/Mexico_City` para operaciones.

2. **Rate Limiting**: La API tiene limite de peticiones. El cliente implementa backoff exponencial automatico.

3. **Paginacion**: El maximo de registros por pagina es 100. Para obtener todos los registros, usar el metodo `_paginated_get()`.

4. **UUID de Facturas**: Las facturas solo tienen UUID despues de ser timbradas ante el SAT.

5. **Autenticacion**: Usar Bearer token en el header `Authorization`.

---

## 10. Pedidos de Venta (Orders)

Obtiene los pedidos de venta registrados.

### Endpoint
```
GET /Orders
GET /Orders/{id}
POST /Orders
PUT /Orders
DELETE /Orders/{id}
```

### Respuesta Real
```json
{
  "value": [
    {
      "ID": "5214ce26-8bd7-4305-86c0-000111a7b617",
      "ClientID": "4a24c484-8b74-41ba-b5a3-52dbd01900d9",
      "ClientName": "CITROFRUT",
      "PriceListName": "LISTA GENERAL",
      "PriceListID": "a9e04a3d-23c5-4658-ab6e-8eb03c41f498",
      "LocationName": "Matriz",
      "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
      "WarehouseID": "07059d9b-b0e1-47cc-b93c-c1048603f20a",
      "WarehouseName": "Matriz",
      "OrderDate": "2022-10-19T00:00:00",
      "Comments": "DIRECCION DE ENTREGA...",
      "Number": 20222019,
      "ClientContact": null,
      "PhoneNumber": "482 361 4086",
      "EmployeeName": "Arisbeth",
      "EmployeeID": "8dfa8140-1344-4e4f-8923-da1bfca7005f",
      "PurchaseOrder": "2101-062662",
      "Status": 1,
      "CurrencyName": "Dolar estadounidense",
      "CurrencyID": "a260c860-9d2d-480a-b090-82cc9408d7f8",
      "ExchangeRate": 19.9913,
      "RFC": "IDC900827B49",
      "Serie": "AWAPED-",
      "ProductSubtotal": 202423.91,
      "Discount": 0.0,
      "VATRate": 0.16,
      "VAT": 32387.83,
      "Total": 234811.74
    }
  ]
}
```

### Campos del Pedido

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `ID` | UUID | Identificador unico |
| `Number` | Integer | Numero de pedido |
| `ClientID` | UUID | ID del cliente |
| `ClientName` | String | Nombre del cliente |
| `RFC` | String | RFC del cliente |
| `OrderDate` | DateTime | Fecha del pedido |
| `PurchaseOrder` | String | Orden de compra del cliente |
| `Status` | Integer | Estado (0=Activo, 1=Parcial, 2=Completo) |
| `EmployeeName` | String | Vendedor asignado |
| `WarehouseName` | String | Almacen de salida |
| `Total` | Decimal | Total del pedido |
| `CurrencyName` | String | Moneda |
| `ExchangeRate` | Decimal | Tipo de cambio |

---

## 11. Cotizaciones (Quotes)

Obtiene las cotizaciones emitidas a clientes.

### Endpoint
```
GET /Quotes
GET /Quotes/{id}
```

### Respuesta Real
```json
{
  "value": [
    {
      "ID": "000160f1-d270-4897-ad22-d21580f2410e",
      "Number": "20232932",
      "CreationDate": "2023-05-16T09:58:00.627",
      "ClientName": "BEBIDAS ELECTROMAS",
      "Locations": "Matriz",
      "Comments": "TIEMPO ESTIMADO DE ENTREGA 5 DIAS HABILES.",
      "TotalOriginalCurrency": 649.6,
      "Currency": "Peso mexicano",
      "Status": 0,
      "Total": 649.6,
      "StatusText": "Activa"
    },
    {
      "ID": "000174eb-1c39-41f7-b553-553964077e57",
      "Number": "20231661",
      "CreationDate": "2023-03-16T13:42:47.437",
      "ClientName": "URLABTEC",
      "Locations": "Matriz",
      "TotalOriginalCurrency": 831.36,
      "Currency": "Dolar estadounidense",
      "Status": 0,
      "Total": 15498.81,
      "StatusText": "Activa"
    }
  ]
}
```

### Estados de Cotizacion

| Status | StatusText | Descripcion |
|--------|------------|-------------|
| 0 | Activa | Cotizacion vigente |
| 1 | Aceptada | Cliente acepto |
| 2 | Rechazada | Cliente rechazo |
| 3 | Vencida | Paso fecha de vigencia |

---

## 12. Proveedores (Providers)

Obtiene el catalogo de proveedores.

### Endpoint
```
GET /Providers
GET /Providers/{id}
POST /Providers
PUT /Providers
```

### Respuesta Real
```json
{
  "value": [
    {
      "ID": "bb528106-b4a3-47c0-bf50-0092fe9c7ff0",
      "Number": 1420,
      "ProviderName": "CENTRAL POINT SYSTEM SA DE CV",
      "LegalName": "CENTRAL POINT SYSTEM SA DE CV",
      "RFC": "CPS170627KY4",
      "Email": null,
      "Phone": "C&M DISTRIBUCION",
      "City": "Atizapan de Zaragoza"
    },
    {
      "ID": "7190d213-d7b6-4473-8fbb-00c89f1d1e1f",
      "Number": 1894,
      "ProviderName": "OFF ROAD ESCUDERIA",
      "LegalName": "OFF ROAD ESCUDERIA",
      "RFC": "PES1507035J4",
      "Email": "",
      "Phone": "",
      "City": ""
    }
  ]
}
```

---

## 13. Usuarios (Users)

Obtiene los usuarios del sistema Bind ERP.

### Endpoint
```
GET /Users
GET /UserProfile
```

### Respuesta Real - Lista de Usuarios
```json
{
  "value": [
    {
      "ID": "b0684520-ebd0-4dbf-b446-070b1b86581d",
      "FullName": "Carlos Cortes",
      "JobPosition": "",
      "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
      "Email": "direccioncomercial@awalabdemexico.com",
      "UserName": "cortes|43965"
    },
    {
      "ID": "08eef4d9-3a02-4071-9eff-0ddb3daa4b4b",
      "FullName": "Proyectos Awalab",
      "JobPosition": "",
      "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
      "Email": "proyectos@awalabdemexico.com",
      "UserName": "proyectos|43965"
    }
  ]
}
```

### Respuesta Real - Perfil de Usuario (UserProfile)
```json
{
  "CompanyID": "14711e96-793a-4302-8cf8-6e5594d239bf",
  "CompanyName": "AWALAB DE MEXICO",
  "CompanyNumber": 43965,
  "Email": "rodrigodalay@entersys.mx",
  "Name": "Rodrigo Dalay",
  "RFC": "AME180118SQ3",
  "Roles": [
    "10|21|CrearOrdenDeProduccion",
    "14|27|Poliza de Diario",
    "..."
  ]
}
```

---

## 14. Monedas (Currencies)

Obtiene las monedas configuradas con tipo de cambio actual.

### Endpoint
```
GET /Currencies
```

### Respuesta Real
```json
{
  "value": [
    {
      "ID": "b7e2c065-bd52-40ca-b508-3accdd538860",
      "Name": "Peso mexicano",
      "Code": "MXN",
      "ExchangeRate": 1.0
    },
    {
      "ID": "a260c860-9d2d-480a-b090-82cc9408d7f8",
      "Name": "Dolar estadounidense",
      "Code": "USD",
      "ExchangeRate": 17.6867
    }
  ]
}
```

---

## 15. Listas de Precios (PriceLists)

Obtiene las listas de precios configuradas.

### Endpoint
```
GET /PriceLists
```

### Respuesta Real
```json
{
  "value": [
    {
      "ID": "a9e04a3d-23c5-4658-ab6e-8eb03c41f498",
      "Name": "LISTA GENERAL"
    },
    {
      "ID": "ae87ea01-5c9f-43c4-bec4-ed3f7938ba97",
      "Name": "PUBLICACIONES DE MERCADO LIBRE"
    }
  ]
}
```

---

## 16. Cuentas Bancarias (BankAccounts)

Obtiene las cuentas bancarias de la empresa.

### Endpoint
```
GET /BankAccounts
```

### Respuesta Real
```json
{
  "value": [
    {
      "ID": "654feecd-70e7-437c-a72f-17c18f965c21",
      "Type": 1,
      "TypeText": "Credito",
      "BankID": null,
      "BankName": "",
      "Name": "ACREEDORES",
      "Balance": 15628411.90,
      "CurrencyID": "b7e2c065-bd52-40ca-b508-3accdd538860",
      "CurrencyCode": "MXN",
      "LocationID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80"
    },
    {
      "ID": "ba270a93-09e7-4310-9201-3bd4e45999c9",
      "Type": 2,
      "TypeText": "Debito",
      "Name": "MONEDERO ELECTRONICO",
      "Balance": 139283.69,
      "CurrencyCode": "MXN"
    },
    {
      "ID": "d298316f-1bd3-4206-bc0c-59242eef3f7e",
      "Type": 2,
      "TypeText": "Debito",
      "Name": "ANTICIPOS",
      "Balance": 41820.56,
      "CurrencyCode": "MXN"
    }
  ]
}
```

### Tipos de Cuenta

| Type | TypeText | Descripcion |
|------|----------|-------------|
| 1 | Credito | Cuentas de credito/pasivo |
| 2 | Debito | Cuentas de debito/activo |

---

## 17. Bancos (Banks)

Obtiene el catalogo de instituciones bancarias.

### Endpoint
```
GET /Banks
```

### Respuesta Real
```json
{
  "value": [
    {
      "ID": "481271ac-6fcc-49fb-adc0-03ae2bc5b122",
      "Name": "Base"
    },
    {
      "ID": "ff89e9eb-cb8f-4961-850b-0a3374a02bc6",
      "Name": "ASP Integra Opciones"
    }
  ]
}
```

---

## 18. Ubicaciones (Locations)

Obtiene las sucursales/ubicaciones de la empresa.

### Endpoint
```
GET /Locations
```

### Respuesta Real
```json
{
  "value": [
    {
      "ID": "3b4b853b-acd1-483e-aba2-e98f3bfb2b80",
      "Name": "Matriz",
      "Street": "Cerrada Guadalupe Victoria",
      "ExtNumber": "5",
      "IntNumber": " ",
      "ZipCode": "52926",
      "Colonia": "Margarita Maza de Juarez",
      "City": "Atizapan de Zaragoza",
      "State": "Mexico"
    }
  ]
}
```

---

## 19. Categorias de Productos (Categories)

Obtiene el arbol de categorias de productos (3 niveles).

### Endpoint
```
GET /Categories
```

### Respuesta Real (Estructura jerarquica)
```json
[
  {
    "ID": "b7f026d0-acbf-4ff0-9094-a4951bf5fb35",
    "Name": "NIVEL 1",
    "SubCategories": [
      {
        "ID": "29e7b180-615f-456d-b518-012321567250",
        "Name": "NIVEL 2",
        "SubCategories": [
          {
            "ID": "d2a7d799-7ca5-4d45-b8aa-c1ad1737e6fa",
            "Name": "NIVEL3"
          }
        ]
      }
    ]
  },
  {
    "ID": "001409d4-64ae-43f2-b483-6ac75bf91a8b",
    "Name": "LABORATORIO",
    "SubCategories": [
      {
        "ID": "72b4e788-7f7e-47fe-b5ac-5aa09565c8ff",
        "Name": "ACCESORIOS",
        "SubCategories": [
          {"ID": "...", "Name": "ADATA"},
          {"ID": "...", "Name": "AESA"},
          {"ID": "...", "Name": "Anton Paar"}
        ]
      }
    ]
  }
]
```

---

## 20. Cuentas Contables (Accounts)

Obtiene el catalogo de cuentas contables.

### Endpoint
```
GET /Accounts
GET /AccountCategories
```

### Respuesta Real - Cuentas
```json
{
  "value": [
    {
      "ID": "ad6c4da4-a257-4067-8e62-00160c955476",
      "GLGroup": "Pasivos circulantes",
      "Group": "Impuestos trasladados cobrados",
      "SubGroup": "IVA trasladado cobrado",
      "GLGroupID": "f689f0fa-724b-4469-83e8-d0b7174567ed",
      "GroupID": "abec8711-3d23-4c04-bd81-994a516cf342",
      "SubGroupID": "62057880-4575-4e1e-baa6-11c46767b9c4",
      "Number": "208-01-001",
      "Description": "IVA trasladado cobrado"
    },
    {
      "ID": "87beb97c-d869-4acf-adca-02a360df9130",
      "GLGroup": "Ingresos",
      "Group": "Otros ingresos",
      "SubGroup": "Otros Ingresos",
      "Number": "403-01-001",
      "Description": "Otros Ingresos"
    }
  ]
}
```

---

## 21. Polizas Contables (AccountingJournals)

Obtiene las polizas contables registradas.

### Endpoint
```
GET /AccountingJournals
POST /AccountingJournals
PUT /AccountingJournals
DELETE /AccountingJournals
```

### Respuesta Real
```json
{
  "value": [
    {
      "ID": "86c47ae0-cde8-4335-9449-00015e167997",
      "DocumentID": "8e129294-1e83-43b3-b5ae-9126cbe7ee2e",
      "Type": "Gasto",
      "ApplicationDate": "2025-07-31T14:13:35",
      "CreationDate": "2025-08-14T18:35:21.52",
      "Number": 56452,
      "LocationID": null,
      "PeriodType": "Diario",
      "Items": [
        {
          "AccountID": "69ca9976-bec2-462e-b7ef-3bc4dfb22995",
          "AccountName": "601-84-001 - Gastos generales",
          "Description": "Gasto #12330 - LOGILAN",
          "Debit": 0.0,
          "Charge": 1159.29
        },
        {
          "AccountID": "69ca9976-bec2-462e-b7ef-3bc4dfb22995",
          "AccountName": "601-84-001 - Gastos generales",
          "Description": "Gasto #12330 - LOGILAN",
          "Debit": 0.0,
          "Charge": 299.0
        }
      ]
    }
  ]
}
```

---

## 22. WebHooks

Permite suscribirse a eventos del sistema.

### Endpoint
```
GET /WebHooks                    - Lista eventos disponibles
GET /WebHooks/{eventID}          - Ejemplo de payload
GET /WebHookSubscriptions        - Lista suscripciones activas
POST /WebHookSubscriptions       - Crear suscripcion
```

### Eventos Disponibles
```json
{
  "value": [
    {
      "ID": "Add_Activity",
      "EventName": "Add_Activity",
      "EventDescription": "Fired when an activity is generated"
    },
    {
      "ID": "Add_Client",
      "EventName": "Add_Client",
      "EventDescription": "Add Client"
    },
    {
      "ID": "Add_Invoice",
      "EventName": "Add_Invoice",
      "EventDescription": "Fired when invoice is created"
    }
  ]
}
```

### Suscripciones Activas
```json
{
  "value": [
    {
      "ID": "aefc9081-6193-4bfa-8505-0decaa7ff53d",
      "EventID": "Add_Invoice",
      "TargetURL": "https://hooks.zapier.com/hooks/standard/...",
      "EventName": "Add_Invoice"
    }
  ]
}
```

### Eventos Disponibles para WebHooks

| EventID | Descripcion |
|---------|-------------|
| `Add_Activity` | Nueva actividad creada |
| `Add_Client` | Nuevo cliente agregado |
| `Edit_Client` | Cliente modificado |
| `Add_Invoice` | Nueva factura creada |
| `Add_Order` | Nuevo pedido creado |
| `Add_Product` | Nuevo producto agregado |
| `Add_Quote` | Nueva cotizacion creada |
| `Add_Payment` | Pago registrado |

---

## Notas Importantes

1. **Zona Horaria**: Todas las fechas en la API estan en formato ISO 8601. Se recomienda usar `America/Mexico_City` para operaciones.

2. **Rate Limiting**: La API tiene limite de peticiones. El cliente implementa backoff exponencial automatico.

3. **Paginacion**: El maximo de registros por pagina es 100. Para obtener todos los registros, usar el metodo `_paginated_get()`.

4. **UUID de Facturas**: Las facturas solo tienen UUID despues de ser timbradas ante el SAT.

5. **Autenticacion**: Usar Bearer token en el header `Authorization`.

6. **Endpoints no disponibles**: Algunos endpoints de la documentacion oficial no estan habilitados en todas las cuentas (Inventory, PaymentMethods, etc.).

7. **Categories**: Retorna una lista directa (no un objeto con `value`).

---

**Documento generado automaticamente**
**Cliente**: bind_client.py
**Middleware**: Smartsheet-Bind ERP Integration
