from datetime import date
from decimal import Decimal
from math import ceil
from typing import Any
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func,or_,select,text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session,joinedload,selectinload
from app.models import AuditLog,InboundLine,InboundRecord,InventoryLot,InventoryPriorityRule,InventoryTransaction,User,WarehouseLocation
from app.services.access_policy import customer_clause,warehouse_clause
from app.models.inventory import InventoryStatus,TransactionType
from app.schemas.inbound import NamedRef,PaginationMeta,UserRef
from app.schemas.inventory import AdjustmentRequest,HoldRequest,InventoryListResponse,InventoryRead,MoveRequest,TransactionRead
from app.utils.business_time import get_business_today

ZERO=Decimal("0")
def generate_lot_no(db:Session,today:date|None=None)->str:
    day=today or get_business_today();prefix=f"LOT{day:%y%m%d}"
    if db.bind and db.bind.dialect.name=="postgresql":db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),{"key":prefix})
    last=db.scalar(select(func.max(InventoryLot.lot_no)).where(InventoryLot.lot_no.like(f"{prefix}%")));return f"{prefix}{(int(last[-4:])+1 if last else 1):04d}"
def snapshot(lot:InventoryLot)->dict[str,Any]:
    keys=("location_id","status","original_pallet_qty","available_pallet_qty","allocated_pallet_qty","hold_pallet_qty","original_carton_qty","available_carton_qty","allocated_carton_qty","hold_carton_qty","original_weight_lbs","available_weight_lbs","allocated_weight_lbs","original_cbm","available_cbm","allocated_cbm")
    return jsonable_encoder({k:getattr(lot,k) for k in keys})
def derive_status(lot:InventoryLot)->None:
    available=lot.available_pallet_qty+lot.available_carton_qty;allocated=lot.allocated_pallet_qty+lot.allocated_carton_qty;held=lot.hold_pallet_qty+lot.hold_carton_qty;original=lot.original_pallet_qty+lot.original_carton_qty
    if available==0 and allocated==0 and held==0 and original>0:lot.status=InventoryStatus.DEPLETED
    elif available==0 and held>0:lot.status=InventoryStatus.HOLD
    elif available==0 and allocated>0:lot.status=InventoryStatus.FULLY_ALLOCATED
    elif allocated>0 and available>0:lot.status=InventoryStatus.PARTIALLY_ALLOCATED
    else:lot.status=InventoryStatus.AVAILABLE
def _priority(db:Session,aging:int|None)->tuple[str|None,str|None]:
    if aging is None:return None,None
    rule=db.scalar(select(InventoryPriorityRule).where(InventoryPriorityRule.is_active.is_(True),InventoryPriorityRule.min_days<=aging,or_(InventoryPriorityRule.max_days.is_(None),InventoryPriorityRule.max_days>=aging)).order_by(InventoryPriorityRule.sort_order.desc()).limit(1));return (rule.priority_level,rule.priority_label) if rule else (None,None)
def _named(obj:Any,kind:str)->NamedRef|None:
    if obj is None:return None
    return NamedRef(id=obj.id,code=getattr(obj,f"{kind}_code"),name=getattr(obj,f"{kind}_name"))
def read_inventory(db:Session,lot:InventoryLot)->InventoryRead:
    aging=max(0,(get_business_today()-lot.inbound_date).days) if lot.inbound_date else None;level,label=_priority(db,aging)
    return InventoryRead.model_validate({**lot.__dict__,"customer":_named(lot.customer,"customer"),"warehouse":_named(lot.warehouse,"warehouse"),"location":_named(lot.location,"location"),"aging_days":aging,"priority_level":level,"priority_label":label,"status_name":InventoryStatus(lot.status).name.replace("_"," ").title()})
def _base_query():return select(InventoryLot).options(joinedload(InventoryLot.customer),joinedload(InventoryLot.warehouse),joinedload(InventoryLot.location),joinedload(InventoryLot.creator))
def get_lot(db:Session,lot_id:int,lock:bool=False,user:User|None=None)->InventoryLot:
    filters=[InventoryLot.id==lot_id]
    if user:filters.extend(x for x in (warehouse_clause(user,InventoryLot.warehouse_id),customer_clause(user,InventoryLot.customer_id)) if x is not None)
    query=select(InventoryLot).where(*filters).with_for_update() if lock else _base_query().where(*filters)
    lot=db.scalar(query)
    if lot is None:raise HTTPException(404,"Inventory lot not found")
    return lot
