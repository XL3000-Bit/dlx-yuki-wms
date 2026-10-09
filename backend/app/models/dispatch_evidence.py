"""Versioned configuration and append-only dispatch review history.

Policies have no application write endpoint. An enabled policy must be installed
through the separately reviewed configuration process; absence is fail-closed.
"""
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class DispatchEvidencePolicy(Base):
    __tablename__ = "dispatch_evidence_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True)
    business_type: Mapped[str] = mapped_column(String(10))
    version: Mapped[int] = mapped_column()
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    source: Mapped[str] = mapped_column(Text)
    rules: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("warehouse_id", "business_type", "version"),
                     CheckConstraint("business_type IN ('FBA','PRIVATE') AND version > 0", name="evidence_policy_domain_version"))


class DispatchEvidenceReview(Base):
    __tablename__ = "dispatch_evidence_reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    load_id: Mapped[int] = mapped_column(ForeignKey("loads.id", ondelete="RESTRICT"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("load_dispatch_plans.id", ondelete="RESTRICT"))
    content_revision: Mapped[int] = mapped_column()
    policy_id: Mapped[int] = mapped_column(ForeignKey("dispatch_evidence_policies.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(16))
    decision: Mapped[str] = mapped_column(String(8))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    operation_id: Mapped[str] = mapped_column(String(64), unique=True)
    note: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("kind IN ('DOCUMENTS','APPROVAL','EXCEPTIONS')", name="evidence_review_kind"),
                     CheckConstraint("decision IN ('ACCEPT','REJECT')", name="evidence_review_decision"))


def immutable(mapper, connection, target):
    raise ValueError("Dispatch evidence history is append-only; create a new version/review")


for model in (DispatchEvidencePolicy, DispatchEvidenceReview):
    event.listen(model, "before_update", immutable)
    event.listen(model, "before_delete", immutable)
