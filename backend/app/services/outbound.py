from app.services.history_policy import require_live_record
from app.services.cargo_bol import identity_for_allocation, document_identity
from datetime import UTC,datetime,date
from decimal import Decimal
from math import ceil
from typing import Any
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func,or_,select
from sqlalchemy.orm import Session,joinedload,selectinload
from app.models import AuditLog,BOL,Carrier,Customer,ExceptionSeverity,ExceptionStatus,ExceptionType,FBAInventoryAllocation,FBAShipment,InventoryLot,InventoryTransaction,LoadVerificationTransaction,OperationalDocument,OperationalException,OutboundInventoryAllocation,OutboundOrder,PickingList,ScanSession,StageTransaction,User,Warehouse,WorkOrder
from app.models.inventory import TransactionType
from app.models.outbound import OBStatus
from app.schemas.inbound import NamedRef,PaginationMeta
from app.schemas.outbound import AllocateRequest,AllocationRead,CompleteRequest,ExceptionRequest,OBCreate,OBRead,OBUpdate,ReleaseRequest
from app.services.inventory import ZERO,_tx,derive_status,get_lot,snapshot
from app.schemas.operational_exception import ExceptionCreate
from app.services.operational_exception import create_exception,transition_exception
from app.services.access_policy import customer_clause,warehouse_clause
from app.services.dispatch_readiness import require_dispatch_ready
from app.utils.business_time import get_business_today,to_business_datetime
STATUS={x.value:x.name.replace('_',' ').title() for x in OBStatus}
TRANS={0:{1,2,3,6,7},1:{2,3,6,7},2:{3,6,7},3:{4,6,7},4:{5},7:{3,6}}

def require_transition(o,target):
 if target not in TRANS.get(o.status,set()):raise HTTPException(409,f'Invalid status transition: {STATUS[o.status]} to {STATUS.get(target)}')
def generate_ob_no(db:Session,today:date|None=None)->str:
 d=today or get_business_today();prefix=f'OB{d:%y%m%d}';last=db.scalar(select(func.max(OutboundOrder.ob_no)).where(OutboundOrder.ob_no.like(prefix+'%')));return f'{prefix}{(int(last[-4:])+1 if last else 1):04d}'
def named(o:Any,kind:str):return NamedRef(id=o.id,code=getattr(o,f'{kind}_code'),name=getattr(o,f'{kind}_name')) if o else None
def query():return select(OutboundOrder).options(joinedload(OutboundOrder.customer),joinedload(OutboundOrder.warehouse),joinedload(OutboundOrder.carrier),joinedload(OutboundOrder.fba_shipment),selectinload(OutboundOrder.allocations).joinedload(OutboundInventoryAllocation.inventory_lot))
def get_ob(db:Session,id:int,lock=False,user:User|None=None,live=True):
 q=query().where(OutboundOrder.id==id).execution_options(populate_existing=True)
 if user:
  clauses=(warehouse_clause(user,OutboundOrder.warehouse_id),customer_clause(user,OutboundOrder.customer_id))
  q=q.where(*(clause for clause in clauses if clause is not None))
 o=db.scalar(q)
 if not o:raise HTTPException(404,'Outbound order not found')
 if lock:
  # Every member mutation uses the same Load -> Order lock order as dispatch.
  from app.models import Load
  load_id=o.load_id
  if load_id is not None:
   db.scalar(select(Load).where(Load.id==load_id).with_for_update().execution_options(populate_existing=True))
  locked=select(OutboundOrder).options(selectinload(OutboundOrder.allocations)).where(OutboundOrder.id==id).with_for_update().execution_options(populate_existing=True)
  if user:locked=locked.where(*(clause for clause in clauses if clause is not None))
  o=db.scalar(locked)
  if not o:raise HTTPException(404,'Outbound order not found')
  if o.load_id!=load_id:raise HTTPException(409,'Outbound membership changed; retry the request')
  if live: require_live_record(db,o)
 return o

