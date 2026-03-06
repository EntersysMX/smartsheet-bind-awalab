"""
database.py - Base de datos SQLite para configuración multi-empresa.
Almacena empresas y la configuración de cada job/proceso del scheduler.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, DateTime, ForeignKey, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

logger = logging.getLogger(__name__)

CDMX_TZ = ZoneInfo("America/Mexico_City")

# Ruta de la base de datos
DB_PATH = Path(__file__).parent / "data" / "processes.db"
DB_PATH.parent.mkdir(exist_ok=True)

# Configuración de SQLAlchemy
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ========== MODELOS ==========

class Company(Base):
    """Modelo para empresas/tenants."""

    __tablename__ = "companies"

    id = Column(String(50), primary_key=True)  # slug: "awalab", "empresa2"
    name = Column(String(200), nullable=False)
    bind_api_key = Column(String(500), nullable=False)
    bind_api_base_url = Column(String(500), default="https://api.bind.com.mx/api")
    smartsheet_workspace_id = Column(String(100))
    bind_warehouse_id = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(CDMX_TZ))
    updated_at = Column(DateTime, default=lambda: datetime.now(CDMX_TZ), onupdate=lambda: datetime.now(CDMX_TZ))

    # Relación con ProcessConfig
    process_configs = relationship("ProcessConfig", back_populates="company")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "bind_api_base_url": self.bind_api_base_url,
            "smartsheet_workspace_id": self.smartsheet_workspace_id,
            "bind_warehouse_id": self.bind_warehouse_id,
            "is_active": self.is_active,
            "has_api_key": bool(self.bind_api_key),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ProcessConfig(Base):
    """Modelo para configuración de procesos/jobs."""

    __tablename__ = "process_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(100), unique=True, nullable=False, index=True)
    company_id = Column(String(50), ForeignKey("companies.id"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)

    # Configuración de Smartsheet
    smartsheet_sheet_id = Column(String(50))
    smartsheet_sheet_name = Column(String(200))

    # Configuración de ejecución
    interval_minutes = Column(Integer, default=60)
    is_active = Column(Boolean, default=True)

    # Horario de operación (hora en formato 24h, zona CDMX)
    operating_start_hour = Column(Integer, default=7)   # 7 AM
    operating_end_hour = Column(Integer, default=20)    # 8 PM

    # Metadatos del proceso
    source_system = Column(String(50))  # "bind" o "smartsheet"
    target_system = Column(String(50))  # "bind" o "smartsheet"
    sync_direction = Column(String(20))  # "push", "pull", "bidirectional"

    # Campos que maneja el proceso (JSON)
    fields_mapping = Column(Text)  # JSON con mapeo de campos

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(CDMX_TZ))
    updated_at = Column(DateTime, default=lambda: datetime.now(CDMX_TZ), onupdate=lambda: datetime.now(CDMX_TZ))

    # Relación con Company
    company = relationship("Company", back_populates="process_configs")

    def to_dict(self) -> dict:
        """Convierte el modelo a diccionario."""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "company_id": self.company_id,
            "name": self.name,
            "description": self.description,
            "smartsheet_sheet_id": self.smartsheet_sheet_id,
            "smartsheet_sheet_name": self.smartsheet_sheet_name,
            "interval_minutes": self.interval_minutes,
            "is_active": self.is_active,
            "operating_start_hour": self.operating_start_hour or 7,
            "operating_end_hour": self.operating_end_hour or 20,
            "source_system": self.source_system,
            "target_system": self.target_system,
            "sync_direction": self.sync_direction,
            "fields_mapping": json.loads(self.fields_mapping) if self.fields_mapping else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ========== INIT & MIGRATION ==========

def init_db():
    """Inicializa la base de datos, crea tablas nuevas y migra columnas faltantes."""
    Base.metadata.create_all(bind=engine)
    logger.info(f"Base de datos inicializada en: {DB_PATH}")

    # Migrar: agregar company_id a process_configs si no existe
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns("process_configs")]
    if "company_id" not in columns:
        with engine.connect() as conn:
            conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE process_configs ADD COLUMN company_id VARCHAR(50) REFERENCES companies(id)"
                )
            )
            conn.commit()
        logger.info("Columna company_id agregada a process_configs")


def migrate_existing_to_company(company_id: str):
    """Migra ProcessConfigs existentes sin company_id a una empresa específica."""
    db = SessionLocal()
    try:
        orphans = db.query(ProcessConfig).filter(
            (ProcessConfig.company_id == None) | (ProcessConfig.company_id == "")
        ).all()
        for config in orphans:
            config.company_id = company_id
            config.updated_at = datetime.now(CDMX_TZ)
        if orphans:
            db.commit()
            logger.info(f"Migrados {len(orphans)} ProcessConfigs a empresa '{company_id}'")
    finally:
        db.close()


# ========== COMPANY CRUD ==========

def get_company(company_id: str) -> Optional[Company]:
    db = SessionLocal()
    try:
        return db.query(Company).filter(Company.id == company_id).first()
    finally:
        db.close()


def get_all_companies(active_only: bool = False) -> list[Company]:
    db = SessionLocal()
    try:
        q = db.query(Company)
        if active_only:
            q = q.filter(Company.is_active == True)
        return q.all()
    finally:
        db.close()


def create_or_update_company(
    company_id: str,
    name: str,
    bind_api_key: str,
    bind_api_base_url: str = "https://api.bind.com.mx/api",
    smartsheet_workspace_id: str = None,
    bind_warehouse_id: str = None,
    is_active: bool = True,
) -> Company:
    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if company:
            company.name = name
            company.bind_api_key = bind_api_key
            company.bind_api_base_url = bind_api_base_url
            company.smartsheet_workspace_id = smartsheet_workspace_id
            company.bind_warehouse_id = bind_warehouse_id
            company.is_active = is_active
            company.updated_at = datetime.now(CDMX_TZ)
        else:
            company = Company(
                id=company_id,
                name=name,
                bind_api_key=bind_api_key,
                bind_api_base_url=bind_api_base_url,
                smartsheet_workspace_id=smartsheet_workspace_id,
                bind_warehouse_id=bind_warehouse_id,
                is_active=is_active,
            )
            db.add(company)
        db.commit()
        db.refresh(company)
        return company
    finally:
        db.close()


def delete_company(company_id: str) -> bool:
    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if company:
            company.is_active = False
            company.updated_at = datetime.now(CDMX_TZ)
            db.commit()
            return True
        return False
    finally:
        db.close()


# ========== PROCESS CONFIG CRUD ==========

def get_db():
    """Obtiene una sesión de base de datos."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_process_config(job_id: str) -> Optional[ProcessConfig]:
    """Obtiene la configuración de un proceso por su job_id."""
    db = SessionLocal()
    try:
        return db.query(ProcessConfig).filter(ProcessConfig.job_id == job_id).first()
    finally:
        db.close()


