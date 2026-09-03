from __future__ import annotations

import pytest

from app.core.database_safety import DatabaseSafetyError, SafeDatabaseTarget
from scripts import reset_and_reseed_dev as reset


DEV_URL = "postgresql+psycopg://dev_user:FakePassword@localhost:5432/dlx_yuki_wms_dev"
TEST_URL = "postgresql+psycopg://test_user:FakePassword@localhost:5432/dlx_yuki_wms_test"


def env(**overrides: str) -> dict[str, str]:
    values = {"WMS_ENV": "development", "DATABASE_URL": DEV_URL}
    values.update(overrides)
    return values


def test_authorizes_only_exact_dev_target_and_confirmation() -> None:
    target, url = reset.authorize_target("dlx_yuki_wms_dev", env())
    assert target.database == "dlx_yuki_wms_dev"
    assert target.environment == "development"
    assert url == DEV_URL


@pytest.mark.parametrize("confirmation", [None, "", "dlx_yuki_wms", "dlx_yuki_wms_test", "DLX_YUKI_WMS_DEV"])
def test_rejects_wrong_confirmation(confirmation: str | None) -> None:
    with pytest.raises(reset.DevResetError, match="Confirmation"):
        reset.authorize_target(confirmation, env())


@pytest.mark.parametrize(
    ("values", "code"),
    [
        ({"WMS_ENV": "production"}, "destructive_environment_forbidden"),
        ({"WMS_ENV": "test"}, "database_not_allowlisted"),
        ({"DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/dlx_yuki_wms"}, "protected_database"),
        ({"DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/dlx_yuki_wms_test"}, "database_not_allowlisted"),
        ({"DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/unknown"}, "database_not_allowlisted"),
    ],
)
def test_rejects_forbidden_targets(values: dict[str, str], code: str) -> None:
    with pytest.raises(DatabaseSafetyError) as caught:
        reset.authorize_target("dlx_yuki_wms_dev", env(**values))
    assert caught.value.code == code


def test_rejects_valid_test_environment_and_database_pair() -> None:
    with pytest.raises(reset.DevResetError, match="restricted to the development"):
        reset.authorize_target(
            "dlx_yuki_wms_dev",
            env(WMS_ENV="test", DATABASE_URL=TEST_URL),
        )


@pytest.mark.parametrize("missing", ["WMS_ENV", "DATABASE_URL"])
def test_rejects_missing_required_configuration(missing: str) -> None:
    values = env()
    values.pop(missing)
    with pytest.raises(DatabaseSafetyError):
        reset.authorize_target("dlx_yuki_wms_dev", values)


class _RoleResult:
    def __init__(self, role: dict[str, bool]):
        self.role = role

    def mappings(self) -> _RoleResult:
        return self

    def one(self) -> dict[str, bool]:
        return self.role


class _RoleConnection:
    def __init__(self, role: dict[str, bool]):
        self.role = role

    def execute(self, _statement: object) -> _RoleResult:
        return _RoleResult(self.role)


def role(**overrides: bool | str) -> dict[str, bool | str]:
    values: dict[str, bool | str] = {
        "rolname": "dlx_yuki_wms_dev_user",
        "rolsuper": False,
        "rolcreatedb": False,
        "rolcreaterole": False,
        "rolreplication": False,
        "rolbypassrls": False,
    }
    values.update(overrides)
    return values


def test_accepts_low_privilege_application_role() -> None:
    reset._assert_low_privilege_role(_RoleConnection(role()))


def test_rejects_other_low_privilege_role() -> None:
    with pytest.raises(reset.DevResetError, match="dedicated DEV"):
        reset._assert_low_privilege_role(
            _RoleConnection(role(rolname="another_low_privilege_role"))
        )


@pytest.mark.parametrize("flag", ["rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication", "rolbypassrls"])
def test_rejects_each_elevated_role_privilege(flag: str) -> None:
    with pytest.raises(reset.DevResetError, match="forbidden elevated"):
        reset._assert_low_privilege_role(_RoleConnection(role(**{flag: True})))


def test_orchestration_order_and_second_run_idempotency(monkeypatch: pytest.MonkeyPatch) -> None:
    target = SafeDatabaseTarget("development", "localhost", 5432, "dlx_yuki_wms_dev")
    calls: list[str] = []

    monkeypatch.setattr(reset, "authorize_target", lambda confirmation, environ: (target, DEV_URL))
    monkeypatch.setattr(reset, "reset_public_schema", lambda actual, url: calls.append("reset"))
    monkeypatch.setattr(reset.safe_alembic, "run", lambda: calls.append("migrate") or target)
    monkeypatch.setattr(reset, "verify_migration_bootstrap", lambda actual, url: calls.append("bootstrap"))

    seed_results = iter(["PASS_CREATED", "PASS_NO_CHANGES"])
    monkeypatch.setattr(
        reset.seed_dev,
        "run",
        lambda: calls.append("seed") or (target, next(seed_results)),
    )
    monkeypatch.setattr(
        reset.verify_dev_seed,
        "verify",
        lambda: calls.append("verify") or (target, {}, 0),
    )

    actual, first, second = reset.run("dlx_yuki_wms_dev")
    assert actual == target
    assert first == "PASS_CREATED"
    assert second == "PASS_NO_CHANGES"
    assert calls == ["reset", "migrate", "bootstrap", "seed", "verify", "seed", "verify"]


def test_schema_reset_uses_schema_ddl_not_database_ddl() -> None:
    import inspect as python_inspect

    source = python_inspect.getsource(reset.reset_public_schema).upper()
    assert "DROP SCHEMA PUBLIC CASCADE" in source
    assert "CREATE SCHEMA PUBLIC" in source
    assert "DROP DATABASE" not in source
    assert "CREATE DATABASE" not in source


def test_failure_output_does_not_reflect_credentials() -> None:
    secret = "DoNotPrintThisPassword"
    exc = reset.DevResetDatabaseError("connect")
    exc.__cause__ = RuntimeError(f"postgresql://user:{secret}@localhost/dev")
    code, message = reset._safe_failure(exc)
    assert code == "dev_reset_database_failed"
    assert secret not in message