def require_allocation_mutable(db,o):
 if o.load_id is not None:
  from app.services.load_dispatch_write import latest_plan
  plan=latest_plan(db,o.load_id)
  if plan and plan.status=='FINAL':raise HTTPException(409,'Final dispatch plan freezes outbound inventory allocation')

def require_release_unreferenced(db,allocation_id):
 from app.models import LoadAllocation
 if db.scalar(select(LoadAllocation.id).where(LoadAllocation.inventory_allocation_id==allocation_id).limit(1)):
  raise HTTPException(409,'Inventory is referenced by dispatch allocation; release is blocked')

OUTBOUND_DELETE_LINKS=(
 ('inventory allocation',OutboundInventoryAllocation,OutboundInventoryAllocation.outbound_order_id),
 ('picking list',PickingList,PickingList.outbound_order_id),
 ('BOL',BOL,BOL.outbound_order_id),
 ('scan session',ScanSession,ScanSession.outbound_id),
 ('staging transaction',StageTransaction,StageTransaction.outbound_id),
 ('load verification',LoadVerificationTransaction,LoadVerificationTransaction.outbound_id),
 ('work order',WorkOrder,WorkOrder.outbound_id),
 ('exception',OperationalException,OperationalException.outbound_id),
 ('document',OperationalDocument,OperationalDocument.outbound_id),
)
def outbound_delete_blockers(db:Session,o:OutboundOrder)->list[str]:
 blockers=[]
 if o.status!=OBStatus.NEW:blockers.append(f'Status {STATUS[o.status]} is not New')
 if o.load_id is not None:blockers.append('Outbound is assigned to a load')
 for label,model,column in OUTBOUND_DELETE_LINKS:
  if db.scalar(select(model.id).where(column==o.id).limit(1)) is not None:blockers.append(f'Outbound has a linked {label}')
 return blockers
def outbound_ids_with_delete_links(db:Session,ids:list[int])->set[int]:
 linked=set()
 if not ids:return linked
 for _,_,column in OUTBOUND_DELETE_LINKS:linked.update(db.scalars(select(column).where(column.in_(ids))).all())
 return linked
def delete_outbound_draft(db:Session,ob_id:int,user_id:int,user:User|None=None,commit=True):
 o=get_ob(db,ob_id,True,user=user);blockers=outbound_delete_blockers(db,o)
 if blockers:raise HTTPException(409,detail={'message':'Only pristine New outbound drafts can be deleted','blocking_reasons':blockers})
 before=jsonable_encoder({'id':o.id,'ob_no':o.ob_no,'status':o.status,'customer_id':o.customer_id,'warehouse_id':o.warehouse_id,'reference_no':o.reference_no})
 db.add(AuditLog(user_id=user_id,action='DELETE_OUTBOUND',entity_type='OUTBOUND',entity_id=o.id,before_data=before));db.delete(o);db.flush()
 if commit:db.commit()
 return before
FIELDS={'pallet':'pallet_qty','carton':'carton_qty','weight_lbs':'weight_lbs','cbm':'cbm'}
def totals(o):return tuple(sum((getattr(a,f'allocated_{FIELDS[x]}')-getattr(a,f'completed_{FIELDS[x]}') for a in o.allocations),ZERO) for x in FIELDS)
def read_ob(db:Session,o):
 t=totals(o);fba_ref=NamedRef(id=o.fba_shipment.id,code=o.fba_shipment.fba_no,name=o.fba_shipment.amazon_fc_code) if o.fba_shipment else None;return OBRead.model_validate({**o.__dict__,'status_name':STATUS[o.status],'customer':named(o.customer,'customer'),'warehouse':named(o.warehouse,'warehouse'),'carrier':named(o.carrier,'carrier'),'fba_shipment':fba_ref,'total_pallet_qty':sum((a.allocated_pallet_qty for a in o.allocations),ZERO),'total_carton_qty':sum((a.allocated_carton_qty for a in o.allocations),ZERO),'total_weight_lbs':sum((a.allocated_weight_lbs for a in o.allocations),ZERO),'total_cbm':sum((a.allocated_cbm for a in o.allocations),ZERO),'allocation_count':len(o.allocations),'remaining_pallet_qty':t[0],'remaining_carton_qty':t[1]})
