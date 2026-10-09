"""Verify the unique code head against an authorized DEV/TEST database, read-only."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Mapping
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from app.core.database_safety import DatabaseSafetyError, SafeDatabaseTarget, validate_destructive_database_target


class SafeMigrationError(RuntimeError):
    """A credential-safe refusal or migration verification failure."""


def get_code_head():
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    try:
        heads = ScriptDirectory.from_config(config).get_heads()
    except Exception as exc:
        raise SafeMigrationError("Cannot resolve Alembic code heads") from exc
    if len(heads) != 1:
        raise SafeMigrationError(f"Expected exactly one Alembic code head; found {len(heads)}")
    return heads[0]


def load_explicit_target(environ: Mapping[str, str]):
    environment = environ.get("WMS_ENV")
    database_url = environ.get("DATABASE_URL")
    target = validate_destructive_database_target(environment, database_url)
    assert database_url is not None
    return target, database_url


def assert_connected_database(connection, target: SafeDatabaseTarget):
    actual_database = connection.scalar(text("SELECT current_database()"))
    if actual_database != target.database:
        raise SafeMigrationError("Connected database does not match the authorized target")


def verify_revision(connection, expected_revision=None):
    expected_revision = expected_revision or get_code_head()
    revisions = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    if revisions != [expected_revision]:
        raise SafeMigrationError(f"Alembic revision verification failed: database revisions={revisions!r}; code head={expected_revision}. No migration was executed.")


def run():
    target, database_url = load_explicit_target(os.environ)
    expected_revision = get_code_head()
    engine = None
    try:
        engine = create_engine(database_url)
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            assert_connected_database(connection, target)
            verify_revision(connection, expected_revision)
            connection.rollback()
    except DatabaseSafetyError:
        raise
    except SafeMigrationError:
        raise
    except SQLAlchemyError as exc:
        raise SafeMigrationError("Database connection or read-only revision check failed") from exc
    finally:
        if engine is not None:
            engine.dispose()
    return target


def main():
    try:
        target = run()
    except (DatabaseSafetyError, SafeMigrationError) as exc:
        code = getattr(exc, "code", "migration_failed")
        print(f"REFUSED code={code}: {exc}")
        return 1
    print("Read-only revision verification succeeded; no migration executed")
    print(target.sanitized_summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