def get_all_process_configs(company_id: str = None) -> list[ProcessConfig]:
    """Obtiene configuraciones de procesos, opcionalmente filtradas por empresa."""
    db = SessionLocal()
    try:
        q = db.query(ProcessConfig)
        if company_id:
            q = q.filter(ProcessConfig.company_id == company_id)
        return q.all()
    finally:
        db.close()


def create_or_update_process_config(
    job_id: str,
    name: str,
    company_id: str = None,
    description: str = None,
    smartsheet_sheet_id: str = None,
    smartsheet_sheet_name: str = None,
    interval_minutes: int = 60,
    is_active: bool = True,
    operating_start_hour: int = 7,
    operating_end_hour: int = 20,
    source_system: str = None,
    target_system: str = None,
    sync_direction: str = None,
    fields_mapping: dict = None,
) -> ProcessConfig:
    """Crea o actualiza la configuración de un proceso."""
    db = SessionLocal()
    try:
        config = db.query(ProcessConfig).filter(ProcessConfig.job_id == job_id).first()

        if config:
            # Actualizar existente
            config.name = name
            if company_id is not None:
                config.company_id = company_id
            config.description = description
            config.smartsheet_sheet_id = smartsheet_sheet_id
            config.smartsheet_sheet_name = smartsheet_sheet_name
            config.interval_minutes = interval_minutes
            config.is_active = is_active
            config.operating_start_hour = operating_start_hour
            config.operating_end_hour = operating_end_hour
            config.source_system = source_system
            config.target_system = target_system
            config.sync_direction = sync_direction
            config.fields_mapping = json.dumps(fields_mapping) if fields_mapping else None
            config.updated_at = datetime.now(CDMX_TZ)
        else:
            # Crear nuevo
            config = ProcessConfig(
                job_id=job_id,
                company_id=company_id,
                name=name,
                description=description,
                smartsheet_sheet_id=smartsheet_sheet_id,
                smartsheet_sheet_name=smartsheet_sheet_name,
                interval_minutes=interval_minutes,
                is_active=is_active,
                operating_start_hour=operating_start_hour,
                operating_end_hour=operating_end_hour,
                source_system=source_system,
                target_system=target_system,
                sync_direction=sync_direction,
                fields_mapping=json.dumps(fields_mapping) if fields_mapping else None,
            )
            db.add(config)

        db.commit()
        db.refresh(config)
        return config
    finally:
        db.close()


