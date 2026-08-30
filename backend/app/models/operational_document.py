import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class DocumentType(str, enum.Enum):
    BOL = "BOL"
    POD = "POD"
    DELIVERY_RECEIPT = "DELIVERY_RECEIPT"
    WAREHOUSE = "WAREHOUSE"
    EXCEPTION_ATTACHMENT = "EXCEPTION_ATTACHMENT"
    GENERAL = "GENERAL"


class DocumentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    AVAILABLE = "AVAILABLE"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"
    PENDING = "PENDING"
    RECEIVED = "RECEIVED"


class OperationalDocument(TimestampMixin, Base):
    __tablename__ = "operational_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType, name="operational_document_type"), index=True)
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus, name="operational_document_status"), default=DocumentStatus.AVAILABLE, index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    original_file_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    file_size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(500))
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True)
    load_id: Mapped[int | None] = mapped_column(ForeignKey("loads.id", ondelete="SET NULL"), index=True)
    outbound_id: Mapped[int | None] = mapped_column(ForeignKey("outbound_orders.id", ondelete="SET NULL"), index=True)
    bol_id: Mapped[int | None] = mapped_column(ForeignKey("bols.id", ondelete="SET NULL"), index=True)
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id", ondelete="SET NULL"), index=True)
    exception_id: Mapped[int | None] = mapped_column(ForeignKey("operational_exceptions.id", ondelete="SET NULL"), index=True)
    container_tracking_id: Mapped[int | None] = mapped_column(ForeignKey("container_trackings.id", ondelete="SET NULL"), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    warehouse = relationship("Warehouse")
    load = relationship("Load")
    outbound = relationship("OutboundOrder")
    bol = relationship("BOL")
    work_order = relationship("WorkOrder")
    exception = relationship("OperationalException")
    container_tracking = relationship("ContainerTracking")
    uploader = relationship("User")
    events = relationship("DocumentEvent", back_populates="document", cascade="all, delete-orphan", order_by="DocumentEvent.created_at.desc()")
    __table_args__ = (
        Index("ix_operational_documents_type_status", "document_type", "status"),
        Index("ix_operational_documents_uploaded", "uploaded_at"),
    )


class DocumentEvent(Base):
    __tablename__ = "document_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("operational_documents.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    document = relationship("OperationalDocument", back_populates="events")
    actor = relationship("User")
    __table_args__ = (Index("ix_document_events_timeline", "document_id", "created_at", "id"),)
