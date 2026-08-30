from datetime import datetime
from pydantic import BaseModel, Field

class WorkOrderCreate(BaseModel):
    work_order_type: str
    warehouse_id: int
    load_id: int|None = None; outbound_id: int|None = None; picking_list_id: int|None = None; container_tracking_id: int|None = None
    priority: str = 'NORMAL'; assigned_to: int|None = None; assigned_team: str|None = Field(None, max_length=100); scheduled_at: datetime|None = None; notes: str|None = None
class WorkOrderUpdate(BaseModel):
    priority: str|None = None; assigned_to: int|None = None; assigned_team: str|None = Field(None, max_length=100); scheduled_at: datetime|None = None; notes: str|None = None
class WorkOrderStatusUpdate(BaseModel): status: str
class WorkOrderRead(BaseModel):
    id:int; work_order_no:str; work_order_type:str; status:str; warehouse_id:int; load_id:int|None; outbound_id:int|None; picking_list_id:int|None; container_tracking_id:int|None; priority:str; assigned_to:int|None; assigned_team:str|None; assignee_name:str|None=None; scheduled_at:datetime|None; started_at:datetime|None; completed_at:datetime|None; notes:str|None; created_by:int; created_at:datetime; updated_at:datetime
