# Alcance de la Solucion - Middleware Smartsheet-Bind ERP

**Proyecto:** Middleware de Sincronizacion Smartsheet-Bind ERP
**Cliente:** Awalab
**Version:** 1.0.0
**Fecha:** Enero 2026

---

## 1. Descripcion General

Este middleware actua como puente de integracion entre **Smartsheet** (plataforma de gestion de proyectos) y **Bind ERP** (sistema de facturacion electronica mexicano CFDI 4.0).

### Objetivo Principal

Automatizar dos flujos criticos de negocio:

1. **Facturacion automatica:** Cuando un usuario cambia el estado de una fila en Smartsheet a "Facturar", el sistema automaticamente crea la factura CFDI en Bind ERP.

2. **Sincronizacion de inventario:** El sistema consulta periodicamente el inventario de Bind ERP y actualiza una hoja de Smartsheet con las existencias actuales.

---

## 2. Flujos de Integracion

### 2.1 Flujo PUSH: Smartsheet -> Bind ERP (Facturacion)

```
[Usuario en Smartsheet]
        |
        v
[Cambia columna "Estado" a "Facturar"]
        |
        v
[Smartsheet envia Webhook]
        |
        v
[Middleware recibe POST /webhook/smartsheet]
        |
        v
[Valida datos de la fila]
        |
        v
[Busca cliente en Bind por RFC]
        |
        +---> Si no existe: Error, actualiza Smartsheet con mensaje
        |
        v (Si existe)
[Crea factura CFDI en Bind]
        |
        v
[Actualiza Smartsheet con UUID, Folio, Fecha]
        |
        v
[Cambia Estado a "Facturado"]
```

#### Eventos que disparan el flujo:
- Webhook de Smartsheet con evento `ROW_CHANGED` o `ROW_UPDATED`
- Columna "Estado" con valor exacto "Facturar"

#### Datos requeridos en la fila:
| Campo | Obligatorio | Validacion |
|-------|-------------|------------|
| RFC | Si | Regex: `^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$` |
| Concepto | Si | Texto, max 1000 chars |
| Cantidad | Si | Numero > 0 |
| Precio Unitario | Si | Numero >= 0 |
| Clave SAT Producto | Si | 8 digitos exactos |
| Clave SAT Unidad | Si | 2-3 caracteres alfanumericos |
| Metodo Pago | Si | "PUE" o "PPD" |
| Forma Pago | Si | 2 digitos (ej: "03") |
| Uso CFDI | Si | Formato: letra + 2 digitos (ej: "G03") |
| Regimen Fiscal | No | 3 digitos |
| Codigo Postal | No | 5 digitos |

#### Resultado exitoso:
- UUID del CFDI guardado en columna "UUID"
- Folio fiscal guardado en columna "Folio Fiscal"
- Fecha de facturacion guardada
- Estado cambiado a "Facturado"
- Columna "Resultado" = "Exitoso"

#### Resultado con error:
- Estado cambiado a "Error"
- Columna "Resultado" = mensaje de error
- Comentario agregado a la fila con detalles del error

---

### 2.2 Flujo PULL: Bind ERP -> Smartsheet (Inventario)

```
[Scheduler cada 60 minutos]
        |
        v
[GET /Inventory de Bind ERP]
        |
        v
[Filtra por almacen configurado]
        |
        v
[Obtiene hoja de inventario de Smartsheet]
        |
        v
[Compara productos existentes]
        |
        +---> Producto existe: Actualiza existencias
        |
        +---> Producto nuevo: (pendiente implementar insercion)
        |
        v
[Actualiza columna "Ultima Actualizacion"]
```

#### Frecuencia:
- Configurable via `SYNC_INVENTORY_INTERVAL_MINUTES`
- Default: 60 minutos
- Valor 0 = deshabilitado

#### Datos sincronizados:
| Campo Smartsheet | Campo Bind |
|------------------|------------|
| Codigo | ProductCode |
| Nombre | ProductName |
| Existencia | Quantity/Stock |
| Almacen | WarehouseName |
| Ultima Actualizacion | Timestamp local |

---

## 3. Componentes del Sistema

### 3.1 Servidor FastAPI (`main.py`)

