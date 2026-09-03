"""Read-only Phase C discovery for the allowlisted development database."""

from __future__ import annotations

import os
from collections.abc import Mapping

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError

import app.models  # noqa: F401 - registers every mapped table on Base.metadata
from app.core.database_safety import DatabaseSafetyError, SafeDatabaseTarget, validate_destructive_database_target
from app.db.base import Base
from scripts.safe_alembic import EXPECTED_REVISION, SafeMigrationError, assert_connected_database, verify_revision


BASELINE_COUNTS = {
    "company_profiles": 1,
    "inventory_priority_rules": 4,
}


class SeedDiscoveryError(RuntimeError):
    """A credential-safe Phase C discovery failure."""


def load_dev_target(environ: Mapping[str, str]) -> tuple[SafeDatabaseTarget, str]:
    target = validate_destructive_database_target(environ.get("WMS_ENV"), environ.get("DATABASE_URL"))
    if target.environment != "development" or target.database != "dlx_yuki_wms_dev":
        raise SeedDiscoveryError("Phase C is restricted to the development database")
    database_url = environ.get("DATABASE_URL")
    assert database_url is not None
    return target, database_url


def discover() -> tuple[SafeDatabaseTarget, dict[str, int]]:
    target, database_url = load_dev_target(os.environ)
    engine = None
    try:
        engine = create_engine(database_url)
        with engine.connect() as connection:
            assert_connected_database(connection, target)
            connection.rollback()
            transaction = connection.begin()
            try:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                verify_revision(connection, EXPECTED_REVISION)

                db_inspector = inspect(connection)
                database_tables = set(db_inspector.get_table_names(schema="public"))
                model_tables = set(Base.metadata.tables)
                expected_tables = model_tables | {"alembic_version"}
                missing_tables = sorted(expected_tables - database_tables)
                unexpected_tables = sorted(database_tables - expected_tables)

                column_mismatches: list[str] = []
                for table_name in sorted(model_tables & database_tables):
                    database_columns = {column["name"] for column in db_inspector.get_columns(table_name)}
                    model_columns = set(Base.metadata.tables[table_name].columns.keys())
                    if database_columns != model_columns:
                        column_mismatches.append(table_name)

                if missing_tables or unexpected_tables or column_mismatches:
                    print("SCHEMA_COMPATIBLE=NO")
                    print("MISSING_TABLES=" + ",".join(missing_tables))
                    print("UNEXPECTED_TABLES=" + ",".join(unexpected_tables))
                    print("COLUMN_MISMATCH_TABLES=" + ",".join(column_mismatches))
                    raise SeedDiscoveryError("DEV schema does not exactly match current ORM metadata")

                counts = {
                    table_name: connection.scalar(
                        select(text("count(*)")).select_from(Base.metadata.tables[table_name])
                    )
                    for table_name in sorted(model_tables)
                }
                transaction.rollback()
            except Exception:
                if transaction.is_active:
                    transaction.rollback()
                raise
    except (DatabaseSafetyError, SafeMigrationError, SeedDiscoveryError):
        raise
    except SQLAlchemyError as exc:
        raise SeedDiscoveryError("Read-only DEV schema discovery failed") from exc
    finally:
        if engine is not None:
            engine.dispose()

    return target, counts


def main() -> int:
    try:
        target, counts = discover()
    except (DatabaseSafetyError, SafeMigrationError, SeedDiscoveryError) as exc:
        code = getattr(exc, "code", "seed_discovery_failed")
        print(f"REFUSED code={code}: {exc}")
        return 1

    print("DATABASE_SAFETY=PASS")
    print(target.sanitized_summary())
    print(f"ALEMBIC_REVISION={EXPECTED_REVISION}")
    print("SCHEMA_COMPATIBLE=YES")
    for table_name, row_count in counts.items():
        print(f"ROW_COUNT {table_name}={row_count}")

    nonbaseline = sorted(
        table_name
        for table_name, row_count in counts.items()
        if row_count != BASELINE_COUNTS.get(table_name, 0)
    )
    if nonbaseline:
        print("SEED_STATE=UNKNOWN_NONEMPTY")
        print("NONBASELINE_TABLES=" + ",".join(nonbaseline))
        return 2

    print("SEED_STATE=EMPTY_BASELINE")
    print("PHASE_C_DEV_DISCOVERY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
