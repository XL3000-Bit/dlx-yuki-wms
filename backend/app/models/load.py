import enum
from datetime import datetime

from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class LoadStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    READY = "READY"
    DISPATCHED = "DISPATCHED"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"


class Load(TimestampMixin, Base):
    __tablename__ = "loads"
    id: Mapped[int] = mapped_column(primary_key=True)
    load_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True)
    carrier_id: Mapped[int | None] = mapped_column(ForeignKey("carriers.id", ondelete="RESTRICT"), index=True)
    status: Mapped[LoadStatus] = mapped_column(Enum(LoadStatus, name="load_status"), default=LoadStatus.PLANNED, index=True)
    appointment_reference: Mapped[str | None] = mapped_column(String(100))
    appointment_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    destination_name: Mapped[str | None] = mapped_column(String(200))
    destination_address: Mapped[str | None] = mapped_column(Text)
    driver_name: Mapped[str | None] = mapped_column(String(100))
    driver_phone: Mapped[str | None] = mapped_column(String(50))
    tractor_no: Mapped[str | None] = mapped_column(String(50))
    trailer_no: Mapped[str | None] = mapped_column(String(50))
    seal_no: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    warehouse = relationship("Warehouse")
    carrier = relationship("Carrier")
    creator = relationship("User")
    outbounds = relationship("OutboundOrder", back_populates="load")
    work_orders = relationship("WorkOrder", back_populates="load")
    operational_exceptions = relationship("OperationalException", back_populates="load")
    __table_args__ = (Index("ix_loads_status_warehouse", "status", "warehouse_id"),)


class StageTransaction(TimestampMixin, Base):
    __tablename__ = "stage_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    load_id: Mapped[int] = mapped_column(ForeignKey("loads.id", ondelete="RESTRICT"), index=True)
    outbound_id: Mapped[int] = mapped_column(ForeignKey("outbound_orders.id", ondelete="RESTRICT"), index=True)
    picking_item_id: Mapped[int] = mapped_column(ForeignKey("picking_list_items.id", ondelete="RESTRICT"), index=True)
    staging_location_id: Mapped[int] = mapped_column(ForeignKey("warehouse_locations.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    quantity_unit: Mapped[str] = mapped_column(String(20))
    client_operation_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    performed_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)


class LoadVerificationTransaction(TimestampMixin, Base):
    __tablename__ = "load_verification_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    verification_run_id: Mapped[str] = mapped_column(String(36), index=True)
    load_id: Mapped[int] = mapped_column(ForeignKey("loads.id", ondelete="RESTRICT"), index=True)
    transaction_type: Mapped[str] = mapped_column(String(12))
    outbound_id: Mapped[int | None] = mapped_column(ForeignKey("outbound_orders.id", ondelete="RESTRICT"), index=True)
    picking_item_id: Mapped[int | None] = mapped_column(ForeignKey("picking_list_items.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    quantity_unit: Mapped[str | None] = mapped_column(String(20))
    result: Mapped[str] = mapped_column(String(20))
    client_operation_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    manifest_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    performed_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