| Endpoint | Metodo | Funcion |
|----------|--------|---------|
| `/` | GET | Health check basico |
| `/health` | GET | Health check con estado de conexiones |
| `/webhook/smartsheet` | POST | Receptor de webhooks, dispara facturacion |
| `/sync/inventory` | POST | Sincronizacion manual de inventario |
| `/sync/inventory/status` | GET | Estado del scheduler |
| `/invoice/process/{sheet_id}/{row_id}` | POST | Facturacion manual de una fila |
| `/scheduler/jobs` | GET | Lista de jobs programados |

### 3.2 Cliente Bind ERP (`bind_client.py`)

| Metodo | Endpoint Bind | Funcion |
|--------|---------------|---------|
| `get_client_by_rfc(rfc)` | GET /Clients | Busca cliente por RFC |
| `create_invoice(data)` | POST /Invoices | Crea factura CFDI |
| `get_products(modified_since)` | GET /Products | Lista productos |
| `get_inventory(warehouse_id)` | GET /Inventory | Obtiene existencias |
| `get_inventory_movements(since)` | GET /InventoryMovements | Movimientos recientes |
| `get_warehouses()` | GET /Warehouses | Lista almacenes |
| `health_check()` | GET /Warehouses | Verifica conectividad |

#### Caracteristicas del cliente:
- **Backoff exponencial:** Reintentos automaticos en errores 429 (rate limit) y 5xx
- **Paginacion OData:** Manejo automatico de `$skip` y `$top`
- **Filtros OData:** Soporte para `$filter` con fechas y campos
- **Rate limiting:** Respeta limite de 300 requests/5 minutos

### 3.3 Servicio Smartsheet (`smartsheet_service.py`)

| Metodo | Funcion |
|--------|---------|
| `get_sheet_as_dataframe(sheet_id)` | Descarga hoja como pandas DataFrame |
| `get_row(sheet_id, row_id)` | Obtiene una fila especifica |
| `update_row_cells(sheet_id, row_id, updates)` | Actualiza multiples celdas |
| `update_invoice_result(...)` | Actualiza resultado de facturacion |
| `add_row_comment(sheet_id, row_id, text)` | Agrega comentario a fila |
| `verify_webhook_signature(...)` | Valida firma HMAC del webhook |
| `health_check()` | Verifica conectividad |

### 3.4 Logica de Negocio (`business_logic.py`)

| Funcion | Responsabilidad |
|---------|-----------------|
| `process_invoice_request()` | Orquesta todo el flujo de facturacion |
| `extract_row_data_from_smartsheet()` | Extrae y valida datos de fila |
| `map_smartsheet_to_bind_invoice()` | Transforma datos al formato de Bind |
| `sync_inventory()` | Sincroniza inventario Bind -> Smartsheet |
| `sync_inventory_movements()` | Sincroniza movimientos recientes |

---

## 4. Estructura de Datos

### 4.1 Columnas de Smartsheet - Hoja de Facturacion

#### Columnas de ENTRADA (usuario llena):

| Columna | Tipo | Ejemplo | Notas |
|---------|------|---------|-------|
| RFC | Texto | XAXX010101000 | RFC del cliente en Bind |
| Razon Social | Texto | Empresa SA de CV | Opcional, referencia |
| Concepto | Texto | Servicio de consultoria | Descripcion del producto/servicio |
| Descripcion | Texto | Horas de soporte tecnico | Detalle adicional |
| Cantidad | Numero | 10 | Cantidad a facturar |
| Precio Unitario | Numero | 1500.00 | Precio sin IVA |
| Clave SAT Producto | Texto | 81111500 | ClaveProdServ del catalogo SAT |
| Clave SAT Unidad | Texto | E48 | ClaveUnidad del catalogo SAT |
| Metodo Pago | Lista | PUE | PUE=Pago en Una Exhibicion, PPD=Pago en Parcialidades |
| Forma Pago | Texto | 03 | 01=Efectivo, 03=Transferencia, etc |
| Uso CFDI | Texto | G03 | G01=Adquisicion, G03=Gastos en general, etc |
| Regimen Fiscal | Texto | 601 | Regimen fiscal del receptor |
| Codigo Postal | Texto | 06600 | CP del domicilio fiscal |
| Estado | Lista | Facturar | Valor que dispara el webhook |

#### Columnas de SALIDA (sistema llena):