def _receive_lot(db:Session,inbound:InboundRecord,line:InboundLine,user_id:int)->InventoryLot:
    p=line.pallet_qty or ZERO;c=line.carton_qty or ZERO;w=line.weight_lbs or ZERO;v=line.cbm or ZERO
    lot=InventoryLot(lot_no=generate_lot_no(db),customer_id=inbound.customer_id,warehouse_id=inbound.warehouse_id,source_inbound_id=inbound.id,inbound_line_id=line.id,container_number=inbound.container_number,fc_code=line.fc_code,marking=inbound.marking,location_id=line.location_id,raw_location_text=inbound.raw_location_text,import_row_id=inbound.import_row_id,original_pallet_qty=p,original_carton_qty=c,original_weight_lbs=w,original_cbm=v,available_pallet_qty=p,available_carton_qty=c,available_weight_lbs=w,available_cbm=v,allocated_pallet_qty=ZERO,allocated_carton_qty=ZERO,allocated_weight_lbs=ZERO,allocated_cbm=ZERO,hold_pallet_qty=ZERO,hold_carton_qty=ZERO,inbound_date=inbound.received_date or inbound.unload_date,status=InventoryStatus.AVAILABLE,remark=line.remark or inbound.remark,created_by=user_id)
    db.add(lot);db.flush();after=snapshot(lot)
    db.add(InventoryTransaction(inventory_lot_id=lot.id,transaction_type=TransactionType.INBOUND,pallet_delta=p,carton_delta=c,weight_delta=w,cbm_delta=v,to_location_id=lot.location_id,reference_type="INBOUND",reference_id=inbound.id,after_snapshot=after,remark=f"Received from inbound line {line.line_no}",created_by=user_id))
    db.add(AuditLog(user_id=user_id,action="CREATE_INVENTORY_FROM_INBOUND",entity_type="INVENTORY",entity_id=lot.id,after_data=after))
    return lot

def receive_inbound_lines(db:Session,inbound_id:int,user_id:int,commit:bool=True,user:User|None=None)->list[InventoryLot]:
    filters=[InboundRecord.id==inbound_id]
    if user:filters.extend(x for x in (warehouse_clause(user,InboundRecord.warehouse_id),customer_clause(user,InboundRecord.customer_id)) if x is not None)
    inbound=db.scalar(select(InboundRecord).options(selectinload(InboundRecord.lines),selectinload(InboundRecord.inventory_lots)).where(*filters).with_for_update())
    if inbound is None:raise HTTPException(404,"Inbound record not found")
    if inbound.status in (2,6):raise HTTPException(409,"Inbound is already received or canceled")
    if inbound.status not in (0,1,3,4):raise HTTPException(409,"Inbound cannot be received in its current status")
    if inbound.inventory_lots:raise HTTPException(409,"Inventory already created for this inbound")
    if not inbound.lines:raise HTTPException(409,"Inbound has no lines")
    try:
        lots=[_receive_lot(db,inbound,line,user_id) for line in inbound.lines]
        inbound.status=2
        inbound.received_date=inbound.received_date or get_business_today()
        db.add(AuditLog(user_id=user_id,action="RECEIVE",entity_type="INBOUND",entity_id=inbound.id,after_data={"inventory_lot_ids":[lot.id for lot in lots]}))
        if commit:db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,"Inbound was received concurrently")
    except Exception:
        db.rollback()
        raise
    if commit:return [get_lot(db,lot.id,user=user) for lot in lots]
    return lots

def receive_inbound(db:Session,inbound_id:int,user_id:int,commit:bool=True)->InventoryLot:
    return receive_inbound_lines(db,inbound_id,user_id,commit=commit)[0]

