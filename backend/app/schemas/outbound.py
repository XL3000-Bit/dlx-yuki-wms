from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel,ConfigDict,Field
from app.schemas.inbound import NamedRef,PaginationMeta,UserRef
class OBBase(BaseModel):
 customer_id:int|None=None;warehouse_id:int;carrier_id:int|None=None;fba_shipment_id:int|None=None;ob_type:str='STANDARD';loading_team:str|None=None;truck_type:str|None=None;notify_carrier:bool=False;delivery_type:str|None=None;pickup_location:str|None=None;schedule_pickup_at:datetime|None=None;delivery_appointment_time:datetime|None=None;fc_code:str|None=None;del_code:str|None=None;agent_code:str|None=None;driver_name:str|None=None;driver_phone:str|None=None;truck_number:str|None=None;trailer_number:str|None=None;reference_no:str|None=None;remark:str|None=None
class OBCreate(OBBase):pass
class OBUpdate(OBBase):pass
class AllocateRequest(BaseModel):inventory_lot_id:int;fba_allocation_id:int|None=None;pallet_qty:Decimal=Field(Decimal('0'),ge=0);carton_qty:Decimal=Field(Decimal('0'),ge=0);weight_lbs:Decimal=Field(Decimal('0'),ge=0);cbm:Decimal=Field(Decimal('0'),ge=0)
class ReleaseRequest(BaseModel):pallet_qty:Decimal|None=None;carton_qty:Decimal|None=None;weight_lbs:Decimal|None=None;cbm:Decimal|None=None;remark:str|None=None
class ExceptionRequest(BaseModel):reason:str=Field(min_length=1);remark:str|None=None
class CompleteRequest(BaseModel):allocation_id:int|None=None;pallet_qty:Decimal|None=None;carton_qty:Decimal|None=None;weight_lbs:Decimal|None=None;cbm:Decimal|None=None
class OBStatusResponse(BaseModel):status:int;status_name:str
class OBRead(BaseModel):
 model_config=ConfigDict(from_attributes=True)
 id:int;ob_no:str;status:int;status_name:str;ob_type:str;customer:NamedRef|None=None;warehouse:NamedRef;carrier:NamedRef|None=None;fba_shipment:NamedRef|None=None;loading_team:str|None=None;truck_type:str|None=None;notify_carrier:bool;delivery_type:str|None=None;pickup_location:str|None=None;schedule_pickup_at:datetime|None=None;delivery_appointment_time:datetime|None=None;fc_code:str|None=None;del_code:str|None=None;agent_code:str|None=None;driver_name:str|None=None;truck_number:str|None=None;trailer_number:str|None=None;total_pallet_qty:Decimal;total_carton_qty:Decimal;total_weight_lbs:Decimal;total_cbm:Decimal;allocation_count:int;remaining_pallet_qty:Decimal;remaining_carton_qty:Decimal;reference_no:str|None=None;exception_reason:str|None=None;remark:str|None=None;created_at:datetime;updated_at:datetime
class OBListResponse(BaseModel):data:list[OBRead];meta:PaginationMeta
class AllocationRead(BaseModel):id:int;inventory_lot_id:int;fba_allocation_id:int|None;lot_no:str;container_number:str;fc_code:str|None;location:NamedRef|None;allocated_pallet_qty:Decimal;allocated_carton_qty:Decimal;allocated_weight_lbs:Decimal;allocated_cbm:Decimal;completed_pallet_qty:Decimal;completed_carton_qty:Decimal;completed_weight_lbs:Decimal;completed_cbm:Decimal;source_type:str;fba_no:str|None;created_at:datetime