| Columna | Tipo | Ejemplo | Notas |
|---------|------|---------|-------|
| UUID | Texto | 6BA7B810-9DAD-11D1-... | UUID del CFDI |
| Folio Fiscal | Texto | A-12345 | Folio de la factura |
| Fecha Facturacion | Fecha | 2026-01-17 10:30:00 | Timestamp de emision |
| Resultado | Texto | Exitoso / Error: ... | Estado de la operacion |

### 4.2 JSON de Factura enviado a Bind

```json
{
  "ClientID": "uuid-del-cliente-en-bind",
  "Date": "2026-01-17T10:30:00",
  "PaymentMethod": "PUE",
  "PaymentForm": "03",
  "CFDIUse": "G03",
  "Currency": "MXN",
  "ExchangeRate": 1,
  "Items": [
    {
      "ProductServiceKey": "81111500",
      "UnitKey": "E48",
      "Description": "Servicio de consultoria",
      "Quantity": 10,
      "UnitPrice": 1500.00,
      "Subtotal": 15000.00,
      "Taxes": [
        {
          "Name": "IVA",
          "Rate": 0.16,
          "Amount": 2400.00,
          "Type": "Tasa",
          "Base": 15000.00
        }
      ],
      "Total": 17400.00
    }
  ],
  "Subtotal": 15000.00,
  "Total": 17400.00
}
```

### 4.3 Columnas de Smartsheet - Hoja de Inventario

| Columna | Tipo | Fuente |
|---------|------|--------|
| Codigo | Texto | ProductCode de Bind |
| Nombre | Texto | ProductName de Bind |
| Existencia | Numero | Quantity de Bind |
| Almacen | Texto | WarehouseName de Bind |
| Ultima Actualizacion | Fecha | Timestamp del sistema |

---

## 5. Integraciones Externas

### 5.1 Bind ERP API

| Aspecto | Detalle |
|---------|---------|
| Base URL | `https://api.bind.com.mx/api` |
| Autenticacion | Bearer Token (JWT) |
| Rate Limit | 300 requests / 5 minutos |
| Formato | JSON |
| Paginacion | OData ($skip, $top) |
| Filtros | OData ($filter) |

### 5.2 Smartsheet API

| Aspecto | Detalle |
|---------|---------|
| SDK | smartsheet-python-sdk v3.7+ |
| Autenticacion | Access Token |
| Webhooks | HMAC-SHA256 signature |
| Rate Limit | Manejado por SDK |

---

## 6. Manejo de Errores

### 6.1 Errores de Bind ERP

| Codigo | Accion |
|--------|--------|
| 429 | Backoff exponencial, reintento hasta 5 veces |
| 5xx | Backoff exponencial, reintento hasta 5 veces |
| 4xx | Error inmediato, se reporta a Smartsheet |
| Timeout | Reintento con backoff |

### 6.2 Errores de Smartsheet

| Error | Accion |
|-------|--------|
| Fila no encontrada | Log error, continua con otras |
| Columna no existe | Log warning, ignora campo |
| API error | Exception, log completo |

### 6.3 Errores de Validacion

| Error | Accion |
|-------|--------|
| Campo requerido faltante | Error en Smartsheet con lista de campos |
| RFC invalido | Error con mensaje especifico |
| Cliente no existe en Bind | Error indicando registrar cliente primero |
| Formato de datos invalido | Error con detalle de validacion Pydantic |

---

## 7. Limitaciones Actuales

### 7.1 Funcionalidad NO implementada

| Feature | Estado | Notas |
|---------|--------|-------|
| Creacion de clientes en Bind | No implementado | Cliente debe existir previamente |
| Insercion de nuevas filas de inventario | Parcial | Solo actualiza existentes |
| Multiples lineas por factura | No implementado | Una fila = una linea de factura |
| Notas de credito | No implementado | Solo facturas de ingreso |
| Complementos de pago | No implementado | Solo metodo PUE funciona completamente |
| Facturacion masiva | No implementado | Una factura a la vez |
| Cancelacion de facturas | No implementado | Solo emision |

### 7.2 Restricciones tecnicas

| Restriccion | Detalle |
|-------------|---------|
| IVA fijo 16% | Calculado automaticamente, no configurable por fila |
| Moneda MXN | Fija, no soporta USD u otras |
| Un almacen | Configurado en variable de entorno |
| Una hoja de facturas | Configurada en variable de entorno |
| Webhook sin reintentos | Si falla, no se reintenta automaticamente |