def create_ob(db:Session,p:OBCreate,user_id:int,ob_no=None,commit=True):
 if not db.get(Warehouse,p.warehouse_id):raise HTTPException(422,'Warehouse not found')
 if p.customer_id and not db.get(Customer,p.customer_id):raise HTTPException(422,'Customer not found')
 if p.carrier_id and not db.get(Carrier,p.carrier_id):raise HTTPException(422,'Carrier not found')
 if p.fba_shipment_id:
  f=db.get(FBAShipment,p.fba_shipment_id)
  if not f or f.warehouse_id!=p.warehouse_id:raise HTTPException(422,'FBA shipment does not belong to warehouse')
  require_live_record(db,f)
 data=p.model_dump()
 related_ids=data.pop('related_outbound_ids',[])
 related=[]
 actor=db.get(User,user_id)
 for source_id in dict.fromkeys(related_ids):
  source=get_ob(db,source_id,user=actor)
  if source.warehouse_id!=p.warehouse_id:raise HTTPException(422,'Related BOL must belong to the same warehouse')
  related.append({'outbound_id':source.id,'ob_no':source.ob_no,'bol_reference':source.bol_reference})
 data['related_bols']=related
 data['schedule_pickup_at']=to_business_datetime(data.get('schedule_pickup_at'));data['delivery_appointment_time']=to_business_datetime(data.get('delivery_appointment_time'));o=OutboundOrder(**data,ob_no=ob_no or generate_ob_no(db),created_by=user_id);db.add(o);db.flush();db.add(AuditLog(user_id=user_id,action='CREATE_OUTBOUND',entity_type='OUTBOUND',entity_id=o.id,after_data=jsonable_encoder(data)))
 if commit:db.commit()
 return o
