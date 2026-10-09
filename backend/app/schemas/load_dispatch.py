"""Read-only dispatch evidence contract; never an authorization token."""
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ReadinessStatus(str, Enum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ReadinessCheck(BaseModel):
    key: str
    status: ReadinessStatus
    reason_code: str
    reason: str
    evidence: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class DispatchReadiness(BaseModel):
    load_id: int
    checked_at: datetime
    plan_id: int | None = None
    plan_version: int | None = None
    content_revision: int | None = None
    ready: bool = False
    checks: list[ReadinessCheck]
    consistency: str = "Sequential reads in the request transaction; not a locked dispatch snapshot."
    notice: str = "此预检尚未接入现有派发阻断；结果不是派发授权，后续修改可使结果失效。"
