from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.scan_execution import ScanOperationType


class ScanSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warehouse_id: int
    operation_type: ScanOperationType
    outbound_id: int | None = None
    picking_id: int | None = None
    picking_ref: str | None = Field(default=None, min_length=1, max_length=24)
    load_id: int | None = None


class ScanValueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(max_length=255)


class PickConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    client_operation_id: str = Field(min_length=1, max_length=64)


class ScanCounters(BaseModel):
    total: int = 0
    accepted: int = 0
    duplicate: int = 0
    rejected: int = 0
    result_counts: dict[str, int] = Field(default_factory=dict)


class ScanSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_no: str
    warehouse_id: int
    operation_type: str
    user_id: int
    outbound_id: int | None = None
    picking_id: int | None = None
    load_id: int | None = None
    current_location_id: int | None = None
    current_picking_item_id: int | None = None
    status: str
    last_scan_at: datetime | None = None
    completed_at: datetime | None = None
    canceled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ScanEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    raw_value: str
    normalized_value: str
    event_type: str
    client_operation_id: str | None = None
    scan_type: str
    result: str
    matched_entity_type: str | None = None
    matched_entity_id: int | None = None
    location_id: int | None = None
    picking_item_id: int | None = None
    quantity: Decimal | None = None
    quantity_unit: str | None = None
    reference_value: str | None = None
    message: str
    scanned_by: int
    scanned_at: datetime


class PickingExecutionSummary(BaseModel):
    picking_no: str
    outbound_no: str
    picking_status: str
    current_step: Literal[
        "EXPECT_LOCATION", "EXPECT_LOT", "EXPECT_QUANTITY_CONFIRMATION"
    ]
    quantity_unit: str | None = None
    required_qty: Decimal = Decimal("0")
    picked_qty: Decimal = Decimal("0")
    remaining_qty: Decimal = Decimal("0")
    current_location_code: str | None = None
    current_lot_no: str | None = None
    current_item_required_qty: Decimal | None = None
    current_item_picked_qty: Decimal | None = None
    current_item_remaining_qty: Decimal | None = None
    current_item_available_qty: Decimal | None = None
    locations_visited: int = 0
    lots_picked: int = 0


class ScanSessionResponse(BaseModel):
    session: ScanSessionRead
    counters: ScanCounters
    picking_summary: PickingExecutionSummary | None = None


class ScanEventListResponse(BaseModel):
    data: list[ScanEventRead]
    total: int
    limit: int
    offset: int


class ScanResultResponse(BaseModel):
    event: ScanEventRead
    session: ScanSessionRead
    counters: ScanCounters
    recent_events: list[ScanEventRead]
    picking_summary: PickingExecutionSummary | None = None