def allocate(db:Session,ob_id:int,p:AllocateRequest,user_id:int,commit=True):
 o=get_ob(db,ob_id,True)
 if o.status in (OBStatus.COMPLETED,OBStatus.CANCELED,OBStatus.DISPATCHED):raise HTTPException(409,'Outbound status does not allow allocation')
 require_allocation_mutable(db,o)
 a=db.scalar(select(OutboundInventoryAllocation).where(OutboundInventoryAllocation.outbound_order_id==o.id,OutboundInventoryAllocation.inventory_lot_id==p.inventory_lot_id).with_for_update().execution_options(populate_existing=True))
 from app.services.load_dispatch_write import lock_fba_shipments
 lock_fba_shipments(db,[o])
 lot=get_lot(db,p.inventory_lot_id,True)
 if lot.warehouse_id!=o.warehouse_id:raise HTTPException(409,'Inventory and Outbound warehouses differ')
 if o.customer_id is None or lot.customer_id!=o.customer_id:raise HTTPException(409,'Inventory and Outbound customers differ or customer is missing')
 require_live_record(db,lot.source_inbound)
 req=(p.pallet_qty,p.carton_qty,p.weight_lbs,p.cbm);fba=None
 if any(r<0 for r in req) or not any(req):raise HTTPException(422,'Allocation requires nonnegative quantities and a positive quantity')
 if o.ob_type=='FBA':
  if not o.fba_shipment_id or not p.fba_allocation_id:raise HTTPException(422,'FBA outbound requires FBA allocation')
  fba=db.scalar(select(FBAInventoryAllocation).where(FBAInventoryAllocation.id==p.fba_allocation_id,FBAInventoryAllocation.fba_shipment_id==o.fba_shipment_id).with_for_update().execution_options(populate_existing=True))
  if not fba or fba.inventory_lot_id!=lot.id:raise HTTPException(409,'Invalid FBA inventory source')
  require_live_record(db,fba.shipment)
  used=db.execute(select(*(func.coalesce(func.sum(getattr(OutboundInventoryAllocation,f'allocated_{unit}')-getattr(OutboundInventoryAllocation,f'completed_{unit}')),0) for unit in FIELDS.values())).where(OutboundInventoryAllocation.fba_allocation_id==fba.id)).one()
  if any(u<0 or r>getattr(fba,f'allocated_{FIELDS[x]}')-u for r,x,u in zip(req,FIELDS,used)):raise HTTPException(409,'Allocation exceeds remaining FBA allocation')
 else:
  if p.fba_allocation_id:raise HTTPException(422,'FBA allocation requires an FBA outbound')
  avail=(lot.available_pallet_qty,lot.available_carton_qty,lot.available_weight_lbs,lot.available_cbm)
  if any(r>a for r,a in zip(req,avail)):raise HTTPException(409,'Allocation exceeds available inventory')
 identity=identity_for_allocation(db,lot,fba)
 if a and a.fba_allocation_id!=p.fba_allocation_id:raise HTTPException(409,'Lot already allocated from a different source')
 if not fba:
  before=snapshot(lot);lot.available_pallet_qty-=p.pallet_qty;lot.available_carton_qty-=p.carton_qty;lot.available_weight_lbs-=p.weight_lbs;lot.available_cbm-=p.cbm;lot.allocated_pallet_qty+=p.pallet_qty;lot.allocated_carton_qty+=p.carton_qty;lot.allocated_weight_lbs+=p.weight_lbs;lot.allocated_cbm+=p.cbm;derive_status(lot);_tx(db,lot,TransactionType.OUTBOUND_ALLOCATE,user_id,before,p=-p.pallet_qty,c=-p.carton_qty,w=-p.weight_lbs,v=-p.cbm,reference_type='OUTBOUND',reference_id=o.id,remark=f'Allocated to {o.ob_no}')
 if a:
  a.allocated_pallet_qty+=p.pallet_qty;a.allocated_carton_qty+=p.carton_qty;a.allocated_weight_lbs+=p.weight_lbs;a.allocated_cbm+=p.cbm
 else:a=OutboundInventoryAllocation(outbound_order_id=o.id,inventory_lot_id=lot.id,fba_allocation_id=fba.id if fba else None,allocated_pallet_qty=p.pallet_qty,allocated_carton_qty=p.carton_qty,allocated_weight_lbs=p.weight_lbs,allocated_cbm=p.cbm,created_by=user_id);db.add(a)
 a.cargo_bol_id=identity.id
 db.add(AuditLog(user_id=user_id,action='ALLOCATE_OUTBOUND_INVENTORY',entity_type='OUTBOUND',entity_id=o.id,after_data=jsonable_encoder(p)));db.flush()
 if commit:db.commit()
 return a