def cancel_inbound(db:Session,inbound_id:int,user_id:int,user:User|None=None)->InboundRecord:
    filters=[InboundRecord.id==inbound_id]
    if user:filters.extend(x for x in (warehouse_clause(user,InboundRecord.warehouse_id),customer_clause(user,InboundRecord.customer_id)) if x is not None)
    inbound=db.scalar(select(InboundRecord).where(*filters).with_for_update())
    if inbound is None:raise HTTPException(404,"Inbound record not found")
    if inbound.status!=0:raise HTTPException(409,"Only draft inbound records can be canceled")
    if db.scalar(select(InventoryLot.id).where(InventoryLot.source_inbound_id==inbound.id).limit(1)):raise HTTPException(409,"Inbound with inventory cannot be canceled")
    inbound.status=6
    db.add(AuditLog(user_id=user_id,action="CANCEL",entity_type="INBOUND",entity_id=inbound.id,after_data={"status":6}))
    db.commit()
    return inbound
def list_inventory(db:Session,*,page:int=1,per_page:int=20,q:str|None=None,container_number:str|None=None,fc_code:str|None=None,customer_id:int|None=None,warehouse_id:int|None=None,location_id:int|None=None,status:int|None=None,priority_level:str|None=None,inbound_date_from:date|None=None,inbound_date_to:date|None=None,aging_min:int|None=None,aging_max:int|None=None,has_available:bool|None=None,sort_by:str="id",sort_order:str="desc",user:User|None=None)->InventoryListResponse:
    filters=[]
    if user:filters.extend(x for x in (warehouse_clause(user,InventoryLot.warehouse_id),customer_clause(user,InventoryLot.customer_id)) if x is not None)
    if q:
        term=f"%{q}%";filters.append(or_(InventoryLot.lot_no.ilike(term),InventoryLot.container_number.ilike(term),InventoryLot.fc_code.ilike(term),InventoryLot.marking.ilike(term),InventoryLot.remark.ilike(term)))
    for val,col in ((container_number,InventoryLot.container_number),(fc_code,InventoryLot.fc_code),(customer_id,InventoryLot.customer_id),(warehouse_id,InventoryLot.warehouse_id),(location_id,InventoryLot.location_id),(status,InventoryLot.status)):
        if val is not None:filters.append(col.ilike(f"%{val}%") if isinstance(val,str) else col==val)
    if inbound_date_from:filters.append(InventoryLot.inbound_date>=inbound_date_from)
    if inbound_date_to:filters.append(InventoryLot.inbound_date<=inbound_date_to)
    if has_available is True:filters.append(or_(InventoryLot.available_pallet_qty>0,InventoryLot.available_carton_qty>0))
    if has_available is False:filters.append(InventoryLot.available_pallet_qty==0,InventoryLot.available_carton_qty==0)
    lots=list(db.scalars(_base_query().where(*filters)).all());items=[read_inventory(db,x) for x in lots];items=[x for x in items if (priority_level is None or x.priority_level==priority_level) and (aging_min is None or (x.aging_days is not None and x.aging_days>=aging_min)) and (aging_max is None or (x.aging_days is not None and x.aging_days<=aging_max))]
    key=lambda x:getattr(x,sort_by,None)or 0;items.sort(key=key,reverse=sort_order!="asc");total=len(items);return InventoryListResponse(data=items[(page-1)*per_page:page*per_page],meta=PaginationMeta(page=page,per_page=per_page,total=total,total_pages=ceil(total/per_page)if total else 0))
def _tx(db:Session,lot:InventoryLot,kind:TransactionType,user_id:int,before:dict,*,p:Decimal=ZERO,c:Decimal=ZERO,w:Decimal=ZERO,v:Decimal=ZERO,from_id:int|None=None,to_id:int|None=None,remark:str|None=None,reference_type:str|None=None,reference_id:int|None=None)->None:
    after=snapshot(lot);db.add(InventoryTransaction(inventory_lot_id=lot.id,transaction_type=kind,pallet_delta=p,carton_delta=c,weight_delta=w,cbm_delta=v,from_location_id=from_id,to_location_id=to_id,reference_type=reference_type,reference_id=reference_id,before_snapshot=before,after_snapshot=after,remark=remark,created_by=user_id));db.add(AuditLog(user_id=user_id,action=f"{kind.value}_INVENTORY",entity_type="INVENTORY",entity_id=lot.id,before_data=before,after_data=after))
