"""
config.py - Configuración centralizada del middleware Smartsheet-Bind ERP.
Carga variables de entorno desde .env y define constantes del sistema.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    """Configuración del sistema cargada desde variables de entorno."""

    # ========== BIND ERP ==========
    BIND_API_BASE_URL: str = os.getenv("BIND_API_BASE_URL", "https://api.bind.com.mx/api")
    BIND_API_KEY: str = os.getenv("BIND_API_KEY", "")
    BIND_WAREHOUSE_ID: str = os.getenv("BIND_WAREHOUSE_ID", "")

    # Rate limiting config
    BIND_MAX_REQUESTS_PER_WINDOW: int = int(os.getenv("BIND_MAX_REQUESTS_PER_WINDOW", "300"))
    BIND_RATE_WINDOW_SECONDS: int = int(os.getenv("BIND_RATE_WINDOW_SECONDS", "300"))  # 5 minutos
    BIND_MAX_RETRIES: int = int(os.getenv("BIND_MAX_RETRIES", "5"))
    BIND_INITIAL_BACKOFF: float = float(os.getenv("BIND_INITIAL_BACKOFF", "1.0"))

    # ========== SMARTSHEET ==========
    SMARTSHEET_ACCESS_TOKEN: str = os.getenv("SMARTSHEET_ACCESS_TOKEN", "")
    SMARTSHEET_WEBHOOK_SECRET: str = os.getenv("SMARTSHEET_WEBHOOK_SECRET", "")

    # IDs de hojas de Smartsheet
    SMARTSHEET_INVOICES_SHEET_ID: int = int(os.getenv("SMARTSHEET_INVOICES_SHEET_ID", "0"))
    SMARTSHEET_INVENTORY_SHEET_ID: int = int(os.getenv("SMARTSHEET_INVENTORY_SHEET_ID", "0"))

    # ========== SERVIDOR ==========
    SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
    DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "false").lower() == "true"

    # ========== LOGGING ==========
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "middleware.log")

    # ========== SCHEDULER ==========
    SYNC_INVENTORY_INTERVAL_MINUTES: int = int(os.getenv("SYNC_INVENTORY_INTERVAL_MINUTES", "60"))

    @classmethod
    def validate(cls) -> list[str]:
        """
        Valida que las variables críticas estén configuradas.
        Retorna lista de errores encontrados.
        """
        errors = []

        if not cls.BIND_API_KEY:
            errors.append("BIND_API_KEY no está configurada")

        if not cls.SMARTSHEET_ACCESS_TOKEN:
            errors.append("SMARTSHEET_ACCESS_TOKEN no está configurado")

        if cls.SMARTSHEET_INVOICES_SHEET_ID == 0:
            errors.append("SMARTSHEET_INVOICES_SHEET_ID no está configurado")

        return errors


# Mapeo de columnas Smartsheet -> campos de factura Bind
SMARTSHEET_COLUMN_MAPPING = {
    # Columnas requeridas en Smartsheet
    "RFC": "rfc",
    "Razon Social": "razon_social",
    "Concepto": "concepto",
    "Descripcion": "descripcion",
    "Cantidad": "cantidad",
    "Precio Unitario": "precio_unitario",
    "Clave SAT Producto": "clave_sat_producto",
    "Clave SAT Unidad": "clave_sat_unidad",
    "Metodo Pago": "metodo_pago",          # PUE o PPD
    "Forma Pago": "forma_pago",            # 01, 03, etc.
    "Uso CFDI": "uso_cfdi",                # G01, G03, etc.
    "Regimen Fiscal": "regimen_fiscal",    # 601, 612, etc.
    "Codigo Postal": "codigo_postal",
    "Estado": "estado",                    # Columna de control: "Facturar" dispara webhook

    # Columnas de respuesta (escritas por el middleware)
    "UUID": "uuid",
    "Folio Fiscal": "folio_fiscal",
    "Fecha Facturacion": "fecha_facturacion",
    "Resultado": "resultado",              # "Exitoso" o mensaje de error
}

# Columnas mínimas requeridas para crear factura
REQUIRED_INVOICE_COLUMNS = [
    "RFC",
    "Concepto",
    "Cantidad",
    "Precio Unitario",
    "Clave SAT Producto",
    "Clave SAT Unidad",
    "Metodo Pago",
    "Forma Pago",
    "Uso CFDI",
]

# Instancia global de configuración
settings = Settings()