def release(db:Session,ob_id:int,allocation_id:int,p:ReleaseRequest,user_id:int,commit=True):
 o=get_ob(db,ob_id,True);a=db.scalar(select(OutboundInventoryAllocation).where(OutboundInventoryAllocation.id==allocation_id,OutboundInventoryAllocation.outbound_order_id==ob_id).with_for_update().execution_options(populate_existing=True))
 if not a:raise HTTPException(404,'Outbound allocation not found')
 require_release_unreferenced(db,a.id)
 if o.status in (OBStatus.COMPLETED,OBStatus.DISPATCHED):raise HTTPException(409,'Completed or dispatched outbound is immutable')
 vals=(p.pallet_qty if p.pallet_qty is not None else a.allocated_pallet_qty-a.completed_pallet_qty,p.carton_qty if p.carton_qty is not None else a.allocated_carton_qty-a.completed_carton_qty,p.weight_lbs if p.weight_lbs is not None else a.allocated_weight_lbs-a.completed_weight_lbs,p.cbm if p.cbm is not None else a.allocated_cbm-a.completed_cbm);remain=(a.allocated_pallet_qty-a.completed_pallet_qty,a.allocated_carton_qty-a.completed_carton_qty,a.allocated_weight_lbs-a.completed_weight_lbs,a.allocated_cbm-a.completed_cbm)
 if any(v<0 or v>r for v,r in zip(vals,remain)):raise HTTPException(409,'Release exceeds remaining allocation')
 locked=lock_completion_inventory(db,o,[a])
 if a.fba_allocation_id is None:
  lot=locked[a.id][0];before=snapshot(lot);lot.available_pallet_qty+=vals[0];lot.available_carton_qty+=vals[1];lot.available_weight_lbs+=vals[2];lot.available_cbm+=vals[3];lot.allocated_pallet_qty-=vals[0];lot.allocated_carton_qty-=vals[1];lot.allocated_weight_lbs-=vals[2];lot.allocated_cbm-=vals[3];derive_status(lot);_tx(db,lot,TransactionType.OUTBOUND_RELEASE,user_id,before,p=vals[0],c=vals[1],w=vals[2],v=vals[3],reference_type='OUTBOUND',reference_id=o.id,remark=p.remark or 'Released')
 a.allocated_pallet_qty-=vals[0];a.allocated_carton_qty-=vals[1];a.allocated_weight_lbs-=vals[2];a.allocated_cbm-=vals[3];db.add(AuditLog(user_id=user_id,action='RELEASE_OUTBOUND_INVENTORY',entity_type='OUTBOUND',entity_id=o.id,after_data={'allocation_id':a.id}));db.flush()
 if commit:db.commit()
 return a
def allocation_read(a):
 lot=a.inventory_lot;return AllocationRead.model_validate({**a.__dict__,**document_identity(a),'lot_no':lot.lot_no,'container_number':lot.container_number,'fc_code':lot.fc_code,'location':named(lot.location,'location'),'source_type':'FBA' if a.fba_allocation_id else 'INVENTORY','fba_no':a.outbound.fba_shipment.fba_no if a.fba_allocation_id and a.outbound.fba_shipment else None})
