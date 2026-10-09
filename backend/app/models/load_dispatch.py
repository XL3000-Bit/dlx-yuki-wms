"""Dispatch facts and versioned plans maintained by explicit scoped writers.

Allocation facts do not reserve stock. No history is inferred or backfilled.
Final plans are immutable in PostgreSQL (see the structure migration).
"""
from decimal import Decimal
from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class LoadAllocation(Base, TimestampMixin):
    __tablename__ = "load_allocations"
    __table_args__ = (
        CheckConstraint("carton_qty BETWEEN 0 AND 9999999999.99", name="cartons_valid"),
        CheckConstraint("pallet_qty BETWEEN 0 AND 9999999999.99", name="pallets_valid"),
        UniqueConstraint("operation_id", name="uq_load_allocation_operation"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    load_id: Mapped[int] = mapped_column(ForeignKey("loads.id", ondelete="RESTRICT"), index=True)
    outbound_id: Mapped[int] = mapped_column(ForeignKey("outbound_orders.id", ondelete="RESTRICT"), index=True)
    inventory_allocation_id: Mapped[int] = mapped_column(ForeignKey("outbound_inventory_allocations.id", ondelete="RESTRICT"))
    carton_qty: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    pallet_qty: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    operation_id: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class LoadDispatchPlan(Base, TimestampMixin):
    __tablename__ = "load_dispatch_plans"
    __table_args__ = (
        UniqueConstraint("load_id", "version", name="uq_load_dispatch_plan_version"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("status IN ('DRAFT', 'FINAL')", name="valid_status"),
        CheckConstraint("content_revision >= 0", name="content_revision_nonnegative"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    load_id: Mapped[int] = mapped_column(ForeignKey("loads.id", ondelete="RESTRICT"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12))
    content_revision: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    finalized_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class LoadDispatchPlanLine(Base, TimestampMixin):
    __tablename__ = "load_dispatch_plan_lines"
    __table_args__ = (
        UniqueConstraint("plan_id", "allocation_id", name="uq_load_dispatch_plan_allocation"),
        CheckConstraint("carton_qty BETWEEN 0 AND 9999999999.99", name="cartons_valid"),
        CheckConstraint("pallet_qty BETWEEN 0 AND 9999999999.99", name="pallets_valid"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("load_dispatch_plans.id", ondelete="RESTRICT"), index=True)
    allocation_id: Mapped[int] = mapped_column(ForeignKey("load_allocations.id", ondelete="RESTRICT"))
    carton_qty: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    pallet_qty: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class LoadDispatchExecution(Base, TimestampMixin):
    __tablename__ = "load_dispatch_executions"
    id: Mapped[int] = mapped_column(primary_key=True)
    load_id: Mapped[int] = mapped_column(ForeignKey("loads.id", ondelete="RESTRICT"), unique=True)
    operation_id: Mapped[str] = mapped_column(String(64), unique=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("load_dispatch_plans.id", ondelete="RESTRICT"))
    content_revision: Mapped[int] = mapped_column(Integer)
    performed_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
