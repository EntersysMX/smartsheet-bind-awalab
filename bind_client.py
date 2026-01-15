"""
bind_client.py - Cliente personalizado para la API de Bind ERP.
Implementa manejo de reintentos con backoff exponencial y paginación OData.
"""

import logging
import time
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import settings

logger = logging.getLogger(__name__)


class BindAPIError(Exception):
    """Excepción personalizada para errores de la API de Bind."""

    def __init__(self, message: str, status_code: int = None, response_body: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class BindClient:
    """
    Cliente HTTP para interactuar con la API de Bind ERP.

    Características:
    - Autenticación mediante Bearer token
    - Reintentos automáticos con backoff exponencial para errores 429/5xx
    - Soporte para paginación OData ($skip, $top)
    - Filtrado OData ($filter)
    """

    def __init__(self, api_key: str = None, base_url: str = None):
        """
        Inicializa el cliente de Bind.

        Args:
            api_key: API Key de Bind. Si no se proporciona, usa settings.
            base_url: URL base de la API. Si no se proporciona, usa settings.
        """
        self.api_key = api_key or settings.BIND_API_KEY
        self.base_url = (base_url or settings.BIND_API_BASE_URL).rstrip("/")

        if not self.api_key:
            raise ValueError("BIND_API_KEY es requerida")

        # Configurar sesión con pool de conexiones
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

        # Configurar adaptador con retry básico para errores de conexión
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # Configuración de rate limiting
        self.max_retries = settings.BIND_MAX_RETRIES
        self.initial_backoff = settings.BIND_INITIAL_BACKOFF

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        data: dict = None,
        timeout: int = 30,
    ) -> dict:
        """
        Método privado para realizar peticiones HTTP con reintentos y backoff.

        Args:
            method: Método HTTP (GET, POST, PUT, DELETE)
            endpoint: Endpoint relativo (ej. "/Clients")
            params: Parámetros de query string
            data: Cuerpo de la petición (para POST/PUT)
            timeout: Timeout en segundos

        Returns:
            Respuesta JSON parseada

        Raises:
            BindAPIError: Si la petición falla después de todos los reintentos
        """
        url = f"{self.base_url}{endpoint}"
        backoff = self.initial_backoff

        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"Bind API request: {method} {url} (intento {attempt + 1})")

                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=data,
                    timeout=timeout,
                )

                # Éxito
                if response.status_code in (200, 201, 204):
                    if response.status_code == 204 or not response.content:
                        return {}
                    return response.json()

                # Rate limit - aplicar backoff exponencial
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_time = int(retry_after) if retry_after else backoff

                    logger.warning(
                        f"Rate limit alcanzado (429). Esperando {wait_time}s antes de reintentar..."
                    )

                    if attempt < self.max_retries:
                        time.sleep(wait_time)
                        backoff *= 2  # Backoff exponencial
                        continue
                    else:
                        raise BindAPIError(
                            f"Rate limit excedido después de {self.max_retries} reintentos",
                            status_code=429,
                        )

                # Error de servidor - reintentar con backoff
                if response.status_code >= 500:
                    logger.warning(
                        f"Error de servidor ({response.status_code}). "
                        f"Reintentando en {backoff}s..."
                    )

                    if attempt < self.max_retries:
                        time.sleep(backoff)
                        backoff *= 2
                        continue

                # Error del cliente - no reintentar
                error_body = {}
                try:
                    error_body = response.json()
                except Exception:
                    error_body = {"raw": response.text[:500]}

                error_msg = error_body.get("message", error_body.get("error", str(error_body)))
                logger.error(f"Error en Bind API: {response.status_code} - {error_msg}")

                raise BindAPIError(
                    f"Error {response.status_code}: {error_msg}",
                    status_code=response.status_code,
                    response_body=error_body,
                )

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout en petición a {url}")
                if attempt < self.max_retries:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise BindAPIError(f"Timeout después de {self.max_retries} reintentos")

            except requests.exceptions.RequestException as e:
                logger.error(f"Error de conexión: {e}")
                if attempt < self.max_retries:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise BindAPIError(f"Error de conexión: {e}")

        raise BindAPIError("Error inesperado en petición")

    def _paginated_get(
        self,
        endpoint: str,
        params: dict = None,
        page_size: int = 100,
        max_records: int = None,
    ) -> list[dict]:
        """
        Obtiene todos los registros de un endpoint con paginación OData.

        Args:
            endpoint: Endpoint a consultar
            params: Parámetros adicionales de query
            page_size: Registros por página
            max_records: Máximo de registros a obtener (None = todos)

        Returns:
            Lista con todos los registros obtenidos
        """
        all_records = []
        skip = 0
        params = params or {}

        while True:
            page_params = {**params, "$skip": skip, "$top": page_size}
            response = self._request("GET", endpoint, params=page_params)

            # Manejar diferentes formatos de respuesta
            if isinstance(response, list):
                records = response
            elif "value" in response:
                records = response["value"]
            else:
                records = [response] if response else []

            if not records:
                break

            all_records.extend(records)

            # Verificar límite máximo
            if max_records and len(all_records) >= max_records:
                all_records = all_records[:max_records]
                break

            # Verificar si hay más páginas
            if len(records) < page_size:
                break

            # Verificar nextLink de OData
            if "nextLink" not in response and "@odata.nextLink" not in response:
                if len(records) < page_size:
                    break

            skip += page_size
            logger.debug(f"Paginación: obtenidos {len(all_records)} registros...")

        logger.info(f"Total registros obtenidos de {endpoint}: {len(all_records)}")
        return all_records

    # ========== MÉTODOS DE CLIENTES ==========

    def get_client_by_rfc(self, rfc: str) -> Optional[dict]:
        """
        Busca un cliente por su RFC usando filtro OData.

        Args:
            rfc: RFC del cliente a buscar

        Returns:
            Datos del cliente o None si no existe
        """
        # Normalizar RFC (mayúsculas, sin espacios)
        rfc = rfc.strip().upper()

        params = {"$filter": f"RFC eq '{rfc}'"}
        response = self._request("GET", "/Clients", params=params)

        # Manejar formato de respuesta
        if isinstance(response, list):
            clients = response
        elif "value" in response:
            clients = response["value"]
        else:
            clients = []

        if clients:
            logger.info(f"Cliente encontrado para RFC {rfc}: {clients[0].get('ID')}")
            return clients[0]

        logger.warning(f"No se encontró cliente con RFC: {rfc}")
        return None

    def get_clients(self, modified_since: datetime = None) -> list[dict]:
        """
        Obtiene lista de clientes, opcionalmente filtrados por fecha de modificación.

        Args:
            modified_since: Solo obtener clientes modificados después de esta fecha

        Returns:
            Lista de clientes
        """
        params = {}
        if modified_since:
            date_str = modified_since.strftime("%Y-%m-%dT%H:%M:%S")
            params["$filter"] = f"ModificationDate gt DateTime'{date_str}'"

        return self._paginated_get("/Clients", params=params)

    # ========== MÉTODOS DE FACTURAS ==========

    def create_invoice(self, invoice_data: dict) -> dict:
        """
        Crea una factura (CFDI) en Bind ERP.

        Args:
            invoice_data: Datos de la factura según esquema de Bind

        Returns:
            Respuesta de Bind con UUID, folio, etc.

        Raises:
            BindAPIError: Si hay error en la creación
        """
        logger.info(f"Creando factura para cliente: {invoice_data.get('ClientID')}")

        response = self._request("POST", "/Invoices", data=invoice_data)

        logger.info(
            f"Factura creada exitosamente. UUID: {response.get('UUID')}, "
            f"Folio: {response.get('Folio')}"
        )

        return response

    def get_invoice(self, invoice_id: str) -> dict:
        """Obtiene una factura por su ID."""
        return self._request("GET", f"/Invoices/{invoice_id}")

    def get_invoices(self, created_since: datetime = None) -> list[dict]:
        """
        Obtiene lista de facturas.

        Args:
            created_since: Solo facturas creadas después de esta fecha
        """
        params = {}
        if created_since:
            date_str = created_since.strftime("%Y-%m-%dT%H:%M:%S")
            params["$filter"] = f"CreationDate gt DateTime'{date_str}'"

        return self._paginated_get("/Invoices", params=params)

    # ========== MÉTODOS DE PRODUCTOS ==========

    def get_products(self, modified_since: datetime = None) -> list[dict]:
        """
        Obtiene productos del catálogo.

        Args:
            modified_since: Solo productos modificados después de esta fecha

        Returns:
            Lista de productos
        """
        params = {}
        if modified_since:
            date_str = modified_since.strftime("%Y-%m-%dT%H:%M:%S")
            params["$filter"] = f"ModificationDate gt DateTime'{date_str}'"

        return self._paginated_get("/Products", params=params)

    def get_product_by_code(self, code: str) -> Optional[dict]:
        """Busca un producto por su código."""
        params = {"$filter": f"Code eq '{code}'"}
        response = self._request("GET", "/Products", params=params)

        if isinstance(response, list):
            products = response
        elif "value" in response:
            products = response["value"]
        else:
            products = []

        return products[0] if products else None

    # ========== MÉTODOS DE INVENTARIO ==========

    def get_inventory(self, warehouse_id: str = None) -> list[dict]:
        """
        Obtiene el inventario actual.

        Args:
            warehouse_id: ID del almacén (opcional, usa default de settings)

        Returns:
            Lista de items de inventario con existencias
        """
        warehouse_id = warehouse_id or settings.BIND_WAREHOUSE_ID

        params = {}
        if warehouse_id:
            params["$filter"] = f"WarehouseID eq '{warehouse_id}'"

        return self._paginated_get("/Inventory", params=params)

    def get_inventory_movements(
        self,
        warehouse_id: str = None,
        since: datetime = None,
    ) -> list[dict]:
        """
        Obtiene movimientos de inventario (entradas/salidas).

        Args:
            warehouse_id: ID del almacén
            since: Movimientos desde esta fecha
        """
        filters = []

        if warehouse_id:
            filters.append(f"WarehouseID eq '{warehouse_id}'")

        if since:
            date_str = since.strftime("%Y-%m-%dT%H:%M:%S")
            filters.append(f"Date gt DateTime'{date_str}'")

        params = {}
        if filters:
            params["$filter"] = " and ".join(filters)

        return self._paginated_get("/InventoryMovements", params=params)

    # ========== MÉTODOS DE CATÁLOGOS ==========

    def get_warehouses(self) -> list[dict]:
        """Obtiene lista de almacenes configurados."""
        return self._paginated_get("/Warehouses")

    def get_payment_methods(self) -> list[dict]:
        """Obtiene catálogo de métodos de pago SAT."""
        return self._paginated_get("/PaymentMethods")

    def get_payment_forms(self) -> list[dict]:
        """Obtiene catálogo de formas de pago SAT."""
        return self._paginated_get("/PaymentForms")

    def get_cfdi_uses(self) -> list[dict]:
        """Obtiene catálogo de usos de CFDI."""
        return self._paginated_get("/CFDIUses")

    # ========== HEALTH CHECK ==========

    def health_check(self) -> bool:
        """
        Verifica conectividad con la API de Bind.

        Returns:
            True si la conexión es exitosa
        """
        try:
            # Intentar obtener almacenes como prueba simple
            self._request("GET", "/Warehouses", params={"$top": 1})
            logger.info("Conexión a Bind ERP verificada correctamente")
            return True
        except BindAPIError as e:
            logger.error(f"Error de conectividad con Bind: {e}")
            return False
