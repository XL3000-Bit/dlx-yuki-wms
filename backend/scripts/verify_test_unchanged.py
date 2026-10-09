"""Read-only proof that Phase D did not modify the allowlisted TEST DB."""
from __future__ import annotations

import os
from collections.abc import Mapping

from sqlalchemy import Enum as SqlEnum
from sqlalchemy import String, Text, cast, create_engine, func, inspect, or_, select, text
from sqlalchemy.exc import SQLAlchemyError

import app.models  # noqa: F401 - register all mapped tables
from app.core.database_safety import DatabaseSafetyError, SafeDatabaseTarget, validate_destructive_database_target
from app.db.base import Base
from scripts.discover_dev_seed_state import BASELINE_COUNTS
from scripts.safe_alembic import get_code_head, SafeMigrationError, assert_connected_database, verify_revision


class DatabaseUnchangedError(RuntimeError):
    """A credential-safe Phase F verification failure."""


class TestUnchangedDatabaseError(DatabaseUnchangedError):
    def __init__(self, stage: str):
        self.stage = stage
        super().__init__(f"Read-only TEST verification failed during {stage}")


def load_test_target(environ: Mapping[str, str]) -> tuple[SafeDatabaseTarget, str]:
    target = validate_destructive_database_target(environ.get("WMS_ENV"), environ.get("DATABASE_URL"))
    if target.environment != "test" or target.database != "dlx_yuki_wms_test":
        raise DatabaseUnchangedError("Phase F is restricted to the test database")
    return target, environ["DATABASE_URL"]


def expected_baseline_counts() -> dict[str, int]:
    return {name: BASELINE_COUNTS.get(name, 0) for name in Base.metadata.tables}


def _marker_count(connection) -> int:
    total = 0
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if not isinstance(column.type, (String, Text, SqlEnum)):
                continue
            value = cast(column, String)
            total += connection.scalar(
                select(func.count()).select_from(table).where(
                    or_(value.contains("DEV-"), value.contains("SYN-"))
                )
            ) or 0
    return total


def verify() -> tuple[SafeDatabaseTarget, dict[str, int], int]:
    target, database_url = load_test_target(os.environ)
    engine = create_engine(database_url)
    stage = "connect"
    try:
        with engine.connect() as connection:
            stage = "target_verification"
            assert_connected_database(connection, target)
            connection.rollback()
            transaction = connection.begin()
            try:
                stage = "read_only_guard"
                connection.execute(text("SET TRANSACTION READ ONLY"))
                stage = "revision_verification"
                verify_revision(connection)
                stage = "schema_verification"
                database_tables = set(inspect(connection).get_table_names(schema="public"))
                if database_tables != set(Base.metadata.tables) | {"alembic_version"}:
                    raise DatabaseUnchangedError("TEST schema table set does not match current ORM metadata")

                stage = "baseline_verification"
                counts = {
                    name: connection.scalar(select(func.count()).select_from(table)) or 0
                    for name, table in Base.metadata.tables.items()
                }
                expected = expected_baseline_counts()
                if counts != expected:
                    changed = sorted(name for name in counts if counts[name] != expected[name])
                    raise DatabaseUnchangedError(
                        "TEST differs from the approved baseline; changed tables: " + ",".join(changed)
                    )

                stage = "marker_verification"
                markers = _marker_count(connection)
                if markers:
                    raise DatabaseUnchangedError("TEST contains DEV or synthetic seed markers")
            finally:
                if transaction.is_active:
                    transaction.rollback()
        return target, counts, markers
    except (DatabaseSafetyError, SafeMigrationError, DatabaseUnchangedError):
        raise
    except SQLAlchemyError as exc:
        raise TestUnchangedDatabaseError(stage) from exc
    finally:
        engine.dispose()


def _safe_failure(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, DatabaseSafetyError):
        return exc.code, str(exc)
    if isinstance(exc, SafeMigrationError):
        return "migration_verification_failed", str(exc)
    if isinstance(exc, TestUnchangedDatabaseError):
        original = getattr(exc.__cause__, "orig", None)
        if getattr(original, "sqlstate", None) == "28P01" or "password authentication failed" in str(original).lower():
            return "database_authentication_failed", "TEST database role authentication failed"
        return "test_verification_database_failed", str(exc)
    if isinstance(exc, DatabaseUnchangedError):
        return "test_unchanged_verification_failed", str(exc)
    return "unexpected_failure", f"Phase F stopped on {type(exc).__name__}"


def main() -> int:
    try:
        target, counts, markers = verify()
    except Exception as exc:
        code, message = _safe_failure(exc)
        print(f"REFUSED code={code}: {message}")
        print("PHASE_F_TEST_UNCHANGED=STOPPED")
        return 1

    print("DATABASE_SAFETY=PASS")
    print(target.sanitized_summary())
    print(f"ALEMBIC_REVISION={get_code_head()}")
    print(f"COMPANY_PROFILES={counts['company_profiles']}")
    print(f"INVENTORY_PRIORITY_RULES={counts['inventory_priority_rules']}")
    print("OTHER_BUSINESS_ROWS=0")
    print(f"TEST_DEV_SYN_MARKERS={markers}")
    print("READ_ONLY_VERIFICATION=PASS")
    print("PHASE_F_TEST_UNCHANGED=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
