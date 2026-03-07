"""
company_services.py - Factory para crear instancias de servicios por empresa.
Centraliza la creación de BindClient y SmartsheetService con config de Company.
"""

import logging
from typing import Optional

from bind_client import BindClient
from config import settings
from database import get_company, get_all_companies, Company

logger = logging.getLogger(__name__)


class CompanyNotFoundError(Exception):
    pass


class CompanyInactiveError(Exception):
    pass


def get_bind_client_for_company(company_id: str) -> BindClient:
    """Crea un BindClient configurado con las credenciales de una empresa.

    Args:
        company_id: ID/slug de la empresa (ej: "awalab")

    Returns:
        BindClient configurado para esa empresa

    Raises:
        CompanyNotFoundError: Si la empresa no existe
        CompanyInactiveError: Si la empresa está inactiva
    """
    company = get_company(company_id)
    if not company:
        raise CompanyNotFoundError(f"Empresa '{company_id}' no encontrada")
    if not company.is_active:
        raise CompanyInactiveError(f"Empresa '{company_id}' está inactiva")

    return BindClient(
        api_key=company.bind_api_key,
        base_url=company.bind_api_base_url,
    )


def get_workspace_id_for_company(company_id: str) -> Optional[int]:
    """Obtiene el workspace ID de Smartsheet para una empresa.

    Args:
        company_id: ID/slug de la empresa

    Returns:
        Workspace ID como int, o None si no está configurado
    """
    company = get_company(company_id)
    if not company:
        raise CompanyNotFoundError(f"Empresa '{company_id}' no encontrada")

    if company.smartsheet_workspace_id:
        return int(company.smartsheet_workspace_id)
    return None


def get_warehouse_id_for_company(company_id: str) -> Optional[str]:
    """Obtiene el warehouse ID de Bind para una empresa."""
    company = get_company(company_id)
    if not company:
        raise CompanyNotFoundError(f"Empresa '{company_id}' no encontrada")
    return company.bind_warehouse_id


def get_active_companies() -> list[Company]:
    """Retorna todas las empresas activas."""
    return get_all_companies(active_only=True)
