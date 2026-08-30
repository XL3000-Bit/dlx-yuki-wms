from datetime import datetime
from pydantic import BaseModel, Field


class ExceptionCreate(BaseModel):
    exception_type: str; severity: str = "MEDIUM"; title: str = Field(min_length=1, max_length=200); description: str = Field(min_length=1)
    warehouse_id: int; outbound_id: int | None = None; load_id: int | None = None; container_tracking_id: int | None = None
    picking_list_id: int | None = None; bol_id: int | None = None; work_order_id: int | None = None
    assigned_to: int | None = None; assigned_team: str | None = Field(None, max_length=100)


class ExceptionUpdate(BaseModel):
    severity: str | None = None; description: str | None = Field(None, min_length=1); resolution: str | None = None


class ExceptionAssign(BaseModel):
    assigned_to: int | None = None; assigned_team: str | None = Field(None, max_length=100)


class ExceptionStatusUpdate(BaseModel): status: str
class ExceptionResolve(BaseModel): resolution: str = Field(min_length=1)


class ExceptionRead(BaseModel):
    id: int; exception_no: str; exception_type: str; severity: str; status: str; title: str; description: str; warehouse_id: int
    outbound_id: int | None; load_id: int | None; container_tracking_id: int | None; picking_list_id: int | None; bol_id: int | None
    assigned_to: int | None; assigned_team: str | None; assignee_name: str | None; reported_at: datetime; reported_by: int
    resolved_at: datetime | None; resolved_by: int | None; resolution: str | None; created_at: datetime; updated_at: datetime
    related: dict; work_orders: list[dict]


class ExceptionEventRead(BaseModel):
    id: int; event_type: str; actor_user_id: int | None; actor_name: str; field_name: str | None; old_value: str | None; new_value: str | None; message: str | None; created_at: datetime


class ExceptionWorkOrderCreate(BaseModel):
    assigned_to: int | None = None; assigned_team: str | None = Field(None, max_length=100); notes: str | None = None
