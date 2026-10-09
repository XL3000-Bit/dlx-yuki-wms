from datetime import date,datetime
from decimal import Decimal
from pydantic import BaseModel,ConfigDict,Field
from app.schemas.inbound import NamedRef,PaginationMeta,UserRef

class FBABase(BaseModel):customer_id:int|None=None;warehouse_id:int;amazon_fc_code:str=Field(min_length=1,max_length=20);carrier_id:int|None=None;scheduled_pickup_at:datetime|None=None;appointment_time:datetime|None=None;reference_no:str|None=None;shipment_id:str|None=None;st_number:str|None=None;remark:str|None=None
class FBACreate(FBABase):pass
class FBAUpdate(FBABase):pass
class FBARead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:int;fba_no:str;customer:NamedRef|None;warehouse:NamedRef;amazon_fc_code:str;amazon_fc_name:str|None;amazon_fc_address:str|None;fc_address_missing:bool;status:int;status_name:str;carrier:NamedRef|None;scheduled_pickup_at:datetime|None;appointment_time:datetime|None;reference_no:str|None;shipment_id:str|None;st_number:str|None;remark:str|None;total_pallet_qty:Decimal;total_carton_qty:Decimal;total_weight_lbs:Decimal;total_cbm:Decimal;inventory_lot_count:int;containers:list[str];oldest_inbound_date:date|None;min_aging_days:int|None;max_aging_days:int|None;average_aging_days:Decimal|None;priority_level:str|None;priority_label:str|None;created_by:UserRef;created_at:datetime;updated_at:datetime
class FBAListResponse(BaseModel):data:list[FBARead];meta:PaginationMeta
class AllocateRequest(BaseModel):inventory_lot_id:int;pallet_qty:Decimal=Field(Decimal("0"),ge=0);carton_qty:Decimal=Field(Decimal("0"),ge=0);weight_lbs:Decimal=Field(Decimal("0"),ge=0);cbm:Decimal=Field(Decimal("0"),ge=0);confirm_fc_mismatch:bool=False
class ReleaseRequest(BaseModel):pallet_qty:Decimal|None=Field(None,ge=0);carton_qty:Decimal|None=Field(None,ge=0);weight_lbs:Decimal|None=Field(None,ge=0);cbm:Decimal|None=Field(None,ge=0);remark:str|None=None
class AllocationRead(BaseModel):
    id:int;inventory_lot_id:int;lot_no:str;container_number:str;fc_code:str|None;location:NamedRef|None;inbound_date:date|None;aging_days:int|None;priority_level:str|None;priority_label:str|None;allocated_pallet_qty:Decimal;allocated_carton_qty:Decimal;allocated_weight_lbs:Decimal;allocated_cbm:Decimal;inventory_available_pallet_qty:Decimal;inventory_available_carton_qty:Decimal;inventory_available_weight_lbs:Decimal;inventory_available_cbm:Decimal;fc_mismatch:bool;created_by:UserRef;created_at:datetime;updated_at:datetime
class StatusRequest(BaseModel):status:int=Field(ge=0,le=9)
