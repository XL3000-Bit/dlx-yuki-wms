from __future__ import annotations

import inspect

import pytest
from sqlalchemy.exc import OperationalError

from app.core.database_safety import DatabaseSafetyError
from scripts.seed_dev import (
    DATES,
    DevSeedDatabaseError,
    DevSeedError,
    expected_counts,
    load_dev_target,
    run,
    safe_failure,
)


DEV_URL = "postgresql+psycopg://dev_user:FakePassword@localhost:5432/dlx_yuki_wms_dev"


def test_dev_seed_accepts_only_exact_development_target() -> None:
    target, url, password = load_dev_target(
        {
            "WMS_ENV": "development",
            "DATABASE_URL": DEV_URL,
            "DEV_SEED_USER_PASSWORD": "FakePasswordOnly",
        }
    )

    assert target.database == "dlx_yuki_wms_dev"
    assert url == DEV_URL
    assert password == "FakePasswordOnly"


@pytest.mark.parametrize(
    ("environment", "database"),
    [
        ("development", "dlx_yuki_wms"),
        ("development", "dlx_yuki_wms_test"),
        ("test", "dlx_yuki_wms_test"),
        ("production", "dlx_yuki_wms_dev"),
    ],
)
def test_dev_seed_refuses_every_non_dev_target(environment: str, database: str) -> None:
    url = f"postgresql+psycopg://user:FakePassword@localhost:5432/{database}"

    with pytest.raises((DatabaseSafetyError, DevSeedError)):
        load_dev_target({"WMS_ENV": environment, "DATABASE_URL": url})


@pytest.mark.parametrize("environ", [{}, {"WMS_ENV": "development"}, {"DATABASE_URL": DEV_URL}])
def test_dev_seed_refuses_missing_process_configuration(environ: dict[str, str]) -> None:
    with pytest.raises(DatabaseSafetyError):
        load_dev_target(environ)


def test_seed_plan_uses_fixed_business_dates_and_expected_counts() -> None:
    assert tuple(day.isoformat() for day in DATES) == (
        "2026-09-01",
        "2026-09-02",
        "2026-09-03",
    )
    counts = expected_counts()
    assert counts["company_profiles"] == 1
    assert counts["inventory_priority_rules"] == 4
    assert counts["users"] == 3
    assert counts["inventory_lots"] == 7
    assert counts["bols"] == 2


def test_seed_business_data_has_no_runtime_clock_or_random_source() -> None:
    source = inspect.getsource(run)
    assert "datetime.now" not in source
    assert "uuid4" not in source
    assert "random(" not in source


def test_database_failures_are_rendered_without_driver_message() -> None:
    driver_message = "credential detail \ufffd"
    failure = OperationalError("connect", {}, RuntimeError(driver_message))

    code, message = safe_failure(failure)

    assert code == "database_connection_failed"
    assert message == "DEV database connection or transaction failed"
    assert driver_message not in message


@pytest.mark.parametrize(
    ("sqlstate", "expected_code", "expected_message"),
    [
        ("28P01", "database_authentication_failed", "DEV database role authentication failed"),
        ("3D000", "development_database_missing", "DEV database does not exist"),
    ],
)
def test_known_connection_failures_are_safely_classified(
    sqlstate: str, expected_code: str, expected_message: str
) -> None:
    class DriverFailure(RuntimeError):
        pass

    driver_failure = DriverFailure("sensitive driver detail")
    driver_failure.sqlstate = sqlstate
    failure = OperationalError("connect", {}, driver_failure)

    code, message = safe_failure(failure)

    assert code == expected_code
    assert message == expected_message
    assert "sensitive" not in message


def test_database_stage_is_reported_without_driver_detail() -> None:
    driver_failure = OperationalError("insert", {}, RuntimeError("secret row detail"))
    try:
        raise DevSeedDatabaseError("seed_insert") from driver_failure
    except DevSeedDatabaseError as failure:
        code, message = safe_failure(failure)

    assert code == "dev_seed_database_failed"
    assert message == "DEV database operation failed during seed_insert"
    assert "secret" not in message


def test_handshake_authentication_failure_is_classified_without_echo() -> None:
    driver_detail = 'password authentication failed for user "sensitive-user"'
    driver_failure = OperationalError("connect", {}, RuntimeError(driver_detail))
    try:
        raise DevSeedDatabaseError("connect") from driver_failure
    except DevSeedDatabaseError as failure:
        code, message = safe_failure(failure)

    assert code == "database_authentication_failed"
    assert message == "DEV database role authentication failed"
    assert "sensitive-user" not in message
