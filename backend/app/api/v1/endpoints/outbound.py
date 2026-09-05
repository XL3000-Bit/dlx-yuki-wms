from datetime import datetime,timezone
import logging
from typing import Annotated,Literal
from fastapi import APIRouter,Depends,Header,HTTPException,Query,Response
from fastapi.responses import StreamingResponse
from io import BytesIO
from openpyxl import Workbook
from app.api.deps import CurrentUser,DbSession,require_outbound_write
from app.models import AuditLog,OutboundInventoryIdempotency,User
from fastapi.encoders import jsonable_encoder
from app.schemas.outbound import AllocateRequest,AllocationRead,CompleteRequest,ExceptionRequest,InventoryBatchRequest,OBCreate,OBListResponse,OBRead,OBUpdate,ReleaseRequest
from pydantic import BaseModel
from app.services.outbound import allocate,allocations,change,complete_partial,create_ob,delete_outbound_draft,get_ob,list_outbounds,release,read_ob
from app.schemas.outbound_workbench import OutboundWorkbenchResponse,OutboundWorkbenchDetail
from app.services.outbound_workbench import list_workbench,detail as workbench_detail
from app.schemas.dispatch_readiness import DispatchReadinessRead
from app.services.dispatch_readiness import get_dispatch_readiness
from app.services.picking_bol import generate_picking,generate_bol
from app.utils.business_time import to_business_datetime
from app.services.access_policy import assert_customer_access,assert_warehouse_access
from app.services.inventory import get_lot
from app.services.idempotency import acquire_command_lock,find_receipt,request_fingerprint,validate_idempotency_key
router=APIRouter(prefix='/outbounds',tags=['Outbound']);files_router=APIRouter(prefix='/outbounds',tags=['Outbound Files']);Writer=Annotated[User,Depends(require_outbound_write)]
logger=logging.getLogger(__name__)
GENERIC_BATCH_ERROR='OUTBOUND_BATCH_OPERATION_FAILED'
def _business_error_message(exc:HTTPException)->str:
 detail=exc.detail
 if isinstance(detail,dict):
  reasons=detail.get('blocking_reasons')
  if reasons:return '; '.join(str(reason) for reason in reasons)
  return str(detail.get('message') or detail.get('code') or 'Request failed')
 return str(detail)
class SchedulePatch(BaseModel):
 carrier_id:int|None=None; schedule_pickup_at:datetime|None=None; delivery_appointment_time:datetime|None=None; driver_name:str|None=None; driver_phone:str|None=None; truck_number:str|None=None; trailer_number:str|None=None; remark:str|None=None