def delete_process_config(job_id: str) -> bool:
    """Elimina la configuración de un proceso."""
    db = SessionLocal()
    try:
        config = db.query(ProcessConfig).filter(ProcessConfig.job_id == job_id).first()
        if config:
            db.delete(config)
            db.commit()
            return True
        return False
    finally:
        db.close()


# ========== SEED ==========

def seed_default_configs():
    """Crea las configuraciones por defecto solo si no existen.

    IMPORTANTE: Esta función NO sobrescribe configuraciones existentes
    para preservar cambios hechos por el usuario (intervalos, horarios, etc.)
    """
    from config import settings

    # Crear empresa AWALab si no existe
    if not get_company("awalab"):
        create_or_update_company(
            company_id="awalab",
            name="AWALab de México",
            bind_api_key=settings.BIND_API_KEY,
            bind_api_base_url=settings.BIND_API_BASE_URL,
            smartsheet_workspace_id="75095659046788",
            bind_warehouse_id=settings.BIND_WAREHOUSE_ID,
            is_active=True,
        )
        logger.info("Empresa AWALab creada")

    # Migrar configs existentes sin company_id
    migrate_existing_to_company("awalab")

    db = SessionLocal()
    try:
        # Proceso de sincronización de inventario - solo crear si no existe
        existing_inventory = db.query(ProcessConfig).filter(ProcessConfig.job_id == "sync_inventory").first()
        if not existing_inventory:
            create_or_update_process_config(
                job_id="sync_inventory",
                company_id="awalab",
                name="Sincronización de Inventario",
                description="Sincroniza el inventario desde Bind ERP hacia Smartsheet. Obtiene productos con existencias del almacén configurado y actualiza la hoja de inventario.",
                smartsheet_sheet_id="346190987087748",
                smartsheet_sheet_name="Registros Inventario Bind - Awalab",
                interval_minutes=settings.SYNC_INVENTORY_INTERVAL_MINUTES,
                is_active=True,
                source_system="bind",
                target_system="smartsheet",
                sync_direction="pull",
                fields_mapping={
                    "bind_fields": ["ProductID", "ProductCode", "ProductName", "Stock", "WarehouseID"],
                    "smartsheet_columns": ["ID Producto", "Código", "Nombre", "Existencias", "Almacén"],
                },
            )
            logger.info("Configuración de inventario creada")
        else:
            logger.info("Configuración de inventario existente preservada")

        # Proceso de sincronización de facturas - solo crear si no existe
        existing_invoices = db.query(ProcessConfig).filter(ProcessConfig.job_id == "sync_invoices").first()
        if not existing_invoices:
            create_or_update_process_config(
                job_id="sync_invoices",
                company_id="awalab",
                name="Sincronización de Facturas Bind -> Smartsheet",
                description="Sincroniza facturas creadas en Bind ERP hacia Smartsheet. Obtiene facturas de los últimos 10 minutos y realiza UPSERT (actualiza existentes por UUID o inserta nuevas).",
                smartsheet_sheet_id="4956740131966852",
                smartsheet_sheet_name="Registros Facturas Bind - Awalab",
                interval_minutes=settings.SYNC_INVOICES_INTERVAL_MINUTES,
                is_active=True,
                source_system="bind",
                target_system="smartsheet",
                sync_direction="pull",
                fields_mapping={
                    "bind_fields": ["UUID", "Folio", "Date", "ClientRFC", "ClientName", "Total", "Status"],
                    "smartsheet_columns": ["UUID", "Folio", "Fecha", "RFC Cliente", "Nombre Cliente", "Total", "Estado"],
                },
            )
            logger.info("Configuración de facturas creada")
        else:
            logger.info("Configuración de facturas existente preservada")

        # Procesos de sincronización de catálogos Bind - cada 2 horas (120 min)
        catalog_configs = [
            ("sync_catalog_warehouses", "Sync Catálogo - Almacenes", "Sincroniza almacenes desde Bind ERP"),
            ("sync_catalog_clients", "Sync Catálogo - Clientes", "Sincroniza clientes desde Bind ERP"),
            ("sync_catalog_products", "Sync Catálogo - Productos", "Sincroniza productos desde Bind ERP"),
            ("sync_catalog_providers", "Sync Catálogo - Proveedores", "Sincroniza proveedores desde Bind ERP"),
            ("sync_catalog_users", "Sync Catálogo - Usuarios", "Sincroniza usuarios desde Bind ERP"),
            ("sync_catalog_currencies", "Sync Catálogo - Monedas", "Sincroniza monedas y tipos de cambio"),
            ("sync_catalog_pricelists", "Sync Catálogo - Listas de Precios", "Sincroniza listas de precios"),
            ("sync_catalog_bankaccounts", "Sync Catálogo - Cuentas Bancarias", "Sincroniza cuentas bancarias"),
            ("sync_catalog_banks", "Sync Catálogo - Bancos", "Sincroniza catálogo de bancos"),
            ("sync_catalog_locations", "Sync Catálogo - Ubicaciones", "Sincroniza ubicaciones/sucursales"),
            ("sync_catalog_orders", "Sync Catálogo - Pedidos", "Sincroniza pedidos de venta"),
            ("sync_catalog_quotes", "Sync Catálogo - Cotizaciones", "Sincroniza cotizaciones"),
            ("sync_catalog_categories", "Sync Catálogo - Categorías", "Sincroniza categorías de productos"),
            ("sync_catalog_accounts", "Sync Catálogo - Cuentas Contables", "Sincroniza cuentas contables"),
            ("sync_catalog_account_categories", "Sync Catálogo - Catálogo Cuentas SAT", "Sincroniza catálogo de cuentas SAT"),
            ("sync_catalog_accounting_journals", "Sync Catálogo - Pólizas Contables", "Sincroniza pólizas contables"),
            ("sync_catalog_invoices", "Sync Catálogo - Facturas", "Sincroniza facturas emitidas"),
        ]

        for job_id, name, description in catalog_configs:
            existing = db.query(ProcessConfig).filter(ProcessConfig.job_id == job_id).first()
            if not existing:
                create_or_update_process_config(
                    job_id=job_id,
                    company_id="awalab",
                    name=name,
                    description=description,
                    interval_minutes=120,  # Cada 2 horas
                    is_active=True,
                    operating_start_hour=6,
                    operating_end_hour=22,
                    source_system="bind",
                    target_system="smartsheet",
                    sync_direction="pull",
                )
                logger.info(f"Configuración de {job_id} creada")
    finally:
        db.close()


