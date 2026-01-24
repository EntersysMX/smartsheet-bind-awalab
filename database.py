"""
database.py - Base de datos SQLite para configuración de procesos.
Almacena la configuración de cada job/proceso del scheduler.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

CDMX_TZ = ZoneInfo("America/Mexico_City")

# Ruta de la base de datos
DB_PATH = Path(__file__).parent / "data" / "processes.db"
DB_PATH.parent.mkdir(exist_ok=True)

# Configuración de SQLAlchemy
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ProcessConfig(Base):
    """Modelo para configuración de procesos/jobs."""

    __tablename__ = "process_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(50), unique=True, nullable=False, index=True)
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

    def to_dict(self) -> dict:
        """Convierte el modelo a diccionario."""
        return {
            "id": self.id,
            "job_id": self.job_id,
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


def init_db():
    """Inicializa la base de datos y crea las tablas."""
    Base.metadata.create_all(bind=engine)
    logger.info(f"Base de datos inicializada en: {DB_PATH}")


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


def get_all_process_configs() -> list[ProcessConfig]:
    """Obtiene todas las configuraciones de procesos."""
    db = SessionLocal()
    try:
        return db.query(ProcessConfig).all()
    finally:
        db.close()


def create_or_update_process_config(
    job_id: str,
    name: str,
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


def seed_default_configs():
    """Crea las configuraciones por defecto solo si no existen.

    IMPORTANTE: Esta función NO sobrescribe configuraciones existentes
    para preservar cambios hechos por el usuario (intervalos, horarios, etc.)
    """
    from config import settings

    db = SessionLocal()
    try:
        # Proceso de sincronización de inventario - solo crear si no existe
        existing_inventory = db.query(ProcessConfig).filter(ProcessConfig.job_id == "sync_inventory").first()
        if not existing_inventory:
            create_or_update_process_config(
                job_id="sync_inventory",
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
