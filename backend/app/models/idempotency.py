from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, JSON, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


JsonType = JSON().with_variant(JSONB(), "postgresql")


class OutboundInventoryIdempotency(Base):
    __tablename__ = "outbound_inventory_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "scope", "action", "idempotency_key", name="uq_outbound_inventory_idempotency_command"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    response_status: Mapped[int | None] = mapped_column(nullable=True)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
