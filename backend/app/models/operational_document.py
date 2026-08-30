import enum
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class DocumentType(str, enum.Enum):
    BOL = "BOL"; POD = "POD"; DELIVERY_RECEIPT = "DELIVERY_RECEIPT"; WAREHOUSE = "WAREHOUSE"
    EXCEPTION_ATTACHMENT = "EXCEPTION_ATTACHMENT"; GENERAL = "GENERAL"


class DocumentStatus(str, enum.Enum):
    DRAFT = "DRAFT"; AVAILABLE = "AVAILABLE"; SUPERSEDED = "SUPERSEDED"; ARCHIVED = "ARCHIVED"


class OperationalDocument(TimestampMixin, Base):
    __tablename__ = "operational_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_no: Mapped[str] = mapped_column(String(40))
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType, name="operational_document_type"), index=True)
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus, name="operational_document_status"), default=DocumentStatus.DRAFT, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    original_filename: Mapped[str] = mapped_column(String(255), index=True)
    content_type: Mapped[str] = mapped_column(String(120))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    storage_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    is_generated: Mapped[bool] = mapped_column(default=False)
    title: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), index=True)
    load_id: Mapped[int | None] = mapped_column(ForeignKey("loads.id", ondelete="SET NULL"), index=True)
    outbound_id: Mapped[int | None] = mapped_column(ForeignKey("outbound_orders.id", ondelete="SET NULL"), index=True)
    bol_id: Mapped[int | None] = mapped_column(ForeignKey("bols.id", ondelete="SET NULL"), index=True)
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id", ondelete="SET NULL"), index=True)
    operational_exception_id: Mapped[int | None] = mapped_column(ForeignKey("operational_exceptions.id", ondelete="SET NULL"), index=True)
    container_tracking_id: Mapped[int | None] = mapped_column(ForeignKey("container_trackings.id", ondelete="SET NULL"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    warehouse = relationship("Warehouse"); customer = relationship("Customer"); load = relationship("Load")
    outbound = relationship("OutboundOrder"); bol = relationship("BOL"); work_order = relationship("WorkOrder")
    operational_exception = relationship("OperationalException"); container_tracking = relationship("ContainerTracking")
    creator = relationship("User", foreign_keys=[created_by]); events = relationship("DocumentEvent", back_populates="document", order_by="DocumentEvent.created_at.desc()", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint("document_no"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("load_id IS NOT NULL OR outbound_id IS NOT NULL OR bol_id IS NOT NULL OR work_order_id IS NOT NULL OR operational_exception_id IS NOT NULL OR container_tracking_id IS NOT NULL", name="business_link_required"),
        Index("ix_operational_documents_scope_status", "warehouse_id", "status", "document_type"),
        Index("ix_operational_documents_document_no", "document_no"),
    )


class DocumentEvent(Base):
    __tablename__ = "document_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("operational_documents.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    document = relationship("OperationalDocument", back_populates="events"); actor = relationship("User")
    __table_args__ = (Index("ix_document_events_timeline", "document_id", "created_at", "id"),)