def seed_company_default_configs(company_id: str):
    """Crea los ProcessConfigs default para una empresa nueva."""
    company = get_company(company_id)
    if not company:
        raise ValueError(f"Empresa '{company_id}' no existe")

    catalog_configs = [
        ("sync_invoices", "Sincronización de Facturas Bind -> Smartsheet", 10),
        ("sync_inventory", "Sincronización de Inventario", 60),
        ("sync_catalog_warehouses", "Sync Catálogo - Almacenes", 120),
        ("sync_catalog_clients", "Sync Catálogo - Clientes", 120),
        ("sync_catalog_products", "Sync Catálogo - Productos", 120),
        ("sync_catalog_providers", "Sync Catálogo - Proveedores", 120),
        ("sync_catalog_users", "Sync Catálogo - Usuarios", 120),
        ("sync_catalog_currencies", "Sync Catálogo - Monedas", 120),
        ("sync_catalog_pricelists", "Sync Catálogo - Listas de Precios", 120),
        ("sync_catalog_bankaccounts", "Sync Catálogo - Cuentas Bancarias", 120),
        ("sync_catalog_banks", "Sync Catálogo - Bancos", 120),
        ("sync_catalog_locations", "Sync Catálogo - Ubicaciones", 120),
        ("sync_catalog_orders", "Sync Catálogo - Pedidos", 120),
        ("sync_catalog_quotes", "Sync Catálogo - Cotizaciones", 120),
        ("sync_catalog_categories", "Sync Catálogo - Categorías", 120),
        ("sync_catalog_accounts", "Sync Catálogo - Cuentas Contables", 120),
        ("sync_catalog_account_categories", "Sync Catálogo - Catálogo Cuentas SAT", 120),
        ("sync_catalog_accounting_journals", "Sync Catálogo - Pólizas Contables", 120),
        ("sync_catalog_invoices", "Sync Catálogo - Facturas", 120),
    ]

    created = 0
    for base_job_id, name, interval in catalog_configs:
        full_job_id = f"{company_id}__{base_job_id}"
        if not get_process_config(full_job_id):
            create_or_update_process_config(
                job_id=full_job_id,
                company_id=company_id,
                name=f"[{company.name}] {name}",
                description=f"{name} para {company.name}",
                interval_minutes=interval,
                is_active=False,  # Inactivo por default, el admin los activa
                operating_start_hour=7,
                operating_end_hour=20,
                source_system="bind",
                target_system="smartsheet",
                sync_direction="pull",
            )
            created += 1

    logger.info(f"Creados {created} ProcessConfigs para empresa '{company_id}'")
    return created
