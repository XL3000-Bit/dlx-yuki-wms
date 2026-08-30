from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict

Stage = Literal["waiting_picking", "waiting_appointment", "waiting_outbound", "completed", "exception"]

class WorkbenchRow(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:int;fba_no:str;shipment_id:str|None=None;st_number:str|None=None;po_number:str|None=None;reference_no:str|None=None
    customer_id:int|None=None;customer:str|None=None;warehouse_id:int;warehouse:str;amazon_fc_code:str;amazon_fc_name:str|None=None;fc_address_missing:bool
    container_count:int=0;containers_preview:list[str]=[];location_count:int=0;locations_preview:list[str]=[]
    total_pallet_qty:Decimal=Decimal(0);total_carton_qty:Decimal=Decimal(0);total_weight_lbs:Decimal=Decimal(0);total_cbm:Decimal=Decimal(0)
    oldest_inbound_date:date|None=None;max_aging_days:int|None=None;priority_level:str|None=None;priority_label:str|None=None;priority_range:str|None=None;priority_rank:int=0
    inbound_date:date|None=None;warehouse_days:int|None=None;earliest_outbound_date:date|None=None;outbound_days_remaining:int|None=None;dispatch_priority:str="NORMAL";dispatch_priority_rank:int=3
    appointment_time:datetime|None=None;scheduled_pickup_at:datetime|None=None
    picking_count:int=0;picking_id:int|None=None;picking_no:str|None=None;picking_status:int|None=None
    bol_id:int|None=None;bol_no:str|None=None;bol_status:int|None=None
    outbound_id:int|None=None;outbound_no:str|None=None;outbound_status:int|None=None
    workbench_stage:Stage;workbench_stage_name:str;has_exception:bool=False;status:int;created_at:datetime;updated_at:datetime

class WorkbenchSummary(BaseModel):
    task_count:int=0;total_pallet_qty:Decimal=Decimal(0);total_carton_qty:Decimal=Decimal(0);total_weight_lbs:Decimal=Decimal(0);total_cbm:Decimal=Decimal(0);average_aging_days:Decimal|None=None

class WorkbenchResponse(BaseModel):
    data:list[WorkbenchRow];meta:dict[str,Any];summary:WorkbenchSummary;stage_counts:dict[str,int];permissions:dict[str,bool]

class WorkbenchDetail(BaseModel):
    basic:dict[str,Any];inventory_sources:list[dict[str,Any]];picking:list[dict[str,Any]];bol:dict[str,Any]|None=None;outbound:dict[str,Any]|None=None;audit:list[dict[str,Any]];workflow:list[dict[str,Any]];permissions:dict[str,bool]

class BatchActionRequest(BaseModel):
    action:str
    fba_ids:list[int]

class BatchActionResult(BaseModel):
    fba_id:int;status:str;reason:str|None=None;outbound_id:int|None=None;picking_id:int|None=None;bol_id:int|None=None

class BatchActionResponse(BaseModel):
    action:str;successful:int;skipped:int;failed:int;results:list[BatchActionResult]
