"""Apply the pinned DEV/TEST migration through a fail-closed connection."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.database_safety import (
    DatabaseSafetyError,
    SafeDatabaseTarget,
    validate_destructive_database_target,
)


EXPECTED_REVISION = "20260902_0026"


class SafeMigrationError(RuntimeError):
    """A credential-safe refusal or migration verification failure."""


def load_explicit_target(environ: Mapping[str, str]) -> tuple[SafeDatabaseTarget, str]:
    """Load only process-level values; never fall back to a local .env file."""
    environment = environ.get("WMS_ENV")
    database_url = environ.get("DATABASE_URL")
    target = validate_destructive_database_target(environment, database_url)
    assert database_url is not None  # Guaranteed by the validator.
    return target, database_url


def assert_connected_database(connection: object, target: SafeDatabaseTarget) -> None:
    """Verify the server-reported database before allowing Alembic to run."""
    actual_database = connection.scalar(text("SELECT current_database()"))
    if actual_database != target.database:
        raise SafeMigrationError("Connected database does not match the authorized target")


def verify_revision(connection: object, expected_revision: str = EXPECTED_REVISION) -> None:
    """Require exactly one Alembic revision matching the pinned target."""
    revisions = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    if revisions != [expected_revision]:
        raise SafeMigrationError("Alembic revision verification failed")


def run() -> SafeDatabaseTarget:
    target, database_url = load_explicit_target(os.environ)
    engine = None
    try:
        engine = create_engine(database_url)
        with engine.connect() as connection:
            assert_connected_database(connection, target)
            connection.rollback()

            alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, EXPECTED_REVISION)
            verify_revision(connection)
    except DatabaseSafetyError:
        raise
    except SafeMigrationError:
        raise
    except SQLAlchemyError as exc:
        raise SafeMigrationError("Database connection or migration failed") from exc
    finally:
        if engine is not None:
            engine.dispose()
    return target


def main() -> int:
    try:
        target = run()
    except (DatabaseSafetyError, SafeMigrationError) as exc:
        code = getattr(exc, "code", "migration_failed")
        print(f"REFUSED code={code}: {exc}")
        return 1

    print("Migration and revision verification succeeded")
    print(target.sanitized_summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
