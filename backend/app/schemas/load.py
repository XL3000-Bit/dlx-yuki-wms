from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class LoadCreate(BaseModel):
    warehouse_id: int
    carrier_id: int | None = None
    appointment_reference: str | None = Field(None, max_length=100)
    appointment_time: datetime | None = None
    destination_name: str | None = Field(None, max_length=200)
    destination_address: str | None = None
    driver_name: str | None = Field(None, max_length=100)
    driver_phone: str | None = Field(None, max_length=50)
    tractor_no: str | None = Field(None, max_length=50)
    trailer_no: str | None = Field(None, max_length=50)
    seal_no: str | None = Field(None, max_length=50)
    notes: str | None = None
    outbound_ids: list[int] = Field(default_factory=list, max_length=100)


class LoadUpdate(BaseModel):
    carrier_id: int | None = None
    appointment_reference: str | None = Field(None, max_length=100)
    appointment_time: datetime | None = None
    destination_name: str | None = Field(None, max_length=200)
    destination_address: str | None = None
    driver_name: str | None = Field(None, max_length=100)
    driver_phone: str | None = Field(None, max_length=50)
    tractor_no: str | None = Field(None, max_length=50)
    trailer_no: str | None = Field(None, max_length=50)
    seal_no: str | None = Field(None, max_length=50)
    notes: str | None = None


class LoadStatusUpdate(BaseModel):
    status: str


class LoadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; load_no: str; warehouse_id: int; warehouse: dict | None = None; carrier_id: int | None = None; carrier: dict | None = None
    status: str; appointment_reference: str | None = None; appointment_time: datetime | None = None; destination_name: str | None = None; destination_address: str | None = None
    driver_name: str | None = None; driver_phone: str | None = None; tractor_no: str | None = None; trailer_no: str | None = None; seal_no: str | None = None; notes: str | None = None
    outbound_count: int = 0; total_pallet_qty: Decimal = Decimal("0"); total_carton_qty: Decimal = Decimal("0"); total_weight_lbs: Decimal = Decimal("0"); total_cbm: Decimal = Decimal("0")
    outbounds: list[dict] = []
    work_orders: list[dict] = []
    active_exception_count: int = 0
    active_exceptions: list[dict] = Field(default_factory=list)
    created_at: datetime; updated_at: datetime
