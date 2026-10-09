from functools import lru_cache
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Warehouse Management System"
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("WMS_ENV", "ENVIRONMENT"),
    )
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    # Required: absence must never silently fall back to the protected main DB.
    database_url: str = Field(min_length=1)
    jwt_secret_key: str = Field(default="development-only-change-me-32-chars", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cors_origins: list[str] = ["http://localhost:5173"]
    trailer_default_pallet_capacity: int = Field(default=26, ge=1, le=100)
    business_timezone: str = "America/Los_Angeles"
    document_storage_root: str = "data/documents"
    document_max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        if not value.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must use PostgreSQL")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
