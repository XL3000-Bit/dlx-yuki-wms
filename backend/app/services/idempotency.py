import hashlib
import json
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.idempotency import OutboundInventoryIdempotency


_SAFE_KEY = re.compile(r"^[!-~]{1,128}$")


def validate_idempotency_key(value: str | None) -> str:
    if value is None or not value.strip():
        raise HTTPException(400, {"code": "OUTBOUND_IDEMPOTENCY_KEY_REQUIRED", "message": "Idempotency-Key is required"})
    value = value.strip()
    if not _SAFE_KEY.fullmatch(value):
        raise HTTPException(400, {"code": "OUTBOUND_IDEMPOTENCY_KEY_INVALID", "message": "Idempotency-Key must contain 1-128 safe printable ASCII characters"})
    return value


def request_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def acquire_command_lock(db: Session, scope: str, action: str, key: str) -> None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        digest = hashlib.sha256(f"{scope}\0{action}\0{key}".encode()).digest()
        lock_id = int.from_bytes(digest[:8], byteorder="big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})


def find_receipt(db: Session, scope: str, action: str, key: str) -> OutboundInventoryIdempotency | None:
    return db.scalar(
        select(OutboundInventoryIdempotency).where(
            OutboundInventoryIdempotency.scope == scope,
            OutboundInventoryIdempotency.action == action,
            OutboundInventoryIdempotency.idempotency_key == key,
        )
    )
