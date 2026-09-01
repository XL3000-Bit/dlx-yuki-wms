from typing import Literal

from pydantic import BaseModel, Field


class DispatchReadinessCheck(BaseModel):
    key: str
    label: str
    passed: bool
    reason: str | None = None
    route: str | None = None
    code: str | None = None


class DispatchReadinessRead(BaseModel):
    status: Literal["READY", "NOT_READY"]
    checks: list[DispatchReadinessCheck]
    blocking_reasons: list[str]
    blocking_codes: list[str] = Field(default_factory=list)
    error_code: str | None = None