def allocations(db:Session,o):return[allocation_read(a) for a in db.scalars(select(OutboundInventoryAllocation).options(joinedload(OutboundInventoryAllocation.inventory_lot).joinedload(InventoryLot.location),joinedload(OutboundInventoryAllocation.outbound).joinedload(OutboundOrder.fba_shipment)).where(OutboundInventoryAllocation.outbound_order_id==o.id).order_by(OutboundInventoryAllocation.id)).all()]
def change(db:Session,ob_id:int,target:int,user_id:int,exception:ExceptionRequest|None=None,*,commit:bool=True):
 o=get_ob(db,ob_id,True)
 if target==OBStatus.DISPATCHED:require_dispatch_ready(db,o)
 require_transition(o,target)
 if target==OBStatus.CONFIRMED and not o.allocations:raise HTTPException(409,'Outbound requires at least one allocation')
 if target==OBStatus.CANCELED:
  require_allocation_mutable(db,o)
  for allocation in o.allocations:require_release_unreferenced(db,allocation.id)
 now=datetime.now(UTC);before=o.status;o.status=target
 if target==OBStatus.CONFIRMED:o.confirmed_at=now;o.confirmed_by=user_id
 if target==OBStatus.DISPATCHED:o.dispatched_at=now;o.dispatched_by=user_id
 if target==OBStatus.EXCEPTION:o.exception_reason=exception.reason if exception else 'Exception';o.remark=exception.remark if exception else o.remark
 if target==OBStatus.EXCEPTION:
  create_exception(db,ExceptionCreate(exception_type=ExceptionType.OUTBOUND,severity=ExceptionSeverity.MEDIUM,title=f'Outbound {o.ob_no}: {o.exception_reason}'[:200],description=o.remark or o.exception_reason,warehouse_id=o.warehouse_id,outbound_id=o.id,load_id=o.load_id),user_id,commit=False)
 if before==OBStatus.EXCEPTION and target==OBStatus.CONFIRMED:
  for incident in db.scalars(select(OperationalException).where(OperationalException.outbound_id==o.id,OperationalException.exception_type==ExceptionType.OUTBOUND,OperationalException.status.in_((ExceptionStatus.OPEN,ExceptionStatus.INVESTIGATING))).with_for_update()).all():
   transition_exception(db,incident,ExceptionStatus.RESOLVED,user_id,'Resolved through Outbound action',commit=False)
 if target==OBStatus.CONFIRMED:
  from app.services.picking_bol import ensure_outbound_documents
  ensure_outbound_documents(db,o.id,user_id,commit=False)
 if target==OBStatus.COMPLETED:complete_all(db,o,user_id);o.completed_at=now;o.completed_by=user_id
 if target==OBStatus.CANCELED:
  for a in list(o.allocations):
   if any((a.allocated_pallet_qty-a.completed_pallet_qty,a.allocated_carton_qty-a.completed_carton_qty,a.allocated_weight_lbs-a.completed_weight_lbs,a.allocated_cbm-a.completed_cbm)):release(db,o.id,a.id,ReleaseRequest(),user_id,False)
 o.canceled_at=now if target==OBStatus.CANCELED else o.canceled_at;o.canceled_by=user_id if target==OBStatus.CANCELED else o.canceled_by;db.add(AuditLog(user_id=user_id,action='CANCEL_OUTBOUND' if target==6 else 'CHANGE_OUTBOUND_STATUS',entity_type='OUTBOUND',entity_id=o.id,before_data={'status':before},after_data={'status':target}));db.flush()
 if commit:db.commit()
 return get_ob(db,o.id)
def lock_completion_inventory(db,o,allocations):
 from app.services.load_dispatch_write import lock_fba_shipments,validate_reservation_source,validate_lot_reservations
 records=list(db.scalars(select(OutboundInventoryAllocation).where(OutboundInventoryAllocation.id.in_([a.id for a in allocations]),OutboundInventoryAllocation.outbound_order_id==o.id).order_by(OutboundInventoryAllocation.id).with_for_update().execution_options(populate_existing=True)))
 if len(records)!=len(allocations):raise HTTPException(409,'OUTBOUND_ALLOCATION_OWNERSHIP_MISMATCH')
 lock_fba_shipments(db,[o])
 lots={lot_id:get_lot(db,lot_id,True) for lot_id in sorted({a.inventory_lot_id for a in records})}
 for lot in lots.values():validate_lot_reservations(db,lot)
 result={}
 for a in records:
  lot=lots[a.inventory_lot_id]
  if o.customer_id is None or lot.warehouse_id!=o.warehouse_id or lot.customer_id!=o.customer_id:raise HTTPException(409,'INVENTORY_OWNERSHIP_MISMATCH')
  require_live_record(db,lot.source_inbound)
  rem=tuple(getattr(a,f'allocated_{unit}')-getattr(a,f'completed_{unit}') for unit in FIELDS.values())
  if any(q<0 or q>getattr(lot,f'allocated_{unit}') for unit,q in zip(FIELDS.values(),rem)):raise HTTPException(409,'INVENTORY_RESERVATION_QUANTITY_MISMATCH')
  result[a.id]=(lot,validate_reservation_source(db,o,a,lock=True))
 return result

