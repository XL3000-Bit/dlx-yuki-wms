from datetime import date,datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from app.schemas.inbound import NamedRef,PaginationMeta,UserRef

class InventoryRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:int;lot_no:str;container_number:str;fc_code:str|None;marking:str|None;customer:NamedRef|None;warehouse:NamedRef;location:NamedRef|None;source_inbound_id:int;inbound_date:date|None;aging_days:int|None;priority_level:str|None;priority_label:str|None;original_pallet_qty:Decimal;available_pallet_qty:Decimal;allocated_pallet_qty:Decimal;hold_pallet_qty:Decimal;original_carton_qty:Decimal;available_carton_qty:Decimal;allocated_carton_qty:Decimal;hold_carton_qty:Decimal;original_weight_lbs:Decimal;available_weight_lbs:Decimal;allocated_weight_lbs:Decimal;original_cbm:Decimal;available_cbm:Decimal;allocated_cbm:Decimal;status:int;status_name:str;remark:str|None;created_at:datetime;updated_at:datetime
class InventoryListResponse(BaseModel):data:list[InventoryRead];meta:PaginationMeta
class MoveRequest(BaseModel):to_location_id:int;remark:str|None=None
class AdjustmentRequest(BaseModel):
    pallet_delta:Decimal=Decimal("0");carton_delta:Decimal=Decimal("0");weight_delta:Decimal=Decimal("0");cbm_delta:Decimal=Decimal("0");reason:Literal["COUNT_CORRECTION","DAMAGE","LOST","FOUND","REPACK","MANUAL","OTHER"];remark:str|None=None
    def model_post_init(self,_):
        if self.reason=="OTHER" and not (self.remark or "").strip():raise ValueError("Remark is required for OTHER reason")
class HoldRequest(BaseModel):pallet_qty:Decimal=Field(Decimal("0"),ge=0);carton_qty:Decimal=Field(Decimal("0"),ge=0);remark:str|None=None
class TransactionRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:int;transaction_type:str;pallet_delta:Decimal;carton_delta:Decimal;weight_delta:Decimal;cbm_delta:Decimal;from_location:NamedRef|None;to_location:NamedRef|None;reference_type:str|None;reference_id:int|None;before_snapshot:dict|None;after_snapshot:dict|None;remark:str|None;created_by:UserRef;created_at:datetime
