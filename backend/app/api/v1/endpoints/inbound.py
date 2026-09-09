from datetime import date
from io import BytesIO
from typing import Annotated,Literal
from fastapi import APIRouter,Depends,HTTPException,Query,status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import select
from app.api.deps import CurrentUser,DbSession,require_admin,require_warehouse_write
from app.models import InboundRecord,User
from app.models.inbound import InboundStatus
from app.schemas.common import Message
from app.schemas.inbound import InboundCreate,InboundListParams,InboundListResponse,InboundPatch,InboundRead,InboundUpdate
from app.services.inbound import _read,create_inbound,delete_inbound,get_inbound,list_inbounds,update_inbound
from app.services.inventory import cancel_inbound,read_inventory,receive_inbound,receive_inbound_lines
from app.services.access_policy import assert_customer_access,assert_warehouse_access
from app.schemas.inventory import InventoryRead

router=APIRouter(prefix="/inbound",tags=["Inbound"]);files_router=APIRouter(prefix="/inbound",tags=["Inbound Files"]);Admin=Annotated[User,Depends(require_admin)];Writer=Annotated[User,Depends(require_warehouse_write)]
@router.get("",response_model=InboundListResponse)
def list_records(db:DbSession,user:CurrentUser,page:int=1,per_page:int=20,q:str|None=None,container_number:str|None=None,customer_id:int|None=None,warehouse_id:int|None=None,fc_code:str|None=None,location_id:int|None=None,status:InboundStatus|None=None,unload_date_from:date|None=None,unload_date_to:date|None=None,received_date_from:date|None=None,received_date_to:date|None=None,sort_by:str="id",sort_order:Literal["asc","desc"]="desc"):
    return list_inbounds(db,InboundListParams(**{k:v for k,v in locals().items() if k not in ('db','user')}),user)
@router.post("",response_model=InboundRead,status_code=201)
def add_record(payload:InboundCreate,db:DbSession,user:Writer):assert_warehouse_access(user,payload.warehouse_id);assert_customer_access(user,payload.customer_id);return _read(get_inbound(db,create_inbound(db,payload,user.id).id,user=user))
@router.get("/{record_id}",response_model=InboundRead)
def get_record(record_id:int,db:DbSession,user:CurrentUser):return _read(get_inbound(db,record_id,user=user))
@router.put("/{record_id}",response_model=InboundRead)
def edit_record(record_id:int,payload:InboundUpdate,db:DbSession,user:Writer):assert_warehouse_access(user,payload.warehouse_id);assert_customer_access(user,payload.customer_id);return _read(update_inbound(db,get_inbound(db,record_id,user=user),payload,user.id))
@router.patch("/{record_id}",response_model=InboundRead)
def patch_record(record_id:int,payload:InboundPatch,db:DbSession,user:Writer):
    row=get_inbound(db,record_id,user=user)
    fields=payload.model_fields_set
    warehouse_id=payload.warehouse_id if "warehouse_id" in fields else row.warehouse_id
    customer_id=payload.customer_id if "customer_id" in fields else row.customer_id
    if warehouse_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,"Warehouse is required")
    assert_warehouse_access(user,warehouse_id)
    assert_customer_access(user,customer_id)
    return _read(update_inbound(db,row,payload,user.id,require_draft=True))
@router.delete("/{record_id}",response_model=Message)
def remove_record(record_id:int,db:DbSession,user:Admin):delete_inbound(db,get_inbound(db,record_id,user=user),user.id);return Message(message="Inbound record deleted")
@router.post("/{record_id}/receive-to-inventory",response_model=InventoryRead)
def receive_to_inventory(record_id:int,db:DbSession,user:Writer):get_inbound(db,record_id,user=user);return read_inventory(db,receive_inbound(db,record_id,user.id))
@router.post("/{record_id}/receive")
def receive(record_id:int,db:DbSession,user:Writer):
    lots=receive_inbound_lines(db,record_id,user.id,user=user)
    return {"inbound":_read(get_inbound(db,record_id,user=user)),"inventory_lots":[read_inventory(db,lot) for lot in lots]}
@router.post("/{record_id}/cancel",response_model=InboundRead)
def cancel(record_id:int,db:DbSession,user:Writer):cancel_inbound(db,record_id,user.id,user=user);return _read(get_inbound(db,record_id,user=user))
@files_router.get("/files/template.xlsx")
def template(_:CurrentUser):
    wb=Workbook();ws=wb.active;ws.title="Inbound Import";headers=["Container Number","PO Number","Customer","Warehouse","Unload Date","Received Date","FC Code","Marking","Pallet Qty","Carton Qty","Weight LBS","CBM","Location","Remark"];ws.append(headers);ws.append(["MSCU1234567","PO-10001","ACME","DLX-LAX","2026-08-28","2026-08-29","LAX9","FBA-001",10,200,12500,42.5,"A01","Example row"]);stream=BytesIO();wb.save(stream);stream.seek(0);return StreamingResponse(stream,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":"attachment; filename=Inbound_Import_Template.xlsx"})
@files_router.get("/files/export.xlsx")
def export(db:DbSession,user:CurrentUser,q:str|None=None,warehouse_id:int|None=None,fc_code:str|None=None):
    first=list_inbounds(db,InboundListParams(q=q,warehouse_id=warehouse_id,fc_code=fc_code,per_page=100),user);records=list(first.data)
    for page in range(2,first.meta.total_pages+1):records.extend(list_inbounds(db,InboundListParams(q=q,warehouse_id=warehouse_id,fc_code=fc_code,per_page=100,page=page),user).data)
    wb=Workbook();ws=wb.active;ws.title="Inbound";ws.append(["Inbound No","Container Number","PO Number","Customer","Warehouse","Unload Date","Received Date","FC Code","Marking","Pallet Qty","Carton Qty","Weight LBS","CBM","Location","Status","Aging Days","Remark","Created At"])
    for r in records:ws.append([r.inbound_no,r.container_number,r.po_number,r.customer.name if r.customer else "",r.warehouse.name,r.unload_date,r.received_date,r.fc_code,r.marking,r.pallet_qty,r.carton_qty,r.weight_lbs,r.cbm,r.location.code if r.location else "",r.status_name,r.aging_days,r.remark,r.created_at.replace(tzinfo=None)])
    stream=BytesIO();wb.save(stream);stream.seek(0);return StreamingResponse(stream,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":"attachment; filename=Inbound_Export.xlsx"})
