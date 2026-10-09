from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class BolDetails(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    carrier_id: int | None = None
    shipping_mode: Literal["53' FTL", 'LTL', "26' FTL", 'Floor loaded', "30' FTL"] = 'LTL'
    scheduled_pickup_time: datetime | None = None
    delivery_appointment_time: datetime | None = None
    estimated_transit_days: int | None = Field(default=None, ge=0, le=365)
    payment: Literal['', 'PREPAID', 'COLLECT', 'THIRTY PAIRTY'] = 'PREPAID'
    customer_reference: str = Field(default='', max_length=100)
    pickup_reference: str = Field(default='', max_length=100)
    delivery_reference: str = Field(default='', max_length=100)
    delivery_appointment: str = Field(default='', max_length=100)
    seal_number: str = Field(default='', max_length=100)
    pro_number: str = Field(default='', max_length=100)
    pickup_address: str = Field(default='', max_length=2000)
    delivery_address: str = Field(default='', max_length=2000)
    title_header: str = Field(default='', max_length=200)
    title_body: str = Field(default='', max_length=2000)
    billing_to: str = Field(default='', max_length=2000)
    remark: str = Field(default='', max_length=4000)
    customer_remark: str = Field(default='', max_length=4000)
    internal_remark: str = Field(default='', max_length=4000)
    pod_delivery_appointment: str = Field(default='', max_length=100)
    customer_dispatch_remark: str = Field(default='', max_length=4000)
    redirect_location: str = Field(default='', max_length=200)
    redirect_address: str = Field(default='', max_length=2000)
    urgent_level: Literal['No', 'Yes'] = 'No'


class BolCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    warehouse_id: int
    customer_id: int
    delivery_code: str = Field(min_length=1, max_length=20)
    details: BolDetails = Field(default_factory=BolDetails)


class VersionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)


class BolUpdate(VersionRequest):
    details: BolDetails


class LoadQuantity(BaseModel):
    model_config = ConfigDict(extra='forbid')
    inventory_lot_id: int
    pallet_qty: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    carton_qty: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    weight_lbs: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    cbm: Decimal = Field(ge=0, max_digits=14, decimal_places=4)


class LoadSelection(VersionRequest):
    inventory_lot_ids: list[int] = Field(default_factory=list, max_length=200)
    lines: list[LoadQuantity] = Field(default_factory=list, max_length=200)


class BolAction(VersionRequest):
    action: Literal['confirm', 'shipout', 'deliver', 'cancel']
    confirm_all_picked: bool = False
    lines: list[LoadQuantity] = Field(default_factory=list, max_length=200)
    request_id: str | None = Field(default=None, min_length=8, max_length=80)
    remark: str = Field(default='', max_length=4000)


class PodReview(VersionRequest):
    document_id: int
    result: Literal['Verified', 'Exception']
    remark: str = Field(default='', max_length=4000)


class PodBolSelection(VersionRequest):
    id: int = Field(gt=0)


class BatchPodUpload(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    ob_no: str = Field(min_length=1, max_length=100)
    bols: list[PodBolSelection] = Field(min_length=1, max_length=200)
    delivery_date: date
    delivery_appointment: str = Field(default='', max_length=100)


class DispatchMembership(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['join', 'remove']
    bols: list[PodBolSelection] = Field(min_length=1, max_length=200)
