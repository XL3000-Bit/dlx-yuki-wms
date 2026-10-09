from datetime import datetime
from pydantic import BaseModel, Field

class WorkOrderCreate(BaseModel):
    work_order_type: str
    warehouse_id: int
    load_id: int|None = None; outbound_id: int|None = None; picking_list_id: int|None = None; container_tracking_id: int|None = None
    priority: str = 'NORMAL'; assigned_to: int|None = None; assigned_team: str|None = Field(None, max_length=100); scheduled_at: datetime|None = None; notes: str|None = None
class WorkOrderUpdate(BaseModel):
    priority: str|None = None; assigned_to: int|None = None; assigned_team: str|None = Field(None, max_length=100); scheduled_at: datetime|None = None; notes: str|None = None
class WorkOrderAssign(BaseModel):
    assigned_to: int|None = None
    assigned_team: str|None = Field(None, max_length=100)
class WorkOrderStatusUpdate(BaseModel): status: str
class WorkOrderRead(BaseModel):
    id:int; work_order_no:str; work_order_type:str; status:str; warehouse_id:int; load_id:int|None; outbound_id:int|None; picking_list_id:int|None; container_tracking_id:int|None; operational_exception_id:int|None=None; priority:str; assigned_to:int|None; assigned_team:str|None; assignee_name:str|None=None; scheduled_at:datetime|None; started_at:datetime|None; completed_at:datetime|None; notes:str|None; created_by:int; created_at:datetime; updated_at:datetime

class WorkOrderEventActor(BaseModel):
    id: int
    username: str
    display_name: str

class WorkOrderEventRead(BaseModel):
    id: int; event_type: str; field_name: str|None; old_value: str|None; new_value: str|None; message: str|None
    from_status: str|None; to_status: str|None; actor_user_id: int|None; actor_name: str; actor: WorkOrderEventActor|None
    assigned_to_before: int|None; assigned_to_after: int|None; assigned_team_before: str|None; assigned_team_after: str|None
    priority_before: str|None; priority_after: str|None; note: str|None; created_at: datetime

class WorkOrderEventList(BaseModel):
    data: list[WorkOrderEventRead]
    total: int
    limit: int
    offset: int
