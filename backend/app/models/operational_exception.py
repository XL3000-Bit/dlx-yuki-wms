import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ExceptionType(str, enum.Enum):
    INVENTORY = "INVENTORY"; PICKING = "PICKING"; OUTBOUND = "OUTBOUND"; CONTAINER = "CONTAINER"
    DOCUMENT = "DOCUMENT"; APPOINTMENT = "APPOINTMENT"; WAREHOUSE = "WAREHOUSE"; DATA = "DATA"; OTHER = "OTHER"


class ExceptionSeverity(str, enum.Enum):
    LOW = "LOW"; MEDIUM = "MEDIUM"; HIGH = "HIGH"; CRITICAL = "CRITICAL"


class ExceptionStatus(str, enum.Enum):
    OPEN = "OPEN"; INVESTIGATING = "INVESTIGATING"; RESOLVED = "RESOLVED"; CANCELED = "CANCELED"


class OperationalException(TimestampMixin, Base):
    __tablename__ = "operational_exceptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    exception_no: Mapped[str] = mapped_column(String(32))
    exception_type: Mapped[ExceptionType] = mapped_column(Enum(ExceptionType, name="operational_exception_type"), index=True)
    severity: Mapped[ExceptionSeverity] = mapped_column(Enum(ExceptionSeverity, name="operational_exception_severity"), default=ExceptionSeverity.MEDIUM, index=True)
    status: Mapped[ExceptionStatus] = mapped_column(Enum(ExceptionStatus, name="operational_exception_status"), default=ExceptionStatus.OPEN, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True)
    outbound_id: Mapped[int | None] = mapped_column(ForeignKey("outbound_orders.id", ondelete="SET NULL"), index=True)
    load_id: Mapped[int | None] = mapped_column(ForeignKey("loads.id", ondelete="SET NULL"), index=True)
    container_tracking_id: Mapped[int | None] = mapped_column(ForeignKey("container_trackings.id", ondelete="SET NULL"), index=True)
    picking_list_id: Mapped[int | None] = mapped_column(ForeignKey("picking_lists.id", ondelete="SET NULL"), index=True)
    bol_id: Mapped[int | None] = mapped_column(ForeignKey("bols.id", ondelete="SET NULL"), index=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    assigned_team: Mapped[str | None] = mapped_column(String(100), index=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reported_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolution: Mapped[str | None] = mapped_column(Text)

    warehouse = relationship("Warehouse"); outbound = relationship("OutboundOrder"); load = relationship("Load", back_populates="operational_exceptions")
    container_tracking = relationship("ContainerTracking"); picking_list = relationship("PickingList"); bol = relationship("BOL")
    assignee = relationship("User", foreign_keys=[assigned_to]); reporter = relationship("User", foreign_keys=[reported_by]); resolver = relationship("User", foreign_keys=[resolved_by])
    events = relationship("OperationalExceptionEvent", back_populates="operational_exception", cascade="all, delete-orphan", order_by="OperationalExceptionEvent.created_at.desc()")
    work_orders = relationship("WorkOrder", back_populates="operational_exception")
    __table_args__ = (
        UniqueConstraint("exception_no"),
        Index("ix_operational_exceptions_exception_no", "exception_no"),
        Index("ix_operational_exceptions_scope", "warehouse_id", "status", "severity"),
    )


class OperationalExceptionEvent(Base):
    __tablename__ = "operational_exception_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    operational_exception_id: Mapped[int] = mapped_column(ForeignKey("operational_exceptions.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    field_name: Mapped[str | None] = mapped_column(String(50))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    operational_exception = relationship("OperationalException", back_populates="events")
    actor = relationship("User")
    __table_args__ = (Index("ix_operational_exception_events_timeline", "operational_exception_id", "created_at", "id"),)
