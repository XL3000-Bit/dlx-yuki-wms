import enum
from datetime import datetime

from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, event, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ScanOperationType(str, enum.Enum):
    PICK = "PICK"
    STAGE = "STAGE"
    LOAD_VERIFY = "LOAD_VERIFY"


class ScanSessionStatus(str, enum.Enum):
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"


class ScanType(str, enum.Enum):
    UNKNOWN = "UNKNOWN"
    LOCATION = "LOCATION"
    OUTBOUND = "OUTBOUND"
    FBA = "FBA"
    CONTAINER = "CONTAINER"
    PICKING = "PICKING"
    INVENTORY_LOT = "INVENTORY_LOT"


class ScanResult(str, enum.Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"
    NOT_FOUND = "NOT_FOUND"
    WRONG_WAREHOUSE = "WRONG_WAREHOUSE"
    WRONG_OUTBOUND = "WRONG_OUTBOUND"
    WRONG_LOCATION = "WRONG_LOCATION"
    INVALID_STATE = "INVALID_STATE"
    PICK_SOURCE_MISMATCH = "PICK_SOURCE_MISMATCH"


class ScanEventType(str, enum.Enum):
    GENERIC_SCANNED = "GENERIC_SCANNED"
    LOCATION_SCANNED = "LOCATION_SCANNED"
    LOT_SCANNED = "LOT_SCANNED"
    PICK_CONFIRMED = "PICK_CONFIRMED"


class PickQuantityUnit(str, enum.Enum):
    PALLET = "PALLET"
    CARTON = "CARTON"


class ScanSession(TimestampMixin, Base):
    __tablename__ = "scan_sessions"
    __table_args__ = (
        CheckConstraint(
            "operation_type IN ('PICK', 'STAGE', 'LOAD_VERIFY')",
            name="operation_type_values",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'COMPLETED', 'CANCELED')",
            name="status_values",
        ),
        Index("ix_scan_sessions_warehouse_status", "warehouse_id", "status"),
        Index("ix_scan_sessions_user_status", "user_id", "status"),
        Index(
            "uq_scan_sessions_open_pick_picking",
            "picking_id",
            unique=True,
            postgresql_where=text(
                "operation_type = 'PICK' AND status = 'OPEN' AND picking_id IS NOT NULL"
            ),
            sqlite_where=text(
                "operation_type = 'PICK' AND status = 'OPEN' AND picking_id IS NOT NULL"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True
    )
    operation_type: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    outbound_id: Mapped[int | None] = mapped_column(
        ForeignKey("outbound_orders.id", ondelete="RESTRICT"), index=True
    )
    picking_id: Mapped[int | None] = mapped_column(
        ForeignKey("picking_lists.id", ondelete="RESTRICT"), index=True
    )
    load_id: Mapped[int | None] = mapped_column(
        ForeignKey("loads.id", ondelete="RESTRICT"), index=True
    )
    current_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_locations.id", ondelete="RESTRICT"), index=True
    )
    current_picking_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("picking_list_items.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=ScanSessionStatus.OPEN.value, server_default="OPEN", index=True
    )
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    warehouse = relationship("Warehouse")
    user = relationship("User")
    outbound = relationship("OutboundOrder")
    picking = relationship("PickingList")
    load = relationship("Load")
    current_location = relationship("WarehouseLocation", foreign_keys=[current_location_id])
    current_picking_item = relationship("PickingListItem", foreign_keys=[current_picking_item_id])
    events = relationship(
        "ScanEvent",
        back_populates="session",
        order_by="ScanEvent.id",
        passive_deletes=True,
    )


class ScanEvent(Base):
    __tablename__ = "scan_events"
    __table_args__ = (
        CheckConstraint(
            "scan_type IN ('UNKNOWN', 'LOCATION', 'OUTBOUND', 'FBA', "
            "'CONTAINER', 'PICKING', 'INVENTORY_LOT')",
            name="scan_type_values",
        ),
        CheckConstraint(
            "result IN ('ACCEPTED', 'REJECTED', 'DUPLICATE', 'NOT_FOUND', "
            "'WRONG_WAREHOUSE', 'WRONG_OUTBOUND', 'WRONG_LOCATION', 'INVALID_STATE', "
            "'PICK_SOURCE_MISMATCH')",
            name="result_values",
        ),
        CheckConstraint(
            "event_type IN ('GENERIC_SCANNED', 'LOCATION_SCANNED', 'LOT_SCANNED', "
            "'PICK_CONFIRMED')",
            name="event_type_values",
        ),
        CheckConstraint(
            "quantity_unit IS NULL OR quantity_unit IN ('PALLET', 'CARTON')",
            name="quantity_unit_values",
        ),
        CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="quantity_positive",
        ),
        Index("ix_scan_events_session_scanned", "session_id", "scanned_at", "id"),
        Index("ix_scan_events_session_normalized", "session_id", "normalized_value"),
        Index(
            "uq_scan_events_session_client_operation",
            "session_id",
            "client_operation_id",
            unique=True,
            postgresql_where=text("client_operation_id IS NOT NULL"),
            sqlite_where=text("client_operation_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("scan_sessions.id", ondelete="RESTRICT"), index=True
    )
    raw_value: Mapped[str] = mapped_column(String(255))
    normalized_value: Mapped[str] = mapped_column(String(255), index=True)
    event_type: Mapped[str] = mapped_column(
        String(30), default=ScanEventType.GENERIC_SCANNED.value,
        server_default=ScanEventType.GENERIC_SCANNED.value,
    )
    client_operation_id: Mapped[str | None] = mapped_column(String(64))
    scan_type: Mapped[str] = mapped_column(String(30))
    result: Mapped[str] = mapped_column(String(30), index=True)
    matched_entity_type: Mapped[str | None] = mapped_column(String(40))
    matched_entity_id: Mapped[int | None] = mapped_column(index=True)
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouse_locations.id", ondelete="RESTRICT"), index=True
    )
    picking_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("picking_list_items.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    quantity_unit: Mapped[str | None] = mapped_column(String(20))
    reference_value: Mapped[str | None] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    scanned_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session = relationship("ScanSession", back_populates="events")
    location = relationship("WarehouseLocation")
    picking_item = relationship("PickingListItem")
    scanner = relationship("User")


def _prevent_scan_event_mutation(*_args: object, **_kwargs: object) -> None:
    raise ValueError("ScanEvent rows are append-only")


event.listen(ScanEvent, "before_update", _prevent_scan_event_mutation)
event.listen(ScanEvent, "before_delete", _prevent_scan_event_mutation)
