from datetime import date
from io import BytesIO
from typing import Annotated,Literal
from fastapi import APIRouter,Depends,Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from app.api.deps import CurrentUser,DbSession,require_warehouse_write
from app.models import User
from app.schemas.inventory import AdjustmentRequest,HoldRequest,InventoryListResponse,InventoryRead,MoveRequest,TransactionRead
from app.services.inventory import adjust,get_lot,hold,list_inventory,move,read_inventory,release,transactions

router=APIRouter(prefix="/inventory",tags=["Inventory"]);files_router=APIRouter(prefix="/inventory",tags=["Inventory Files"]);Writer=Annotated[User,Depends(require_warehouse_write)]
def params(page=1,per_page=20,q=None,container_number=None,fc_code=None,customer_id=None,warehouse_id=None,location_id=None,status=None,priority_level=None,inbound_date_from=None,inbound_date_to=None,aging_min=None,aging_max=None,has_available=None,sort_by="id",sort_order="desc"):return locals()
@files_router.get("/files/export.xlsx")
def export(db:DbSession,_:CurrentUser,q:str|None=None,container_number:str|None=None,fc_code:str|None=None,customer_id:int|None=None,warehouse_id:int|None=None,location_id:int|None=None,status:int|None=None,priority_level:str|None=None,aging_min:int|None=None,aging_max:int|None=None):
    first=list_inventory(db,**params(per_page=100,q=q,container_number=container_number,fc_code=fc_code,customer_id=customer_id,warehouse_id=warehouse_id,location_id=location_id,status=status,priority_level=priority_level,aging_min=aging_min,aging_max=aging_max));records=list(first.data)
    for page in range(2,first.meta.total_pages+1):records.extend(list_inventory(db,**params(page=page,per_page=100,q=q,container_number=container_number,fc_code=fc_code,customer_id=customer_id,warehouse_id=warehouse_id,location_id=location_id,status=status,priority_level=priority_level,aging_min=aging_min,aging_max=aging_max)).data)
    wb=Workbook();ws=wb.active;ws.title="Inventory";ws.append(["Lot No","Container Number","FC Code","Marking","Customer","Warehouse","Location","Inbound Date","Aging Days","Priority","Original Pallet","Available Pallet","Allocated Pallet","Hold Pallet","Original Carton","Available Carton","Weight LBS","CBM","Status","Remark"])
    for r in records:ws.append([r.lot_no,r.container_number,r.fc_code,r.marking,r.customer.name if r.customer else "",r.warehouse.code,r.location.code if r.location else "",r.inbound_date,r.aging_days,f"{r.priority_level or ''} {r.priority_label or ''}".strip(),r.original_pallet_qty,r.available_pallet_qty,r.allocated_pallet_qty,r.hold_pallet_qty,r.original_carton_qty,r.available_carton_qty,r.available_weight_lbs,r.available_cbm,r.status_name,r.remark])
    stream=BytesIO();wb.save(stream);stream.seek(0);return StreamingResponse(stream,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":"attachment; filename=Inventory_Export.xlsx"})
@router.get("",response_model=InventoryListResponse)
def inventory_list(db:DbSession,_:CurrentUser,page:int=Query(1,ge=1),per_page:int=Query(20,ge=1,le=100),q:str|None=None,container_number:str|None=None,fc_code:str|None=None,customer_id:int|None=None,warehouse_id:int|None=None,location_id:int|None=None,status:int|None=None,priority_level:str|None=None,inbound_date_from:date|None=None,inbound_date_to:date|None=None,aging_min:int|None=Query(None,ge=0),aging_max:int|None=Query(None,ge=0),has_available:bool|None=None,sort_by:str="id",sort_order:Literal["asc","desc"]="desc"):return list_inventory(db,**{k:v for k,v in locals().items()if k not in("db","_")})
@router.get("/{lot_id}",response_model=InventoryRead)
def inventory_detail(lot_id:int,db:DbSession,_:CurrentUser):return read_inventory(db,get_lot(db,lot_id))
@router.post("/{lot_id}/move",response_model=InventoryRead)
def move_lot(lot_id:int,payload:MoveRequest,db:DbSession,user:Writer):return read_inventory(db,move(db,lot_id,payload,user.id))
@router.post("/{lot_id}/adjust",response_model=InventoryRead)
def adjust_lot(lot_id:int,payload:AdjustmentRequest,db:DbSession,user:Writer):return read_inventory(db,adjust(db,lot_id,payload,user.id))
@router.post("/{lot_id}/hold",response_model=InventoryRead)
def hold_lot(lot_id:int,payload:HoldRequest,db:DbSession,user:Writer):return read_inventory(db,hold(db,lot_id,payload,user.id))
@router.post("/{lot_id}/release",response_model=InventoryRead)
def release_lot(lot_id:int,payload:HoldRequest,db:DbSession,user:Writer):return read_inventory(db,release(db,lot_id,payload,user.id))
@router.get("/{lot_id}/transactions",response_model=list[TransactionRead])
def lot_transactions(lot_id:int,db:DbSession,_:CurrentUser):return transactions(db,lot_id)