def move(db:Session,lot_id:int,payload:MoveRequest,user_id:int)->InventoryLot:
    lot=get_lot(db,lot_id,True);location=db.get(WarehouseLocation,payload.to_location_id)
    if location is None or location.warehouse_id!=lot.warehouse_id:raise HTTPException(422,"Location must belong to the same warehouse")
    before=snapshot(lot);old=lot.location_id;lot.location_id=location.id;_tx(db,lot,TransactionType.MOVE,user_id,before,from_id=old,to_id=location.id,remark=payload.remark);db.commit();db.expire(lot);return get_lot(db,lot.id)
def adjust(db:Session,lot_id:int,payload:AdjustmentRequest,user_id:int)->InventoryLot:
    lot=get_lot(db,lot_id,True);before=snapshot(lot);pairs=(("pallet",payload.pallet_delta),("carton",payload.carton_delta),("weight_lbs",payload.weight_delta),("cbm",payload.cbm_delta))
    for name,delta in pairs:
        available=f"available_{name}_qty" if name in ("pallet","carton") else f"available_{name}";original=f"original_{name}_qty" if name in ("pallet","carton") else f"original_{name}";new=getattr(lot,available)+delta
        if new<0:raise HTTPException(409,f"Adjustment would make {available} negative")
        new_original=getattr(lot,original)+delta
        allocated=getattr(lot,f"allocated_{name}_qty" if name in ("pallet","carton") else f"allocated_{name}");held=getattr(lot,f"hold_{name}_qty",ZERO)
        if new_original<allocated+held:raise HTTPException(409,"Adjustment conflicts with allocated or held quantity")
        setattr(lot,available,new);setattr(lot,original,new_original)
    derive_status(lot);_tx(db,lot,TransactionType.ADJUSTMENT,user_id,before,p=payload.pallet_delta,c=payload.carton_delta,w=payload.weight_delta,v=payload.cbm_delta,remark=f"{payload.reason}: {payload.remark or ''}".strip());db.commit();return get_lot(db,lot.id)
def hold(db:Session,lot_id:int,payload:HoldRequest,user_id:int)->InventoryLot:
    lot=get_lot(db,lot_id,True)
    if payload.pallet_qty>lot.available_pallet_qty or payload.carton_qty>lot.available_carton_qty:raise HTTPException(409,"Hold exceeds available inventory")
    before=snapshot(lot);lot.available_pallet_qty-=payload.pallet_qty;lot.available_carton_qty-=payload.carton_qty;lot.hold_pallet_qty+=payload.pallet_qty;lot.hold_carton_qty+=payload.carton_qty;derive_status(lot);_tx(db,lot,TransactionType.HOLD,user_id,before,p=-payload.pallet_qty,c=-payload.carton_qty,remark=payload.remark);db.commit();return get_lot(db,lot.id)
def release(db:Session,lot_id:int,payload:HoldRequest,user_id:int)->InventoryLot:
    lot=get_lot(db,lot_id,True)
    if payload.pallet_qty>lot.hold_pallet_qty or payload.carton_qty>lot.hold_carton_qty:raise HTTPException(409,"Release exceeds held inventory")
    before=snapshot(lot);lot.hold_pallet_qty-=payload.pallet_qty;lot.hold_carton_qty-=payload.carton_qty;lot.available_pallet_qty+=payload.pallet_qty;lot.available_carton_qty+=payload.carton_qty;derive_status(lot);_tx(db,lot,TransactionType.RELEASE,user_id,before,p=payload.pallet_qty,c=payload.carton_qty,remark=payload.remark);db.commit();return get_lot(db,lot.id)
def transactions(db:Session,lot_id:int)->list[TransactionRead]:
    get_lot(db,lot_id);rows=db.scalars(select(InventoryTransaction).options(joinedload(InventoryTransaction.from_location),joinedload(InventoryTransaction.to_location),joinedload(InventoryTransaction.creator)).where(InventoryTransaction.inventory_lot_id==lot_id).order_by(InventoryTransaction.created_at.desc(),InventoryTransaction.id.desc())).all();return[TransactionRead.model_validate({**x.__dict__,"transaction_type":x.transaction_type.value,"from_location":_named(x.from_location,"location"),"to_location":_named(x.to_location,"location"),"created_by":UserRef(id=x.creator.id,display_name=x.creator.display_name)})for x in rows]
