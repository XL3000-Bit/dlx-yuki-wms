import pytest

from app.core.database_safety import (
    DatabaseSafetyError,
    validate_destructive_database_target,
)


DEV_URL = "postgresql+psycopg://dev_user:FakeDevPassword@localhost:5432/dlx_yuki_wms_dev"
TEST_URL = "postgresql+psycopg://test_user:FakeTestPassword@localhost:5432/dlx_yuki_wms_test"


@pytest.mark.parametrize(
    ("environment", "url", "database"),
    [
        ("development", DEV_URL, "dlx_yuki_wms_dev"),
        ("test", TEST_URL, "dlx_yuki_wms_test"),
    ],
)
def test_exact_environment_database_mapping_is_allowed(environment: str, url: str, database: str) -> None:
    target = validate_destructive_database_target(environment, url)

    assert target.environment == environment
    assert target.database == database
    assert target.host == "localhost"
    assert target.port == 5432


@pytest.mark.parametrize(
    ("environment", "database"),
    [
        ("development", "dlx_yuki_wms"),
        ("test", "dlx_yuki_wms"),
        ("production", "dlx_yuki_wms"),
        ("development", "dlx_yuki_wms_test"),
        ("test", "dlx_yuki_wms_dev"),
        ("development", "random_db"),
        ("test", "random_db"),
    ],
)
def test_non_allowlisted_database_is_refused(environment: str, database: str) -> None:
    url = f"postgresql+psycopg://user:SecretValue@localhost:5432/{database}"

    with pytest.raises(DatabaseSafetyError):
        validate_destructive_database_target(environment, url)


@pytest.mark.parametrize("environment", ["development", "test", "production"])
def test_protected_main_database_is_always_refused(environment: str) -> None:
    url = "postgresql+psycopg://user:SecretValue@localhost:5432/dlx_yuki_wms"

    with pytest.raises(DatabaseSafetyError) as caught:
        validate_destructive_database_target(environment, url)

    assert caught.value.code == "protected_database"


@pytest.mark.parametrize("environment", [None, "", "   "])
def test_missing_environment_is_refused(environment: str | None) -> None:
    with pytest.raises(DatabaseSafetyError) as caught:
        validate_destructive_database_target(environment, DEV_URL)

    assert caught.value.code == "missing_environment"


@pytest.mark.parametrize("url", [None, "", "   "])
def test_missing_database_url_is_refused(url: str | None) -> None:
    with pytest.raises(DatabaseSafetyError) as caught:
        validate_destructive_database_target("development", url)

    assert caught.value.code == "missing_database_url"


def test_unknown_environment_is_refused() -> None:
    with pytest.raises(DatabaseSafetyError) as caught:
        validate_destructive_database_target("staging", DEV_URL)

    assert caught.value.code == "unknown_environment"


def test_production_cannot_authorize_an_allowlisted_nonproduction_database() -> None:
    with pytest.raises(DatabaseSafetyError) as caught:
        validate_destructive_database_target("production", DEV_URL)

    assert caught.value.code == "destructive_environment_forbidden"


@pytest.mark.parametrize(
    "url",
    [
        "not a database url",
        "postgresql+psycopg://user:SecretValue@[invalid",
        "postgresql+psycopg://user:SecretValue@localhost:5432",
        "sqlite:///dlx_yuki_wms_dev",
    ],
)
def test_malformed_or_unparseable_database_url_is_refused(url: str) -> None:
    with pytest.raises(DatabaseSafetyError):
        validate_destructive_database_target("development", url)


def test_error_never_reflects_credentials_or_complete_url() -> None:
    password = "UltraSecretPassword123"
    url = f"postgresql+psycopg://sensitive_user:{password}@localhost:5432/random_db"

    with pytest.raises(DatabaseSafetyError) as caught:
        validate_destructive_database_target("development", url)

    message = str(caught.value)
    assert password not in message
    assert "sensitive_user" not in message
    assert url not in message


def test_sanitized_target_summary_contains_no_credentials() -> None:
    target = validate_destructive_database_target("development", DEV_URL)

    summary = target.sanitized_summary()
    assert summary == (
        "environment=development\n"
        "host=localhost\n"
        "port=5432\n"
        "database=dlx_yuki_wms_dev"
    )
    assert "dev_user" not in summary
    assert "FakeDevPassword" not in summary
    assert DEV_URL not in summary


def test_validation_exception_fails_closed_without_reflecting_input(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_url = "postgresql+psycopg://user:NeverReflectMe@localhost:5432/dlx_yuki_wms_dev"

    def unexpected_failure(_: str) -> None:
        raise RuntimeError(secret_url)

    monkeypatch.setattr("app.core.database_safety.make_url", unexpected_failure)

    with pytest.raises(DatabaseSafetyError) as caught:
        validate_destructive_database_target("development", secret_url)

    assert caught.value.code == "database_validation_error"
    assert secret_url not in str(caught.value)
