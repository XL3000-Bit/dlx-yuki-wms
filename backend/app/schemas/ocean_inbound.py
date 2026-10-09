from decimal import Decimal
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OceanReceiptLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    version: int = Field(ge=0)
    received_qty: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    inbound_pallets: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    location_id: int | None = None
    estimated_pallets: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    markup_pallets: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    load_type: Literal["FBA", "FBM"] | None = None
    memo: str = Field(default="", max_length=4000)
    feedback: str = Field(default="", max_length=4000)


class OceanReceiptBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lines: list[OceanReceiptLine] = Field(min_length=1, max_length=500)


class OceanPutawayLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    version: int = Field(ge=0)


class OceanPutawayBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lines: list[OceanPutawayLine] = Field(min_length=1, max_length=500)


class OceanShipmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=0)
    transport_status: Literal['TBD', '待提待拆', '可提未提', '已提待拆', '在拆', '已提已拆'] = 'TBD'
    scheduled_delivery_date: datetime | date | None = None
    pod_eta: date | None = None
    appointment: str = Field(default='', max_length=200)
    size: str = Field(default='', max_length=50)
    trucker: str = Field(default='', max_length=200)
    container_status: str = Field(default='', max_length=100)
    team: str = Field(default='', max_length=100)
    released: bool = False
    printed: bool = False
    empty_reported: bool = False
    outbound_fully_pod: bool = False
    # Reference list status is separate from receiving/inventory state. No inferred mapping.
    list_status: Literal['Upcoming Inbound', "Today's Inbound", 'Overdue Inbound', 'Completed Inbound', 'Canceled Inbound'] | None = None
    ir_eta: date | None = None
    urgent: bool = False
    trouble_status: str = Field(default='', max_length=200)
    trouble_count: int = Field(default=0, ge=0)
    terminal_ready_date: date | None = None
    unloading_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    unloading_remark: str = Field(default='', max_length=1024)
    operator: str = Field(default='', max_length=100)
