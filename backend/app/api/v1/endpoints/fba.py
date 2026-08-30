from datetime import datetime
from io import BytesIO
from typing import Annotated,Literal
from fastapi import APIRouter,Depends,Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from app.api.deps import CurrentUser,DbSession,require_outbound_write
from app.models import User
from app.schemas.fba import AllocateRequest,AllocationRead,FBACreate,FBAListResponse,FBARead,FBAUpdate,ReleaseRequest,StatusRequest
from app.services.fba import allocate,allocation_list,change_status,create_fba,get_fba,list_fba,read_fba,release,update_fba
from app.schemas.fba_workbench import BatchActionRequest,BatchActionResponse,WorkbenchDetail,WorkbenchResponse
from app.services.fba_workbench import batch_action,list_workbench,workbench_detail
from app.services.access_policy import assert_customer_access,assert_warehouse_access
from app.services.inventory import get_lot

router=APIRouter(prefix="/fba",tags=["FBA"]);files_router=APIRouter(prefix="/fba",tags=["FBA Files"]);Writer=Annotated[User,Depends(require_outbound_write)]
@files_router.post('/workbench/export-selected')
def export_selected(payload:dict,db:DbSession,user:CurrentUser):
    result=list_workbench(db,user,page=1,per_page=10000,fba_ids=[int(x) for x in payload.get('fba_ids',[])],sort_by='id',sort_order='asc');wb=Workbook();ws=wb.active;ws.title='FBA Workbench';ws.append(['FBA No','ST Number','PO','Container','FC','Location','Pallet','Carton','Weight LB','CBM','Inbound Date','Warehouse Days','Inventory Priority','Earliest Outbound','Days Remaining','Dispatch Priority','Warehouse','Carrier','Schedule PU','APT Time','Picking No','BOL No','Outbound No','Stage'])
    for r in result['data']:ws.append([r['fba_no'],r['st_number'],r['po_number'],'; '.join(r['containers_preview']),r['amazon_fc_code'],'; '.join(r['locations_preview']),r['total_pallet_qty'],r['total_carton_qty'],r['total_weight_lbs'],r['total_cbm'],r['oldest_inbound_date'],r['warehouse_days'],r['priority_label'],r['earliest_outbound_date'],r['outbound_days_remaining'],r['dispatch_priority'],r['warehouse'],r.get('carrier',''),r['scheduled_pickup_at'],r['appointment_time'],r['picking_no'],r['bol_no'],r['outbound_no'],r['workbench_stage_name']])
    stream=BytesIO();wb.save(stream);stream.seek(0);return StreamingResponse(stream,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename=FBA_Workbench_Selected.xlsx'})
@files_router.get("/files/export.xlsx")
def export(db:DbSession,user:CurrentUser,q:str|None=None,warehouse_id:int|None=None,amazon_fc_code:str|None=None,status:int|None=None,priority_level:str|None=None,selected_ids:str|None=None):
    first=list_fba(db,page=1,per_page=100,q=q,warehouse_id=warehouse_id,amazon_fc_code=amazon_fc_code,status=status,priority_level=priority_level,user=user);records=list(first.data)
    for page in range(2,first.meta.total_pages+1):records.extend(list_fba(db,page=page,per_page=100,q=q,warehouse_id=warehouse_id,amazon_fc_code=amazon_fc_code,status=status,priority_level=priority_level,user=user).data)
    if selected_ids:
        wanted={int(x)for x in selected_ids.split(',')if x.strip().isdigit()};records=[x for x in records if x.id in wanted]
    wb=Workbook();ws=wb.active;ws.title="FBA";ws.append(["FBA No","Amazon FC","FC Address","Customer","Containers","Pallet","Carton","Weight","CBM","Oldest Inbound Date","Aging","Priority","Warehouse","Carrier","Schedule PU","APT Time","ST Number","Status"])
    for r in records:ws.append([r.fba_no,r.amazon_fc_code,r.amazon_fc_address,r.customer.name if r.customer else "",", ".join(r.containers),r.total_pallet_qty,r.total_carton_qty,r.total_weight_lbs,r.total_cbm,r.oldest_inbound_date,r.max_aging_days,f"{r.priority_level or ''} {r.priority_label or ''}".strip(),r.warehouse.code,r.carrier.name if r.carrier else "",r.scheduled_pickup_at.replace(tzinfo=None)if r.scheduled_pickup_at else None,r.appointment_time.replace(tzinfo=None)if r.appointment_time else None,r.st_number,r.status_name])
    stream=BytesIO();wb.save(stream);stream.seek(0);return StreamingResponse(stream,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":"attachment; filename=FBA_Export.xlsx"})
@router.get("",response_model=FBAListResponse)
def fba_list(db:DbSession,user:CurrentUser,page:int=Query(1,ge=1),per_page:int=Query(20,ge=1,le=100),q:str|None=None,fba_no:str|None=None,customer_id:int|None=None,warehouse_id:int|None=None,amazon_fc_code:str|None=None,carrier_id:int|None=None,status:int|None=None,container_number:str|None=None,location_id:int|None=None,priority_level:str|None=None,aging_min:int|None=Query(None,ge=0),aging_max:int|None=Query(None,ge=0),appointment_from:datetime|None=None,appointment_to:datetime|None=None,sort_by:str="id",sort_order:Literal["asc","desc"]="desc"):return list_fba(db,**{k:v for k,v in locals().items()if k!="db"})
@router.get("/workbench",response_model=WorkbenchResponse)
def workbench(db:DbSession,user:CurrentUser,page:int=Query(1,ge=1),per_page:int=Query(20,ge=1,le=100),warehouse_id:int|None=None,customer_id:int|None=None,q:str|None=None,stage:str="all",priority:str|None=None,only_old:bool=False,unload_from:str|None=None,unload_to:str|None=None,aging_min:int|None=None,aging_max:int|None=None,sort_by:str="priority_rank",sort_order:Literal["asc","desc"]="desc",amazon_fc_code:str|None=None,container_number:str|None=None,location_id:int|None=None,carrier_id:int|None=None,fba_status:int|None=None,outbound_status:int|None=None,picking_status:int|None=None,bol_status:int|None=None,st_number:str|None=None,po_number:str|None=None,scheduled_from:datetime|None=None,scheduled_to:datetime|None=None,appointment_from:datetime|None=None,appointment_to:datetime|None=None):return list_workbench(db,user,**{k:v for k,v in locals().items()if k not in('db','user')})
@router.post("/workbench/batch",response_model=BatchActionResponse)
def workbench_batch(payload:BatchActionRequest,db:DbSession,user:Writer):return batch_action(db,user,payload.action,payload.fba_ids)
@router.get("/{fba_id}/workbench-detail",response_model=WorkbenchDetail)
def workbench_detail_endpoint(fba_id:int,db:DbSession,user:CurrentUser):return workbench_detail(db,fba_id,user)
@router.post("",response_model=FBARead,status_code=201)
def add_fba(payload:FBACreate,db:DbSession,user:Writer):assert_warehouse_access(user,payload.warehouse_id);assert_customer_access(user,payload.customer_id);return read_fba(db,get_fba(db,create_fba(db,payload,user.id).id,user=user))
@router.get("/{fba_id}",response_model=FBARead)
def fba_detail(fba_id:int,db:DbSession,user:CurrentUser):return read_fba(db,get_fba(db,fba_id,user=user))
@router.put("/{fba_id}",response_model=FBARead)
def edit_fba(fba_id:int,payload:FBAUpdate,db:DbSession,user:Writer):assert_warehouse_access(user,payload.warehouse_id);assert_customer_access(user,payload.customer_id);return read_fba(db,update_fba(db,get_fba(db,fba_id,user=user),payload,user.id))
@router.post("/{fba_id}/allocate",response_model=AllocationRead)
def add_allocation(fba_id:int,payload:AllocateRequest,db:DbSession,user:Writer):
    get_fba(db,fba_id,user=user);get_lot(db,payload.inventory_lot_id,user=user);allocation=allocate(db,fba_id,payload,user.id);return next(x for x in allocation_list(db,get_fba(db,fba_id,user=user))if x.id==allocation.id)
@router.post("/{fba_id}/allocations/{allocation_id}/release",response_model=AllocationRead)
def release_allocation(fba_id:int,allocation_id:int,payload:ReleaseRequest,db:DbSession,user:Writer):
    get_fba(db,fba_id,user=user);allocation=release(db,fba_id,allocation_id,payload,user.id);return next(x for x in allocation_list(db,get_fba(db,fba_id,user=user))if x.id==allocation.id)
@router.get("/{fba_id}/allocations",response_model=list[AllocationRead])
def allocations(fba_id:int,db:DbSession,user:CurrentUser):return allocation_list(db,get_fba(db,fba_id,user=user))
@router.post("/{fba_id}/status",response_model=FBARead)
def status_change(fba_id:int,payload:StatusRequest,db:DbSession,user:Writer):get_fba(db,fba_id,user=user);return read_fba(db,change_status(db,fba_id,payload.status,user.id))
