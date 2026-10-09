from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.core.database_safety import DatabaseSafetyError, SafeDatabaseTarget
from scripts.safe_alembic import (
    SafeMigrationError,
    assert_connected_database,
    load_explicit_target,
    verify_revision,
)


DEV_URL = "postgresql+psycopg://dev_user:FakePassword@localhost:5432/dlx_yuki_wms_dev"


@dataclass
class FakeScalarResult:
    values: list[str]

    def scalars(self) -> "FakeScalarResult":
        return self

    def all(self) -> list[str]:
        return self.values


class FakeConnection:
    def __init__(self, database: str, revisions: list[str] | None = None) -> None:
        self.database = database
        self.revisions = revisions or []

    def scalar(self, _statement: object) -> str:
        return self.database

    def execute(self, _statement: object) -> FakeScalarResult:
        return FakeScalarResult(self.revisions)


def test_explicit_dev_target_is_loaded_without_dotenv_fallback() -> None:
    target, url = load_explicit_target({"WMS_ENV": "development", "DATABASE_URL": DEV_URL})

    assert target.database == "dlx_yuki_wms_dev"
    assert url == DEV_URL


@pytest.mark.parametrize("environ", [{}, {"WMS_ENV": "development"}, {"DATABASE_URL": DEV_URL}])
def test_missing_process_configuration_fails_closed(environ: dict[str, str]) -> None:
    with pytest.raises(DatabaseSafetyError):
        load_explicit_target(environ)


def test_connected_database_must_match_authorized_target() -> None:
    target = SafeDatabaseTarget("development", "localhost", 5432, "dlx_yuki_wms_dev")

    with pytest.raises(SafeMigrationError, match="does not match"):
        assert_connected_database(FakeConnection("dlx_yuki_wms"), target)


def test_connected_database_match_is_allowed() -> None:
    target = SafeDatabaseTarget("development", "localhost", 5432, "dlx_yuki_wms_dev")

    assert_connected_database(FakeConnection("dlx_yuki_wms_dev"), target)


def test_revision_tracks_current_unique_head():
    from scripts import safe_alembic as safe
    head = safe.get_code_head()
    verify_revision(FakeConnection("dlx_yuki_wms_dev", [head]))
    for revisions in [[], ["older_revision"], [head, "other_head"]]:
        with pytest.raises(SafeMigrationError, match="No migration was executed"):
            verify_revision(FakeConnection("dlx_yuki_wms_dev", revisions))


@pytest.mark.parametrize("heads", [[], ["a", "b"]])
def test_invalid_code_heads_fail_closed(monkeypatch, heads):
    from scripts import safe_alembic as safe
    monkeypatch.setattr(safe.ScriptDirectory, "get_heads", lambda self: heads)
    with pytest.raises(SafeMigrationError, match="exactly one"):
        safe.get_code_head()


def test_future_unique_head_is_discovered(monkeypatch):
    from scripts import safe_alembic as safe
    monkeypatch.setattr(safe.ScriptDirectory, "get_heads", lambda self: ["future_head"])
    assert safe.get_code_head() == "future_head"
    safe.verify_revision(FakeConnection("dev", ["future_head"]))


def test_run_only_reads_revision(monkeypatch):
    from scripts import safe_alembic as safe
    statements = []
    class Connection(FakeConnection):
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, statement):
            statements.append(str(statement))
            return super().execute(statement)
        def rollback(self): statements.append("ROLLBACK")
    class Engine:
        def connect(self): return Connection("dlx_yuki_wms_dev", [safe.get_code_head()])
        def dispose(self): statements.append("DISPOSE")
    monkeypatch.setenv("WMS_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", DEV_URL)
    monkeypatch.setattr(safe, "create_engine", lambda url: Engine())
    safe.run()
    assert statements == ["SET TRANSACTION READ ONLY", "SELECT version_num FROM alembic_version", "ROLLBACK", "DISPOSE"]
