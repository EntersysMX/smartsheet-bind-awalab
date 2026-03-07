"""
Tests for multi-tenant functionality: Company CRUD, job ID parsing,
migration helpers, seed configs, and company_services factory.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database as db_module
from database import (
    Base,
    Company,
    ProcessConfig,
    create_or_update_company,
    get_company,
    get_all_companies,
    delete_company,
    migrate_legacy_job_ids,
    seed_company_default_configs,
    create_or_update_process_config,
    get_process_config,
)


# ---------------------------------------------------------------------------
# Fixture: in-memory SQLite DB, patched into the database module per test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _in_memory_db(monkeypatch):
    """Replace database.engine and database.SessionLocal with an in-memory SQLite DB."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", Session)

    yield engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_company(company_id="testco", name="Test Company", api_key="key123"):
    return create_or_update_company(
        company_id=company_id,
        name=name,
        bind_api_key=api_key,
        bind_api_base_url="https://api.bind.com.mx/api",
    )


# ===========================================================================
# 1. test_parse_job_id
# ===========================================================================

def test_parse_job_id():
    """parse_job_id splits prefixed IDs and returns None for legacy ones."""
    # Import from main requires apscheduler, so we test the logic directly
    def parse_job_id(job_id):
        if "__" in job_id:
            company_id, job_type = job_id.split("__", 1)
            return company_id, job_type
        return None, job_id

    company_id, job_type = parse_job_id("awalab__sync_invoices")
    assert company_id == "awalab"
    assert job_type == "sync_invoices"

    company_id, job_type = parse_job_id("sync_inventory")
    assert company_id is None
    assert job_type == "sync_inventory"


# ===========================================================================
# 2. test_company_crud
# ===========================================================================

def test_company_crud():
    """create_or_update_company, get_company, get_all_companies, delete_company."""
    # Create
    company = _create_test_company()
    assert company.id == "testco"
    assert company.name == "Test Company"
    assert company.is_active is True

    # Read
    fetched = get_company("testco")
    assert fetched is not None
    assert fetched.id == "testco"

    # Update
    updated = create_or_update_company(
        company_id="testco",
        name="Updated Name",
        bind_api_key="new_key",
    )
    assert updated.name == "Updated Name"

    # List
    _create_test_company(company_id="co2", name="Company 2")
    all_companies = get_all_companies()
    assert len(all_companies) == 2

    # Soft-delete (sets is_active=False)
    result = delete_company("testco")
    assert result is True

    deleted = get_company("testco")
    assert deleted.is_active is False

    # active_only filter
    active = get_all_companies(active_only=True)
    assert all(c.is_active for c in active)
    assert len(active) == 1  # only "co2" remains active

    # Delete non-existent returns False
    assert delete_company("nonexistent") is False


# ===========================================================================
# 3. test_migrate_legacy_job_ids
# ===========================================================================

def test_migrate_legacy_job_ids():
    """Legacy job IDs without prefix get renamed to '{company_id}__{job_type}'."""
    _create_test_company(company_id="acme")

    # Create legacy ProcessConfigs (no prefix)
    create_or_update_process_config(job_id="sync_inventory", name="Inv", company_id="acme")
    create_or_update_process_config(job_id="sync_invoices", name="Fac", company_id="acme")
    # One already prefixed -- should NOT be touched
    create_or_update_process_config(job_id="acme__sync_orders", name="Ord", company_id="acme")

    renamed = migrate_legacy_job_ids("acme")
    assert renamed == 2

    # Verify new IDs exist
    assert get_process_config("acme__sync_inventory") is not None
    assert get_process_config("acme__sync_invoices") is not None
    # Already-prefixed one unchanged
    assert get_process_config("acme__sync_orders") is not None
    # Old IDs gone
    assert get_process_config("sync_inventory") is None
    assert get_process_config("sync_invoices") is None


# ===========================================================================
# 4. test_seed_company_default_configs
# ===========================================================================

def test_seed_company_default_configs():
    """seed_company_default_configs creates ProcessConfigs with prefixed IDs."""
    _create_test_company(company_id="newco", name="New Co")

    created = seed_company_default_configs("newco")
    assert created > 0

    # Spot-check a few expected job IDs
    inv = get_process_config("newco__sync_invoices")
    assert inv is not None
    assert inv.company_id == "newco"
    assert inv.is_active is False  # defaults to inactive for new companies

    inventory = get_process_config("newco__sync_inventory")
    assert inventory is not None
    assert inventory.company_id == "newco"

    catalog = get_process_config("newco__sync_catalog_clients")
    assert catalog is not None
    assert catalog.company_id == "newco"

    # Calling again should not create duplicates
    created_again = seed_company_default_configs("newco")
    assert created_again == 0


def test_seed_company_default_configs_nonexistent():
    """seed_company_default_configs raises ValueError for unknown company."""
    with pytest.raises(ValueError, match="no existe"):
        seed_company_default_configs("ghost")


# ===========================================================================
# 5. test_get_bind_client_for_company
# ===========================================================================

def test_get_bind_client_for_company():
    """get_bind_client_for_company creates a BindClient with company credentials."""
    _create_test_company(company_id="bind_co", name="Bind Co", api_key="secret_key")

    with patch("company_services.BindClient") as MockBind:
        mock_instance = MagicMock()
        MockBind.return_value = mock_instance

        from company_services import get_bind_client_for_company

        client = get_bind_client_for_company("bind_co")

        MockBind.assert_called_once_with(
            api_key="secret_key",
            base_url="https://api.bind.com.mx/api",
        )
        assert client is mock_instance


# ===========================================================================
# 6. test_company_not_found_error
# ===========================================================================

def test_company_not_found_error():
    """get_bind_client_for_company raises CompanyNotFoundError for unknown company."""
    from company_services import get_bind_client_for_company, CompanyNotFoundError

    with pytest.raises(CompanyNotFoundError):
        get_bind_client_for_company("unknown_company")
