from __future__ import annotations

import pytest

from app.core.database_safety import DatabaseSafetyError
from scripts.verify_dev_seed import (
    DISPLAY_COUNTS,
    STATUS_RULES,
    DevSeedVerificationError,
    load_dev_target,
)


DEV_URL = "postgresql+psycopg://dev_user:FakePassword@localhost:5432/dlx_yuki_wms_dev"


def test_phase_e_accepts_only_exact_development_target() -> None:
    target, url = load_dev_target({"WMS_ENV": "development", "DATABASE_URL": DEV_URL})
    assert target.database == "dlx_yuki_wms_dev"
    assert url == DEV_URL


@pytest.mark.parametrize(
    ("environment", "database"),
    [
        ("development", "dlx_yuki_wms"),
        ("development", "dlx_yuki_wms_test"),
        ("test", "dlx_yuki_wms_test"),
        ("production", "dlx_yuki_wms_dev"),
    ],
)
def test_phase_e_refuses_every_non_dev_target(environment: str, database: str) -> None:
    url = f"postgresql+psycopg://user:FakePassword@localhost:5432/{database}"
    with pytest.raises((DatabaseSafetyError, DevSeedVerificationError)):
        load_dev_target({"WMS_ENV": environment, "DATABASE_URL": url})


@pytest.mark.parametrize("environ", [{}, {"WMS_ENV": "development"}, {"DATABASE_URL": DEV_URL}])
def test_phase_e_refuses_missing_process_configuration(environ: dict[str, str]) -> None:
    with pytest.raises(DatabaseSafetyError):
        load_dev_target(environ)


def test_phase_e_reports_all_required_business_counts() -> None:
    assert set(DISPLAY_COUNTS) == {
        "CUSTOMERS", "WAREHOUSES", "CARRIERS", "USERS", "LOCATIONS", "INBOUNDS",
        "INVENTORY_LOTS", "FBA_SHIPMENTS", "OUTBOUND_ORDERS", "PICKING_LISTS", "BOLS",
        "CONTAINER_TRACKINGS",
    }


def test_phase_e_has_explicit_status_allowlists() -> None:
    assert set(STATUS_RULES) == {
        ("inbound_records", "status"),
        ("inventory_lots", "status"),
        ("fba_shipments", "status"),
        ("outbound_orders", "status"),
        ("picking_lists", "status"),
        ("bols", "status"),
        ("container_trackings", "tracking_status"),
    }
    assert all(allowed for allowed in STATUS_RULES.values())