### 7.3 Dependencias externas

| Dependencia | Riesgo |
|-------------|--------|
| API de Bind disponible | Si Bind cae, no hay facturacion |
| API de Smartsheet disponible | Si Smartsheet cae, no hay actualizaciones |
| Certificado SSL valido | Gestionado por Traefik/Let's Encrypt |
| DNS configurado | Dominio debe apuntar al servidor |

---

## 8. Seguridad

### 8.1 Credenciales

| Credencial | Almacenamiento |
|------------|----------------|
| BIND_API_KEY | Variable de entorno (.env) |
| SMARTSHEET_ACCESS_TOKEN | Variable de entorno (.env) |
| SMARTSHEET_WEBHOOK_SECRET | Variable de entorno (.env) |

### 8.2 Validaciones

| Validacion | Implementacion |
|------------|----------------|
| Firma de webhook | HMAC-SHA256 (opcional si no hay secret) |
| Datos de factura | Pydantic con regex patterns |
| RFC | Validacion de formato mexicano |

### 8.3 Red

| Aspecto | Configuracion |
|---------|---------------|
| HTTPS | Obligatorio via Traefik |
| Puertos expuestos | Solo 443 (Traefik) |
| Red interna | Docker bridge aislada |

---

## 9. Monitoreo y Logs

### 9.1 Health Checks

```json
{
  "status": "ok",
  "timestamp": "2026-01-17T10:30:00",
  "bind_connected": true,
  "smartsheet_connected": true
}
```

### 9.2 Logs estructurados

Formato de logs:
```
2026-01-17 10:30:00 - module - LEVEL - mensaje
```

Niveles:
- DEBUG: Detalles de requests/responses
- INFO: Operaciones normales
- WARNING: Situaciones recuperables
- ERROR: Fallos de operacion

### 9.3 Metricas disponibles

- Contenedor monitoreado por cAdvisor
- CPU, RAM, red via Prometheus
- Dashboards en Grafana

---

## 10. Escalabilidad

### 10.1 Estado actual

| Metrica | Valor |
|---------|-------|
| Contenedores | 1 |
| CPU limit | 0.5 cores |
| RAM limit | 512 MB |
| Concurrencia | Asyncio (multiples requests) |

### 10.2 Cuellos de botella potenciales

| Componente | Limite |
|------------|--------|
| Rate limit Bind | 300 req/5min |
| Procesamiento secuencial | Una factura a la vez por fila |
| Scheduler single-thread | Una sincronizacion a la vez |

### 10.3 Opciones de escalamiento

| Opcion | Complejidad |
|--------|-------------|
| Aumentar recursos del contenedor | Baja |
| Multiples workers Uvicorn | Media |
| Cola de mensajes (Redis/RabbitMQ) | Alta |
| Multiples instancias con load balancer | Alta |

---

## 11. Mantenimiento

### 11.1 Tareas periodicas

| Tarea | Frecuencia |
|-------|------------|
| Revisar logs de errores | Diaria |
| Verificar health check | Automatico (cada 30s) |
| Actualizar dependencias | Mensual |
| Rotar API keys | Segun politica de seguridad |

### 11.2 Respaldos

| Elemento | Respaldo |
|----------|----------|
| Codigo | GitHub |
| Configuracion (.env) | Manual, no en Git |
| Logs | Volumen Docker, Loki |
| Datos de facturas | En Bind ERP y Smartsheet |

---

## 12. Roadmap Futuro (No implementado)

| Feature | Prioridad | Complejidad |
|---------|-----------|-------------|
| Multiples lineas por factura | Alta | Media |
| Creacion automatica de clientes | Alta | Media |
| Soporte para notas de credito | Media | Alta |
| Dashboard de monitoreo propio | Media | Media |
| Notificaciones por email/Slack | Media | Baja |
| Facturacion masiva (batch) | Baja | Alta |
| Soporte multi-moneda | Baja | Media |
| API REST para integraciones externas | Baja | Media |

---

## 13. Contacto y Soporte

| Rol | Contacto |
|-----|----------|
| Administrador de infraestructura | armando.cortes@entersys.mx |
| Repositorio | https://github.com/EntersysMX/smartsheet-bind-awalab |
| Documentacion de despliegue | DEPLOY.md |

---

**Documento generado por:** Claude Code
**Ultima actualizacion:** Enero 2026
