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


class ThreePLDispatchSummary(BaseModel):
    total: int
    ready: int
    at_risk: int
    blocked: int
    overdue: int
    unassigned: int


class ThreePLDispatchTask(BaseModel):
    id: int
    reference: str
    customer_id: int | None
    customer_code: str
    customer_name: str
    warehouse_id: int
    warehouse_code: str
    status: int
    status_name: str
    priority: str
    priority_reason: str
    queue_state: str
    due_at: datetime | None
    is_overdue: bool
    owner_name: str | None
    work_order_id: int | None
    work_order_no: str | None
    work_order_type: str | None
    exception_id: int | None
    exception_no: str | None
    exception_severity: str | None
    picking_id: int | None
    picking_no: str | None
    picking_status: int | None
    picking_status_name: str | None
    bol_id: int | None
    bol_no: str | None
    bol_status: int | None
    bol_status_name: str | None
    document_state: str
    blocker_code: str | None
    blocker_label: str | None
    blocker: str | None
    carrier_name: str | None
    action_target: str
    action_allowed: bool
    action_disabled_reason: str | None
    picking_download_url: str | None
    bol_download_url: str | None
    updated_at: datetime


class ThreePLDispatchQueue(BaseModel):
    generated_at: datetime
    summary_scope: str
    summary: ThreePLDispatchSummary
    page: int
    page_size: int
    total: int
    pages: int
    sort: str
    tasks: list[ThreePLDispatchTask]
