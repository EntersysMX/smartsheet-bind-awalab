"""
smartsheet_service.py - Wrapper del SDK oficial de Smartsheet.
Proporciona métodos simplificados para interactuar con hojas de Smartsheet.
"""

import logging
from datetime import datetime
from typing import Any, Optional

import pandas as pd
import smartsheet
from smartsheet.models import Cell, Row, Comment

from config import settings

logger = logging.getLogger(__name__)


class SmartsheetServiceError(Exception):
    """Excepción personalizada para errores del servicio Smartsheet."""
    pass


class SmartsheetService:
    """
    Servicio wrapper para el SDK de Smartsheet.

    Proporciona métodos de alto nivel para:
    - Leer hojas como DataFrames
    - Actualizar filas
    - Agregar comentarios
    - Verificar webhooks
    """

    def __init__(self, access_token: str = None):
        """
        Inicializa el servicio de Smartsheet.

        Args:
            access_token: Token de acceso. Si no se proporciona, usa settings.
        """
        self.access_token = access_token or settings.SMARTSHEET_ACCESS_TOKEN

        if not self.access_token:
            raise ValueError("SMARTSHEET_ACCESS_TOKEN es requerido")

        self.client = smartsheet.Smartsheet(self.access_token)
        self.client.errors_as_exceptions(True)

        # Cache de mapeo columna_nombre -> columna_id por hoja
        self._column_cache: dict[int, dict[str, int]] = {}

    def _get_column_map(self, sheet_id: int) -> dict[str, int]:
        """
        Obtiene el mapeo de nombres de columna a IDs para una hoja.
        Usa cache para evitar llamadas repetidas.

        Args:
            sheet_id: ID de la hoja

        Returns:
            Dict {nombre_columna: columna_id}
        """
        if sheet_id not in self._column_cache:
            sheet = self.client.Sheets.get_sheet(sheet_id, page_size=1)
            self._column_cache[sheet_id] = {
                col.title: col.id for col in sheet.columns
            }
            logger.debug(f"Cache de columnas actualizado para hoja {sheet_id}")

        return self._column_cache[sheet_id]

    def _get_column_id(self, sheet_id: int, column_name: str) -> int:
        """
        Obtiene el ID de una columna por su nombre.

        Args:
            sheet_id: ID de la hoja
            column_name: Nombre de la columna

        Returns:
            ID de la columna

        Raises:
            SmartsheetServiceError: Si la columna no existe
        """
        column_map = self._get_column_map(sheet_id)

        if column_name not in column_map:
            raise SmartsheetServiceError(
                f"Columna '{column_name}' no encontrada en hoja {sheet_id}. "
                f"Columnas disponibles: {list(column_map.keys())}"
            )

        return column_map[column_name]

    def get_sheet_as_dataframe(self, sheet_id: int) -> pd.DataFrame:
        """
        Descarga una hoja completa y la convierte a pandas DataFrame.

        Args:
            sheet_id: ID de la hoja de Smartsheet

        Returns:
            DataFrame con los datos de la hoja. Incluye columna 'row_id' con IDs de filas.
        """
        logger.info(f"Descargando hoja {sheet_id} como DataFrame...")

        try:
            sheet = self.client.Sheets.get_sheet(sheet_id)
        except smartsheet.exceptions.ApiError as e:
            logger.error(f"Error al obtener hoja {sheet_id}: {e}")
            raise SmartsheetServiceError(f"Error al obtener hoja: {e}")

        # Crear mapeo de columna_id -> nombre
        column_id_to_name = {col.id: col.title for col in sheet.columns}

        # Extraer datos de filas
        rows_data = []
        for row in sheet.rows:
            row_dict = {"row_id": row.id}

            for cell in row.cells:
                col_name = column_id_to_name.get(cell.column_id, f"col_{cell.column_id}")
                row_dict[col_name] = cell.value

            rows_data.append(row_dict)

        df = pd.DataFrame(rows_data)
        logger.info(f"DataFrame creado con {len(df)} filas y {len(df.columns)} columnas")

        return df

    def get_row(self, sheet_id: int, row_id: int) -> dict[str, Any]:
        """
        Obtiene una fila específica como diccionario.

        Args:
            sheet_id: ID de la hoja
            row_id: ID de la fila

        Returns:
            Dict con los valores de la fila {nombre_columna: valor}
        """
        logger.debug(f"Obteniendo fila {row_id} de hoja {sheet_id}")

        try:
            row = self.client.Sheets.get_row(sheet_id, row_id)
        except smartsheet.exceptions.ApiError as e:
            logger.error(f"Error al obtener fila {row_id}: {e}")
            raise SmartsheetServiceError(f"Error al obtener fila: {e}")

        column_map = self._get_column_map(sheet_id)
        column_id_to_name = {v: k for k, v in column_map.items()}

        row_data = {"row_id": row.id}
        for cell in row.cells:
            col_name = column_id_to_name.get(cell.column_id, f"col_{cell.column_id}")
            row_data[col_name] = cell.value

        return row_data

    def update_row_cells(
        self,
        sheet_id: int,
        row_id: int,
        updates: dict[str, Any],
    ) -> bool:
        """
        Actualiza múltiples celdas de una fila.

        Args:
            sheet_id: ID de la hoja
            row_id: ID de la fila
            updates: Dict {nombre_columna: nuevo_valor}

        Returns:
            True si la actualización fue exitosa
        """
        logger.info(f"Actualizando fila {row_id} con {len(updates)} campos")

        column_map = self._get_column_map(sheet_id)

        # Construir lista de celdas a actualizar
        cells = []
        for col_name, value in updates.items():
            if col_name not in column_map:
                logger.warning(f"Columna '{col_name}' no existe, ignorando")
                continue

            cell = Cell()
            cell.column_id = column_map[col_name]
            cell.value = value
            cells.append(cell)

        if not cells:
            logger.warning("No hay celdas válidas para actualizar")
            return False

        # Crear objeto Row para actualización
        row = Row()
        row.id = row_id
        row.cells = cells

        try:
            self.client.Sheets.update_rows(sheet_id, [row])
            logger.info(f"Fila {row_id} actualizada exitosamente")
            return True
        except smartsheet.exceptions.ApiError as e:
            logger.error(f"Error al actualizar fila {row_id}: {e}")
            raise SmartsheetServiceError(f"Error al actualizar fila: {e}")

    def update_row_status(
        self,
        sheet_id: int,
        row_id: int,
        message: str,
        status_column: str = "Resultado",
    ) -> bool:
        """
        Actualiza la columna de estado/resultado de una fila.

        Args:
            sheet_id: ID de la hoja
            row_id: ID de la fila
            message: Mensaje de estado
            status_column: Nombre de la columna de estado

        Returns:
            True si fue exitoso
        """
        return self.update_row_cells(sheet_id, row_id, {status_column: message})

    def add_row_comment(self, sheet_id: int, row_id: int, text: str) -> bool:
        """
        Agrega un comentario a una fila.

        Args:
            sheet_id: ID de la hoja
            row_id: ID de la fila
            text: Texto del comentario

        Returns:
            True si fue exitoso
        """
        logger.info(f"Agregando comentario a fila {row_id}")

        comment = Comment()
        comment.text = text

        try:
            self.client.Discussions.create_discussion_on_row(
                sheet_id,
                row_id,
                self.client.models.Discussion({"comment": comment}),
            )
            return True
        except smartsheet.exceptions.ApiError as e:
            logger.error(f"Error al agregar comentario: {e}")
            return False

    def update_invoice_result(
        self,
        sheet_id: int,
        row_id: int,
        uuid: str = None,
        folio: str = None,
        error_message: str = None,
    ) -> bool:
        """
        Actualiza el resultado de facturación en una fila.

        Args:
            sheet_id: ID de la hoja
            row_id: ID de la fila
            uuid: UUID de la factura (si fue exitosa)
            folio: Folio fiscal (si fue exitosa)
            error_message: Mensaje de error (si falló)

        Returns:
            True si fue exitoso
        """
        updates = {}

        if uuid:
            updates["UUID"] = uuid
            updates["Folio Fiscal"] = folio or ""
            updates["Fecha Facturacion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            updates["Resultado"] = "Exitoso"
            updates["Estado"] = "Facturado"
        else:
            updates["Resultado"] = f"Error: {error_message}"[:500] if error_message else "Error"
            updates["Estado"] = "Error"

        return self.update_row_cells(sheet_id, row_id, updates)

    def get_rows_by_status(
        self,
        sheet_id: int,
        status_value: str,
        status_column: str = "Estado",
    ) -> list[dict[str, Any]]:
        """
        Obtiene todas las filas con un estado específico.

        Args:
            sheet_id: ID de la hoja
            status_value: Valor de estado a filtrar
            status_column: Nombre de la columna de estado

        Returns:
            Lista de filas como diccionarios
        """
        df = self.get_sheet_as_dataframe(sheet_id)

        if status_column not in df.columns:
            logger.warning(f"Columna '{status_column}' no encontrada")
            return []

        filtered = df[df[status_column] == status_value]
        return filtered.to_dict("records")

    def verify_webhook_signature(self, webhook_secret: str, signature: str, body: bytes) -> bool:
        """
        Verifica la firma de un webhook de Smartsheet.

        Args:
            webhook_secret: Secreto del webhook
            signature: Firma recibida en header Smartsheet-Hmac-SHA256
            body: Cuerpo crudo de la petición

        Returns:
            True si la firma es válida
        """
        import hmac
        import hashlib
        import base64

        if not webhook_secret or not signature:
            return False

        expected = hmac.new(
            webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).digest()

        expected_b64 = base64.b64encode(expected).decode("utf-8")

        return hmac.compare_digest(expected_b64, signature)

    def clear_column_cache(self, sheet_id: int = None):
        """
        Limpia el cache de columnas.

        Args:
            sheet_id: ID específico o None para limpiar todo
        """
        if sheet_id:
            self._column_cache.pop(sheet_id, None)
        else:
            self._column_cache.clear()

    def health_check(self) -> bool:
        """
        Verifica conectividad con Smartsheet.

        Returns:
            True si la conexión es exitosa
        """
        try:
            self.client.Users.get_current_user()
            logger.info("Conexión a Smartsheet verificada correctamente")
            return True
        except Exception as e:
            logger.error(f"Error de conectividad con Smartsheet: {e}")
            return False
