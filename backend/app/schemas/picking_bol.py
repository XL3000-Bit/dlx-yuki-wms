from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
class PickingRead(BaseModel):id:int;picking_no:str;outbound_order_id:int;status:int;status_name:str;assigned_team:str|None=None;planned_pallet_qty:Decimal;planned_carton_qty:Decimal;picked_pallet_qty:Decimal;picked_carton_qty:Decimal;created_at:datetime;completed_at:datetime|None=None
class BOLRead(BaseModel):id:int;bol_no:str;outbound_order_id:int;fba_shipment_id:int|None;ship_from_name:str;ship_from_address:str;ship_to_name:str|None;ship_to_address:str|None;amazon_fc_code:str|None;status:int;status_name:str;total_pallet_qty:Decimal;total_carton_qty:Decimal;total_weight_lbs:Decimal;total_cbm:Decimal;fc_address_missing:bool;transport_mode:str;amazon_bol_ready:bool;missing_amazon_fields:list[str];created_at:datetime
class PickComplete(BaseModel):picked_pallet_qty:Decimal|None=None;picked_carton_qty:Decimal|None=None;remark:str|None=None