def apply_completion(db,o,a,lot,source,vals,user_id):
 before=snapshot(lot)
 for unit,value in zip(FIELDS.values(),vals):
  setattr(lot,f'allocated_{unit}',getattr(lot,f'allocated_{unit}')-value)
  setattr(a,f'completed_{unit}',getattr(a,f'completed_{unit}')+value)
  if source is not None:setattr(source,f'allocated_{unit}',getattr(source,f'allocated_{unit}')-value)
 derive_status(lot);_tx(db,lot,TransactionType.OUTBOUND_COMPLETE,user_id,before,p=-vals[0],c=-vals[1],w=-vals[2],v=-vals[3],reference_type='OUTBOUND',reference_id=o.id,remark=f'Completed {o.ob_no}')

def complete_all(db,o,user_id):
 records=list(o.allocations);locked=lock_completion_inventory(db,o,records)
 for a in records:
  rem=tuple(getattr(a,f'allocated_{unit}')-getattr(a,f'completed_{unit}') for unit in FIELDS.values())
  if any(rem):apply_completion(db,o,a,*locked[a.id],rem,user_id)
 db.flush()

def complete_partial(db,o,user_id,req):
 a=next((x for x in o.allocations if x.id==req.allocation_id),None)
 if not a:raise HTTPException(404,'Allocation not found')
 locked=lock_completion_inventory(db,o,[a])
 vals=(req.pallet_qty or ZERO,req.carton_qty or ZERO,req.weight_lbs or ZERO,req.cbm or ZERO);rem=tuple(getattr(a,f'allocated_{unit}')-getattr(a,f'completed_{unit}') for unit in FIELDS.values())
 if any(v<0 or v>r for v,r in zip(vals,rem)) or not any(vals):raise HTTPException(409,'Completion exceeds remaining allocation or has no positive quantity')
 apply_completion(db,o,a,*locked[a.id],vals,user_id)
 db.add(AuditLog(user_id=user_id,action='COMPLETE_OUTBOUND_PARTIAL',entity_type='OUTBOUND',entity_id=o.id,after_data={'allocation_id':a.id,'quantities':list(map(str,vals))}));db.flush()
def list_outbounds(db:Session,**kw):
 page=kw.pop('page',1);per=kw.pop('per_page',20);q=kw.pop('q',None);user=kw.pop('user',None);filters=[]
 if user:filters.extend(x for x in (warehouse_clause(user,OutboundOrder.warehouse_id),customer_clause(user,OutboundOrder.customer_id)) if x is not None)
 if q:
  t=f'%{q}%';filters.append(or_(OutboundOrder.ob_no.ilike(t),OutboundOrder.reference_no.ilike(t),OutboundOrder.fc_code.ilike(t),OutboundOrder.del_code.ilike(t),OutboundOrder.agent_code.ilike(t),OutboundOrder.truck_number.ilike(t),OutboundOrder.trailer_number.ilike(t),OutboundOrder.driver_name.ilike(t),OutboundOrder.remark.ilike(t)))
 for key,col in [('ob_no',OutboundOrder.ob_no),('status',OutboundOrder.status),('ob_type',OutboundOrder.ob_type),('customer_id',OutboundOrder.customer_id),('warehouse_id',OutboundOrder.warehouse_id),('carrier_id',OutboundOrder.carrier_id),('fba_shipment_id',OutboundOrder.fba_shipment_id),('fc_code',OutboundOrder.fc_code),('del_code',OutboundOrder.del_code),('agent_code',OutboundOrder.agent_code)]:
  if kw.get(key) is not None:filters.append(col.ilike(f"%{kw[key]}%") if isinstance(kw[key],str) else col==kw[key])
 items=[read_ob(db,o) for o in db.scalars(query().where(*filters)).all()];key=kw.get('sort_by','id');items.sort(key=lambda x:getattr(x,key,None)or 0,reverse=kw.get('sort_order','desc')!='asc');total=len(items);return {'data':items[(page-1)*per:page*per],'meta':PaginationMeta(page=page,per_page=per,total=total,total_pages=ceil(total/per)if total else 0)}