@files_router.get('/files/export.xlsx')
def export(db:DbSession,user:CurrentUser,q:str|None=None,status:int|None=None,ob_type:str|None=None,warehouse_id:int|None=None):
 rows=list_outbounds(db,page=1,per_page=10000,q=q,status=status,ob_type=ob_type,warehouse_id=warehouse_id,user=user);wb=Workbook();ws=wb.active;ws.title='Outbound';ws.append(['OB#','Status','OB Type','Carrier','Warehouse','Pallet','Carton','Weight LBS','CBM','Reference'])
 for r in rows['data']:ws.append([r.ob_no,r.status_name,r.ob_type,r.carrier.name if r.carrier else '',r.warehouse.name,r.total_pallet_qty,r.total_carton_qty,r.total_weight_lbs,r.total_cbm,r.reference_no])
 stream=BytesIO();wb.save(stream);stream.seek(0);return StreamingResponse(stream,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename=Outbound_Export.xlsx'})
@router.get('',response_model=OBListResponse)
def listing(db:DbSession,user:CurrentUser,page:int=Query(1,ge=1),per_page:int=Query(20,ge=1,le=100),q:str|None=None,ob_no:str|None=None,status:int|None=None,ob_type:str|None=None,customer_id:int|None=None,warehouse_id:int|None=None,carrier_id:int|None=None,fba_shipment_id:int|None=None,fc_code:str|None=None,del_code:str|None=None,agent_code:str|None=None,sort_by:str='id',sort_order:Literal['asc','desc']='desc'):return list_outbounds(db,**{k:v for k,v in locals().items() if k!='db'})
@router.get('/workbench',response_model=OutboundWorkbenchResponse)
def workbench(db:DbSession,user:CurrentUser,page:int=Query(1,ge=1),per_page:int=Query(20,ge=1,le=100),q:str|None=None,status:int|None=None,ob_type:str|None=None,warehouse_id:int|None=None,carrier_id:int|None=None,sort_by:str='created_at',sort_order:Literal['asc','desc']='desc'):
    return list_workbench(db,user,page=page,per_page=per_page,q=q,status=status,ob_type=ob_type,warehouse_id=warehouse_id,carrier_id=carrier_id,sort_by=sort_by,sort_order=sort_order)
@router.get('/{ob_id}/workbench-detail',response_model=OutboundWorkbenchDetail)
def workbench_detail_route(ob_id:int,db:DbSession,user:CurrentUser):return workbench_detail(db,ob_id,user)
@router.patch('/{ob_id}/schedule',response_model=OBRead)
def schedule_patch(ob_id:int,payload:SchedulePatch,db:DbSession,user:Writer):
 o=get_ob(db,ob_id,user=user)
 if o.status in (5,6):
  from fastapi import HTTPException
  raise HTTPException(409,'Completed or canceled outbound cannot be scheduled')
 changes=payload.model_dump(exclude_unset=True)
 for field in ('schedule_pickup_at','delivery_appointment_time'):
  if field in changes:changes[field]=to_business_datetime(changes[field])
 before={k:getattr(o,k) for k in changes}
 for k,v in changes.items(): setattr(o,k,v)
 db.add(AuditLog(user_id=user.id,action='UPDATE_OUTBOUND_SCHEDULE',entity_type='OUTBOUND',entity_id=o.id,before_data=jsonable_encoder(before),after_data=jsonable_encoder(changes)))
 db.commit(); return read_ob(db,get_ob(db,ob_id,user=user))
@router.post('/workbench/export-selected')
def workbench_export_selected(payload:dict,db:DbSession,user:CurrentUser):
 ids=[int(x) for x in (payload.get('ids') or [])]
 rows=list_workbench(db,user,page=1,per_page=10000)['data']
 selected={x['id'] for x in ids};rows=[r for r in rows if r['id'] in selected]
 wb=Workbook();ws=wb.active;ws.title='Outbound';headers=['OB#','Status','Carrier','FBA','ST','FC','Planned PLT','Allocated PLT','Picked PLT','Completed PLT','Remaining PLT','Weight LB','CBM','Schedule PU','APT','Reference'];ws.append(headers)
 for r in rows: ws.append([r.get('ob_no'),r.get('status_name'),r.get('carrier'),r.get('fba_no'),r.get('st_number'),r.get('fc_code'),r.get('planned_pallet_qty'),r.get('allocated_pallet_qty'),r.get('picked_pallet_qty'),r.get('completed_pallet_qty'),r.get('remaining_pallet_qty'),r.get('allocated_weight_lbs'),r.get('allocated_cbm'),r.get('schedule_pickup_at'),r.get('delivery_appointment_time'),r.get('reference_no')])
 stream=BytesIO();wb.save(stream);stream.seek(0);return StreamingResponse(stream,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename=Outbound_Selected.xlsx'})
@router.post('/workbench/batch')
def workbench_batch(payload:dict,db:DbSession,user:Writer):
 action=payload.get('action'); results=[]
 for raw in payload.get('ids') or []:
  oid=raw
  try:
   oid=int(raw)
   get_ob(db,oid,user=user)
   if action=='picking': generate_picking(db,oid,user.id)
   elif action=='bol': generate_bol(db,oid,user.id)
   elif action=='delete': delete_outbound_draft(db,oid,user.id,user=user)
   elif action in {'confirm','dispatch','complete','cancel'}: change(db,oid,{'confirm':3,'dispatch':4,'complete':5,'cancel':6}[action],user.id)
   else: raise ValueError('Unsupported batch action')
   results.append({'id':oid,'status':'success'})
  except HTTPException as exc:
   db.rollback();results.append({'id':oid,'status':'failed','reason':_business_error_message(exc)})
  except Exception:
   db.rollback();logger.exception('Unexpected outbound workbench batch failure',extra={'outbound_id':oid,'action':action});results.append({'id':oid,'status':'failed','reason':GENERIC_BATCH_ERROR})
 return {'results':results,'successful':sum(r['status']=='success' for r in results),'failed':sum(r['status']=='failed' for r in results)}
@router.post('/{ob_id}/inventory/batch')
def inventory_batch(ob_id:int,payload:InventoryBatchRequest,response:Response,db:DbSession,user:Writer,idempotency_key:str|None=Header(None,alias='Idempotency-Key')):
 item_id=None
 try:
  commands=[]
  for item in payload.items:
   item_id=item.id
   if payload.action=='allocate':
    commands.append((item.id,None,AllocateRequest.model_validate(item.data)))
   else:
    data=dict(item.data);allocation_id=int(data.pop('allocation_id',item.id))
    commands.append((item.id,allocation_id,ReleaseRequest.model_validate(data)))
  item_id=None
  key=validate_idempotency_key(idempotency_key)
  outbound=get_ob(db,ob_id,user=user)
  scope=f'warehouse:{outbound.warehouse_id}:outbound:{ob_id}'
  fingerprint=request_fingerprint({'action':payload.action,'outbound_order_id':ob_id,'warehouse_id':outbound.warehouse_id,'items':payload.model_dump(mode='json')['items']})
  acquire_command_lock(db,scope,payload.action,key)
  receipt=find_receipt(db,scope,payload.action,key)
  if receipt:
   if receipt.request_hash!=fingerprint:
    raise HTTPException(409,{'code':'OUTBOUND_IDEMPOTENCY_CONFLICT','message':'IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST'})
   if receipt.status=='COMPLETED' and receipt.response_payload is not None:
    response.headers['Idempotency-Replayed']='true'
    return receipt.response_payload
   raise HTTPException(409,{'code':'OUTBOUND_IDEMPOTENCY_IN_PROGRESS','message':'The idempotent operation is still in progress'})
  receipt=OutboundInventoryIdempotency(scope=scope,action=payload.action,idempotency_key=key,request_hash=fingerprint,status='PENDING')
  db.add(receipt);db.flush();results=[]
  for command_item_id,allocation_id,request in commands:
   item_id=command_item_id
   if payload.action=='allocate':
    get_lot(db,request.inventory_lot_id,user=user);allocate(db,ob_id,request,user.id,commit=False)
   else:
    release(db,ob_id,allocation_id,request,user.id,commit=False)
   results.append({'id':command_item_id,'status':'success'})
   item_id=None
  result={'action':payload.action,'results':results,'successful':len(results),'failed':0}
  receipt.status='COMPLETED';receipt.response_status=200;receipt.response_payload=result;receipt.completed_at=datetime.now(timezone.utc)
  db.commit()
  response.headers['Idempotency-Replayed']='false'
  return result
 except HTTPException as exc:
  db.rollback()
  if item_id is None:raise
  raise HTTPException(exc.status_code,{'code':'OUTBOUND_INVENTORY_BATCH_FAILED','item_id':item_id,'message':_business_error_message(exc)}) from exc
 except Exception:
  db.rollback();logger.exception('Unexpected outbound inventory batch failure',extra={'outbound_id':ob_id,'item_id':item_id,'action':payload.action})
  raise HTTPException(409,{'code':GENERIC_BATCH_ERROR,'item_id':item_id,'message':GENERIC_BATCH_ERROR})
@router.post('',response_model=OBRead,status_code=201)
def create(payload:OBCreate,db:DbSession,user:Writer):assert_warehouse_access(user,payload.warehouse_id);assert_customer_access(user,payload.customer_id);return read_ob(db,create_ob(db,payload,user.id))
@router.get('/{ob_id}/dispatch-readiness',response_model=DispatchReadinessRead)
def dispatch_readiness(ob_id:int,db:DbSession,user:CurrentUser):return get_dispatch_readiness(db,get_ob(db,ob_id,user=user))
@router.get('/{ob_id}',response_model=OBRead)
def detail(ob_id:int,db:DbSession,user:CurrentUser):return read_ob(db,get_ob(db,ob_id,user=user))
@router.put('/{ob_id}',response_model=OBRead)
def update(ob_id:int,payload:OBUpdate,db:DbSession,user:Writer):
 assert_warehouse_access(user,payload.warehouse_id);assert_customer_access(user,payload.customer_id);o=get_ob(db,ob_id,user=user)
 if o.status in (5,6):from fastapi import HTTPException;raise HTTPException(409,'Completed or canceled outbound cannot be edited')
 data=payload.model_dump()
 for field in ('schedule_pickup_at','delivery_appointment_time'):
  data[field]=to_business_datetime(data.get(field))
 for k,v in data.items():setattr(o,k,v)
 db.commit();return read_ob(db,get_ob(db,ob_id,user=user))
@router.post('/{ob_id}/allocate',response_model=AllocationRead)
def add_alloc(ob_id:int,payload:AllocateRequest,db:DbSession,user:Writer):get_ob(db,ob_id,user=user);get_lot(db,payload.inventory_lot_id,user=user);return AllocationRead.model_validate(allocations(db,get_ob(db,ob_id,user=user))[-1] if allocate(db,ob_id,payload,user.id) else None)
@router.get('/{ob_id}/allocations',response_model=list[AllocationRead])
def list_alloc(ob_id:int,db:DbSession,user:CurrentUser):return allocations(db,get_ob(db,ob_id,user=user))
@router.post('/{ob_id}/allocations/{allocation_id}/release',response_model=AllocationRead)
def release_alloc(ob_id:int,allocation_id:int,payload:ReleaseRequest,db:DbSession,user:Writer):get_ob(db,ob_id,user=user);release(db,ob_id,allocation_id,payload,user.id);return allocations(db,get_ob(db,ob_id,user=user))[0]
@router.post('/{ob_id}/confirm',response_model=OBRead)
def confirm(ob_id:int,db:DbSession,user:Writer):get_ob(db,ob_id,user=user);return read_ob(db,change(db,ob_id,3,user.id))
@router.post('/{ob_id}/dispatch',response_model=OBRead)
def dispatch(ob_id:int,db:DbSession,user:Writer):get_ob(db,ob_id,user=user);return read_ob(db,change(db,ob_id,4,user.id))
@router.post('/{ob_id}/complete',response_model=OBRead)
def complete(ob_id:int,db:DbSession,user:Writer,payload:CompleteRequest|None=None):
 get_ob(db,ob_id,user=user)
 if payload and payload.allocation_id is not None:
  o=get_ob(db,ob_id,True); complete_partial(db,o,user.id,payload); db.commit(); return read_ob(db,get_ob(db,ob_id))
 return read_ob(db,change(db,ob_id,5,user.id))
@router.post('/{ob_id}/cancel',response_model=OBRead)
def cancel(ob_id:int,db:DbSession,user:Writer):get_ob(db,ob_id,user=user);return read_ob(db,change(db,ob_id,6,user.id))
@router.post('/{ob_id}/exception',response_model=OBRead)
def exception_(ob_id:int,payload:ExceptionRequest,db:DbSession,user:Writer):get_ob(db,ob_id,user=user);return read_ob(db,change(db,ob_id,7,user.id,payload))
@router.post('/{ob_id}/resolve-exception',response_model=OBRead)
def resolve(ob_id:int,db:DbSession,user:Writer):get_ob(db,ob_id,user=user);return read_ob(db,change(db,ob_id,3,user.id))
