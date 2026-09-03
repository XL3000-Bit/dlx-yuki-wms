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


def test_revision_must_be_exactly_the_pinned_single_head() -> None:
    verify_revision(FakeConnection("dlx_yuki_wms_dev", ["20260902_0026"]))

    with pytest.raises(SafeMigrationError, match="revision verification failed"):
        verify_revision(FakeConnection("dlx_yuki_wms_dev", ["older_revision"]))

    with pytest.raises(SafeMigrationError, match="revision verification failed"):
        verify_revision(FakeConnection("dlx_yuki_wms_dev", ["20260902_0026", "other_head"]))
