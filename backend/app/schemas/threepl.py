from datetime import date, datetime

from pydantic import BaseModel


class ThreePLMeta(BaseModel):
    generated_at: datetime
    date_from: date
    date_to: date
    customer_id: int | None
    warehouse_id: int | None
    storage_basis: str


class ThreePLSummary(BaseModel):
    active_clients: int
    inventory_pallets: float
    inventory_cartons: float
    inventory_cbm: float
    hold_pallets: float
    open_inbounds: int
    open_outbounds: int


class ThreePLUsage(BaseModel):
    receiving_orders: int
    receiving_pallets: float
    receiving_cartons: float
    outbound_orders: int
    outbound_pallets: float
    outbound_cartons: float
    storage_pallet_days: float


class ThreePLClientRow(BaseModel):
    customer_id: int
    customer_code: str
    customer_name: str
    contact_name: str | None
    email: str | None
    is_active: bool
    inventory_pallets: float
    inventory_cartons: float
    inventory_cbm: float
    hold_pallets: float
    open_inbounds: int
    open_outbounds: int
    completed_inbounds: int
    completed_outbounds: int
    oldest_inventory_days: int | None
    last_activity_at: datetime | None


class ThreePLAttentionItem(BaseModel):
    severity: str
    customer_id: int
    customer_code: str
    title: str
    detail: str
    target: str


class ThreePLOverview(BaseModel):
    meta: ThreePLMeta
    summary: ThreePLSummary
    usage: ThreePLUsage
    clients: list[ThreePLClientRow]
    attention: list[ThreePLAttentionItem]
