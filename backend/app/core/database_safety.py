"""Fail-closed validation for destructive DEV/TEST database operations.

This module only parses configuration. It never opens a database connection.
"""

from dataclasses import dataclass

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


PROTECTED_DATABASES = frozenset({"dlx_yuki_wms"})
DESTRUCTIVE_DATABASE_ALLOWLIST = {
    "development": "dlx_yuki_wms_dev",
    "test": "dlx_yuki_wms_test",
}
KNOWN_ENVIRONMENTS = frozenset({"development", "test", "production"})
ALLOWED_DATABASE_DRIVERS = frozenset({"postgresql", "postgresql+psycopg"})


class DatabaseSafetyError(ValueError):
    """A credential-safe refusal to authorize a destructive operation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class SafeDatabaseTarget:
    environment: str
    host: str
    port: int
    database: str

    def sanitized_summary(self) -> str:
        """Return target identity without username, password, or URL."""
        return "\n".join(
            (
                f"environment={self.environment}",
                f"host={self.host}",
                f"port={self.port}",
                f"database={self.database}",
            )
        )


def _refuse(code: str, message: str) -> None:
    raise DatabaseSafetyError(code, message)


def validate_destructive_database_target(
    wms_env: str | None,
    database_url: str | None,
) -> SafeDatabaseTarget:
    """Authorize only the exact DEV/TEST environment-to-database mappings.

    Input values are deliberately excluded from every error message so a
    malformed URL can never cause credentials to be reflected in logs.
    """
    if wms_env is None or not wms_env.strip():
        _refuse("missing_environment", "WMS_ENV is required for destructive operations")

    environment = wms_env.strip()
    if environment not in KNOWN_ENVIRONMENTS:
        _refuse("unknown_environment", "WMS_ENV is not an explicitly recognized environment")

    if database_url is None or not database_url.strip():
        _refuse("missing_database_url", "DATABASE_URL is required for destructive operations")

    try:
        parsed = make_url(database_url)
        driver = parsed.drivername
        host = parsed.host
        port = parsed.port or 5432
        database = parsed.database
    except (ArgumentError, TypeError, ValueError):
        _refuse("malformed_database_url", "DATABASE_URL could not be safely parsed")
    except Exception:
        _refuse("database_validation_error", "Database target validation failed closed")

    if driver not in ALLOWED_DATABASE_DRIVERS or not host or not database:
        _refuse("unparseable_database_target", "DATABASE_URL does not identify a supported database target")

    if database in PROTECTED_DATABASES:
        _refuse("protected_database", "The protected main database cannot be used for destructive operations")

    expected_database = DESTRUCTIVE_DATABASE_ALLOWLIST.get(environment)
    if expected_database is None:
        _refuse("destructive_environment_forbidden", "This environment does not allow destructive operations")

    if database != expected_database:
        _refuse("database_not_allowlisted", "The database is not allowlisted for the selected environment")

    return SafeDatabaseTarget(
        environment=environment,
        host=host,
        port=port,
        database=database,
    )
