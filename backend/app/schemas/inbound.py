from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, computed_field
from app.models.inbound import InboundStatus
from app.utils.business_time import get_business_today

class NamedRef(BaseModel): id:int; code:str; name:str
class UserRef(BaseModel): id:int; display_name:str
class InboundBase(BaseModel):
    container_number:str=Field(min_length=1,max_length=50);customer_id:int|None=None;warehouse_id:int;unload_date:date|None=None;received_date:date|None=None;fc_code:str|None=Field(None,max_length=20);marking:str|None=Field(None,max_length=100);pallet_qty:Decimal=Field(Decimal("0"),ge=0);carton_qty:Decimal=Field(Decimal("0"),ge=0);weight_lbs:Decimal|None=Field(None,ge=0);cbm:Decimal|None=Field(None,ge=0);location_id:int|None=None;status:InboundStatus=InboundStatus.PENDING;remark:str|None=None
class InboundCreate(InboundBase): pass
class InboundUpdate(InboundBase): pass
class InboundRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:int;inbound_no:str;container_number:str;unload_date:date|None;received_date:date|None;fc_code:str|None;marking:str|None;pallet_qty:Decimal;carton_qty:Decimal;weight_lbs:Decimal|None;cbm:Decimal|None;status:int;remark:str|None;created_at:datetime;updated_at:datetime
    customer:NamedRef|None;warehouse:NamedRef;location:NamedRef|None;created_by:UserRef
    source_metadata:dict|None=None
    inventory_created:bool=False;inventory_lot_id:int|None=None
    @computed_field
    @property
    def status_name(self)->str:
        if self.source_metadata and self.source_metadata.get("mode") == "HISTORY_PENDING_RECONCILIATION":
            return "历史记录 · 库存待核对"
        return InboundStatus(self.status).name.replace("_"," ").title()
    @computed_field
    @property
    def aging_days(self)->int|None:
        base=self.received_date or self.unload_date
        return max(0,(get_business_today()-base).days) if base else None
class PaginationMeta(BaseModel):page:int;per_page:int;total:int;total_pages:int
class InboundListResponse(BaseModel):data:list[InboundRead];meta:PaginationMeta
class InboundListParams(BaseModel):
    page:int=Field(1,ge=1);per_page:int=Field(20,ge=1,le=100);q:str|None=None;container_number:str|None=None;customer_id:int|None=None;warehouse_id:int|None=None;fc_code:str|None=None;location_id:int|None=None;status:InboundStatus|None=None;unload_date_from:date|None=None;unload_date_to:date|None=None;received_date_from:date|None=None;received_date_to:date|None=None;sort_by:str="id";sort_order:Literal["asc","desc"]="desc"
