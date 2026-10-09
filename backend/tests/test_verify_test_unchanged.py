from __future__ import annotations

import pytest

from app.core.database_safety import DatabaseSafetyError
from scripts.verify_test_unchanged import (
    DatabaseUnchangedError,
    expected_baseline_counts,
    load_test_target,
)


TEST_URL = "postgresql+psycopg://test_user:FakePassword@localhost:5432/dlx_yuki_wms_test"


def test_phase_f_accepts_only_exact_test_target() -> None:
    target, url = load_test_target({"WMS_ENV": "test", "DATABASE_URL": TEST_URL})
    assert target.database == "dlx_yuki_wms_test"
    assert url == TEST_URL


@pytest.mark.parametrize(
    ("environment", "database"),
    [
        ("test", "dlx_yuki_wms"),
        ("test", "dlx_yuki_wms_dev"),
        ("development", "dlx_yuki_wms_dev"),
        ("production", "dlx_yuki_wms_test"),
    ],
)
def test_phase_f_refuses_every_non_test_target(environment: str, database: str) -> None:
    url = f"postgresql+psycopg://user:FakePassword@localhost:5432/{database}"
    with pytest.raises((DatabaseSafetyError, DatabaseUnchangedError)):
        load_test_target({"WMS_ENV": environment, "DATABASE_URL": url})


@pytest.mark.parametrize("environ", [{}, {"WMS_ENV": "test"}, {"DATABASE_URL": TEST_URL}])
def test_phase_f_refuses_missing_process_configuration(environ: dict[str, str]) -> None:
    with pytest.raises(DatabaseSafetyError):
        load_test_target(environ)


def test_phase_f_expected_baseline_has_only_approved_rows() -> None:
    counts = expected_baseline_counts()
    assert counts["company_profiles"] == 1
    assert counts["inventory_priority_rules"] == 4
    assert all(
        count == 0
        for table_name, count in counts.items()
        if table_name not in {"company_profiles", "inventory_priority_rules"}
    )
