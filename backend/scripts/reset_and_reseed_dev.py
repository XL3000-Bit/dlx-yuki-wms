"""Fail-closed DEV-only schema reset, migration, and deterministic reseed."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import app.models  # noqa: F401 - register all mapped tables
from app.core.database_safety import (
    DatabaseSafetyError,
    SafeDatabaseTarget,
    validate_destructive_database_target,
)
from app.db.base import Base
from scripts import safe_alembic, seed_dev, verify_dev_seed


DEV_DATABASE = "dlx_yuki_wms_dev"
DEV_ROLE = "dlx_yuki_wms_dev_user"


class DevResetError(RuntimeError):
    """A credential-safe refusal or Phase G verification failure."""


class DevResetDatabaseError(DevResetError):
    def __init__(self, stage: str):
        self.stage = stage
        super().__init__(f"DEV reset/reseed failed during {stage}")


def authorize_target(
    confirmation: str | None,
    environ: Mapping[str, str],
) -> tuple[SafeDatabaseTarget, str]:
    """Require the exact DEV target and independent typed confirmation."""
    if confirmation != DEV_DATABASE:
        raise DevResetError("Confirmation does not match the authorized DEV database")

    target = validate_destructive_database_target(
        environ.get("WMS_ENV"), environ.get("DATABASE_URL")
    )
    if target.environment != "development" or target.database != DEV_DATABASE:
        raise DevResetError("Phase G is restricted to the development database")
    return target, environ["DATABASE_URL"]


def _assert_low_privilege_role(connection: object) -> None:
    role = connection.execute(
        text(
            """
            SELECT rolname, rolsuper, rolcreatedb, rolcreaterole,
                   rolreplication, rolbypassrls
            FROM pg_roles
            WHERE rolname = current_user
            """
        )
    ).mappings().one()
    if role["rolname"] != DEV_ROLE:
        raise DevResetError("Phase G requires the dedicated DEV application role")
    forbidden = (
        role["rolsuper"],
        role["rolcreatedb"],
        role["rolcreaterole"],
        role["rolreplication"],
        role["rolbypassrls"],
    )
    if any(forbidden):
        raise DevResetError("The DEV application role has a forbidden elevated privilege")


def reset_public_schema(target: SafeDatabaseTarget, database_url: str) -> None:
    """Reset only public inside the already-authorized DEV database."""
    engine = create_engine(database_url)
    stage = "connect"
    try:
        with engine.begin() as connection:
            stage = "connected_database_verification"
            safe_alembic.assert_connected_database(connection, target)
            stage = "role_privilege_verification"
            _assert_low_privilege_role(connection)
            stage = "schema_reset"
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public AUTHORIZATION CURRENT_USER"))
    except (DatabaseSafetyError, safe_alembic.SafeMigrationError, DevResetError):
        raise
    except SQLAlchemyError as exc:
        raise DevResetDatabaseError(stage) from exc
    finally:
        engine.dispose()


def verify_migration_bootstrap(target: SafeDatabaseTarget, database_url: str) -> None:
    """Require the migrated empty baseline before inserting synthetic DEV data."""
    engine = create_engine(database_url)
    stage = "connect"
    try:
        with engine.connect() as connection:
            stage = "connected_database_verification"
            safe_alembic.assert_connected_database(connection, target)
            connection.rollback()
            transaction = connection.begin()
            try:
                stage = "read_only_guard"
                connection.execute(text("SET TRANSACTION READ ONLY"))
                stage = "revision_verification"
                safe_alembic.verify_revision(connection, safe_alembic.EXPECTED_REVISION)
                stage = "schema_verification"
                actual_tables = set(inspect(connection).get_table_names(schema="public"))
                expected_tables = set(Base.metadata.tables) | {"alembic_version"}
                if actual_tables != expected_tables:
                    raise DevResetError("Migration bootstrap schema does not match ORM metadata")
                stage = "baseline_verification"
                if seed_dev.seed_state(Session(bind=connection)) != "EMPTY_BASELINE":
                    raise DevResetError("Migration bootstrap is not the expected empty baseline")
            finally:
                if transaction.is_active:
                    transaction.rollback()
    except (DatabaseSafetyError, safe_alembic.SafeMigrationError, DevResetError):
        raise
    except SQLAlchemyError as exc:
        raise DevResetDatabaseError(stage) from exc
    finally:
        engine.dispose()


def run(confirmation: str) -> tuple[SafeDatabaseTarget, str, str]:
    """Run Phase G in the required reset -> migrate -> seed -> verify order."""
    target, database_url = authorize_target(confirmation, os.environ)
    reset_public_schema(target, database_url)
    migrated_target = safe_alembic.run()
    if migrated_target != target:
        raise DevResetError("Migration target identity changed unexpectedly")
    verify_migration_bootstrap(target, database_url)

    first_target, first_result = seed_dev.run()
    if first_target != target or first_result != "PASS_CREATED":
        raise DevResetError("First deterministic seed run did not create the expected dataset")
    verified_target, _counts, orphans = verify_dev_seed.verify()
    if verified_target != target or orphans != 0:
        raise DevResetError("First deterministic seed verification failed")

    second_target, second_result = seed_dev.run()
    if second_target != target or second_result != "PASS_NO_CHANGES":
        raise DevResetError("Second deterministic seed run was not idempotent")
    verified_target, _counts, orphans = verify_dev_seed.verify()
    if verified_target != target or orphans != 0:
        raise DevResetError("Second deterministic seed verification failed")
    return target, first_result, second_result


def _safe_failure(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, DatabaseSafetyError):
        return exc.code, str(exc)
    if isinstance(exc, DevResetDatabaseError):
        original = getattr(exc.__cause__, "orig", None)
        authentication_failed = (
            getattr(original, "sqlstate", None) == "28P01"
            or "password authentication failed" in str(original).lower()
        )
        if authentication_failed:
            return "database_authentication_failed", "DEV database role authentication failed"
        return "dev_reset_database_failed", str(exc)
    if isinstance(exc, (DevResetError, safe_alembic.SafeMigrationError)):
        return "dev_reset_refused", str(exc)
    return "unexpected_failure", f"Phase G stopped on {type(exc).__name__}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely reset and reseed only the WMS DEV database")
    parser.add_argument("--confirm-database", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        target, first_result, second_result = run(args.confirm_database)
    except Exception as exc:
        code, message = _safe_failure(exc)
        print(f"REFUSED code={code}: {message}")
        print("PHASE_G_SAFE_DEV_RESET_AND_RESEED=STOPPED")
        return 1

    print("DATABASE_SAFETY=PASS")
    print(target.sanitized_summary())
    print("CURRENT_DATABASE_VERIFIED=PASS")
    print("ROLE_PRIVILEGE_SAFETY=PASS")
    print("SCHEMA_RESET=PASS")
    print(f"ALEMBIC_REVISION={safe_alembic.EXPECTED_REVISION}")
    print("MIGRATION_BOOTSTRAP=PASS")
    print(f"FIRST_SEED_RESULT={first_result}")
    print("FIRST_SEED_VERIFICATION=PASS")
    print(f"SECOND_SEED_RESULT={second_result}")
    print("IDEMPOTENCY_VERIFICATION=PASS")
    print("TEST_DATABASE_ACTIONS=0")
    print("MAIN_DATABASE_CONNECTIONS=0")
    print("PDA_DEVELOPMENT=PAUSED")
    print("PDA_PRODUCTION_USE=PROHIBITED")
    print("AUTHORIZED_PDA_ACTION=NONE")
    print("PHASE_G_SAFE_DEV_RESET_AND_RESEED=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
