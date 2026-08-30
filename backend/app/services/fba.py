from datetime import date
from decimal import Decimal
from math import ceil
from statistics import mean
from typing import Any
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func,or_,select,text
from sqlalchemy.orm import Session,joinedload,selectinload
from app.models import AmazonFCAddress,AuditLog,Carrier,Customer,FBAInventoryAllocation,FBAShipment,InventoryLot,User,Warehouse
from app.models.fba import FBAStatus
from app.models.inventory import TransactionType
from app.schemas.fba import AllocateRequest,AllocationRead,FBACreate,FBAListResponse,FBARead,FBAUpdate,ReleaseRequest
from app.schemas.inbound import NamedRef,PaginationMeta,UserRef
from app.services.inventory import ZERO,_priority,_tx,derive_status,get_lot,snapshot
from app.services.access_policy import customer_clause,warehouse_clause
from app.utils.business_time import get_business_today,to_business_datetime

STATUS_NAMES={x.value:x.name.replace("_"," ").title()for x in FBAStatus};PRIORITY_RANK={"GREEN":1,"YELLOW":2,"ORANGE":3,"RED":4}
def generate_fba_no(db:Session,today:date|None=None)->str:
    day=today or get_business_today();prefix=f"FBA{day:%y%m%d}"
    if db.bind and db.bind.dialect.name=="postgresql":db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),{"key":prefix})
    last=db.scalar(select(func.max(FBAShipment.fba_no)).where(FBAShipment.fba_no.like(f"{prefix}%")));return f"{prefix}{(int(last[-4:])+1 if last else 1):04d}"
def _named(obj:Any,kind:str)->NamedRef|None:
    if obj is None:return None
    return NamedRef(id=obj.id,code=getattr(obj,f"{kind}_code"),name=getattr(obj,f"{kind}_name"))
def _query():return select(FBAShipment).options(joinedload(FBAShipment.customer),joinedload(FBAShipment.warehouse),joinedload(FBAShipment.amazon_fc_address),joinedload(FBAShipment.carrier),joinedload(FBAShipment.creator),selectinload(FBAShipment.allocations).joinedload(FBAInventoryAllocation.inventory_lot))
def get_fba(db:Session,fba_id:int,lock:bool=False,user:User|None=None)->FBAShipment:
    q=(select(FBAShipment).where(FBAShipment.id==fba_id).with_for_update()) if lock else _query().where(FBAShipment.id==fba_id)
    if user:
        clauses=(warehouse_clause(user,FBAShipment.warehouse_id),customer_clause(user,FBAShipment.customer_id))
        q=q.where(*(clause for clause in clauses if clause is not None))
    shipment=db.scalar(q)
    if shipment is None:raise HTTPException(404,"FBA shipment not found")
    return shipment
def read_fba(db:Session,s:FBAShipment)->FBARead:
    active=[a for a in s.allocations if any((a.allocated_pallet_qty,a.allocated_carton_qty,a.allocated_weight_lbs,a.allocated_cbm))];lots=[a.inventory_lot for a in active];dates=[x.inbound_date for x in lots if x.inbound_date];agings=[max(0,(get_business_today()-x).days)for x in dates];priorities=[_priority(db,x)for x in agings];highest=max(priorities,key=lambda p:PRIORITY_RANK.get(p[0]or"",0),default=(None,None));address=s.amazon_fc_address;formatted=None
    if address:formatted=", ".join(x for x in(address.address_line1,address.address_line2,address.city,address.state,address.zip_code,address.country)if x)
    return FBARead.model_validate({**s.__dict__,"customer":_named(s.customer,"customer"),"warehouse":_named(s.warehouse,"warehouse"),"carrier":_named(s.carrier,"carrier"),"amazon_fc_name":address.fc_name if address else None,"amazon_fc_address":formatted,"fc_address_missing":address is None,"status_name":STATUS_NAMES[s.status],"total_pallet_qty":sum((a.allocated_pallet_qty for a in active),ZERO),"total_carton_qty":sum((a.allocated_carton_qty for a in active),ZERO),"total_weight_lbs":sum((a.allocated_weight_lbs for a in active),ZERO),"total_cbm":sum((a.allocated_cbm for a in active),ZERO),"inventory_lot_count":len(active),"containers":sorted({x.container_number for x in lots}),"oldest_inbound_date":min(dates)if dates else None,"min_aging_days":min(agings)if agings else None,"max_aging_days":max(agings)if agings else None,"average_aging_days":Decimal(str(round(mean(agings),2)))if agings else None,"priority_level":highest[0],"priority_label":highest[1],"created_by":UserRef(id=s.creator.id,display_name=s.creator.display_name)})
def create_fba(db:Session,p:FBACreate,user_id:int,fba_no:str|None=None,commit=True)->FBAShipment:
    if db.get(Warehouse,p.warehouse_id)is None:raise HTTPException(422,"Warehouse not found")
    if p.customer_id and db.get(Customer,p.customer_id)is None:raise HTTPException(422,"Customer not found")
    if p.carrier_id and db.get(Carrier,p.carrier_id)is None:raise HTTPException(422,"Carrier not found")
    code=p.amazon_fc_code.strip().upper();address=db.scalar(select(AmazonFCAddress).where(AmazonFCAddress.fc_code==code));data=p.model_dump(exclude={"amazon_fc_code"});data['scheduled_pickup_at']=to_business_datetime(data.get('scheduled_pickup_at'));data['appointment_time']=to_business_datetime(data.get('appointment_time'));s=FBAShipment(**data,fba_no=fba_no or generate_fba_no(db),amazon_fc_code=code,amazon_fc_address_id=address.id if address else None,status=FBAStatus.DRAFT,created_by=user_id);db.add(s);db.flush();db.add(AuditLog(user_id=user_id,action="CREATE_FBA",entity_type="FBA",entity_id=s.id,after_data=jsonable_encoder(data)))
    if commit:db.commit()
    return s
def update_fba(db:Session,s:FBAShipment,p:FBAUpdate,user_id:int)->FBAShipment:
    before=jsonable_encoder({k:getattr(s,k)for k in type(p).model_fields});code=p.amazon_fc_code.strip().upper();address=db.scalar(select(AmazonFCAddress).where(AmazonFCAddress.fc_code==code));
    data=p.model_dump(exclude={"amazon_fc_code"});data['scheduled_pickup_at']=to_business_datetime(data.get('scheduled_pickup_at'));data['appointment_time']=to_business_datetime(data.get('appointment_time'))
    for k,v in data.items():setattr(s,k,v)
    s.amazon_fc_code=code;s.amazon_fc_address_id=address.id if address else None;db.add(AuditLog(user_id=user_id,action="UPDATE_FBA",entity_type="FBA",entity_id=s.id,before_data=before,after_data=jsonable_encoder(p)));db.commit();return get_fba(db,s.id)
def allocation_read(db:Session,s:FBAShipment,a:FBAInventoryAllocation)->AllocationRead:
    lot=a.inventory_lot;aging=max(0,(get_business_today()-lot.inbound_date).days)if lot.inbound_date else None;priority=_priority(db,aging);return AllocationRead.model_validate({**a.__dict__,"lot_no":lot.lot_no,"container_number":lot.container_number,"fc_code":lot.fc_code,"location":_named(lot.location,"location"),"inbound_date":lot.inbound_date,"aging_days":aging,"priority_level":priority[0],"priority_label":priority[1],"inventory_available_pallet_qty":lot.available_pallet_qty,"inventory_available_carton_qty":lot.available_carton_qty,"inventory_available_weight_lbs":lot.available_weight_lbs,"inventory_available_cbm":lot.available_cbm,"fc_mismatch":bool(lot.fc_code and lot.fc_code.upper()!=s.amazon_fc_code.upper()),"created_by":UserRef(id=a.creator.id,display_name=a.creator.display_name)})
def allocate(db:Session,fba_id:int,p:AllocateRequest,user_id:int,commit=True)->FBAInventoryAllocation:
    s=get_fba(db,fba_id,True)
    if s.status in(FBAStatus.COMPLETED,FBAStatus.CANCELED):raise HTTPException(409,"FBA status does not allow allocation")
    lot=get_lot(db,p.inventory_lot_id,True)
    if lot.warehouse_id!=s.warehouse_id:raise HTTPException(409,"Inventory and FBA warehouses differ")
    mismatch=bool(lot.fc_code and lot.fc_code.upper()!=s.amazon_fc_code.upper())
    if mismatch and not p.confirm_fc_mismatch:raise HTTPException(409,{"message":"Inventory FC differs from FBA FC","fc_mismatch":True})
    requested=(p.pallet_qty,p.carton_qty,p.weight_lbs,p.cbm);available=(lot.available_pallet_qty,lot.available_carton_qty,lot.available_weight_lbs,lot.available_cbm)
    if not any(requested):raise HTTPException(422,"At least one allocation quantity is required")
    if any(r>a for r,a in zip(requested,available)):raise HTTPException(409,"Allocation exceeds currently available inventory")
    before=snapshot(lot);lot.available_pallet_qty-=p.pallet_qty;lot.available_carton_qty-=p.carton_qty;lot.available_weight_lbs-=p.weight_lbs;lot.available_cbm-=p.cbm;lot.allocated_pallet_qty+=p.pallet_qty;lot.allocated_carton_qty+=p.carton_qty;lot.allocated_weight_lbs+=p.weight_lbs;lot.allocated_cbm+=p.cbm;derive_status(lot);a=db.scalar(select(FBAInventoryAllocation).where(FBAInventoryAllocation.fba_shipment_id==s.id,FBAInventoryAllocation.inventory_lot_id==lot.id).with_for_update())
    if a:
        a.allocated_pallet_qty+=p.pallet_qty;a.allocated_carton_qty+=p.carton_qty;a.allocated_weight_lbs+=p.weight_lbs;a.allocated_cbm+=p.cbm
    else:a=FBAInventoryAllocation(fba_shipment_id=s.id,inventory_lot_id=lot.id,allocated_pallet_qty=p.pallet_qty,allocated_carton_qty=p.carton_qty,allocated_weight_lbs=p.weight_lbs,allocated_cbm=p.cbm,created_by=user_id);db.add(a)
    if s.status in(FBAStatus.DRAFT,FBAStatus.PLANNING):s.status=FBAStatus.ALLOCATED
    _tx(db,lot,TransactionType.FBA_ALLOCATE,user_id,before,p=-p.pallet_qty,c=-p.carton_qty,w=-p.weight_lbs,v=-p.cbm,reference_type="FBA",reference_id=s.id,remark=f"Allocated to {s.fba_no}");db.add(AuditLog(user_id=user_id,action="ALLOCATE_FBA_INVENTORY",entity_type="FBA",entity_id=s.id,after_data=jsonable_encoder(p)));db.flush()
    if commit:db.commit()
    return a
def release(db:Session,fba_id:int,allocation_id:int,p:ReleaseRequest,user_id:int,commit=True)->FBAInventoryAllocation:
    s=get_fba(db,fba_id,True);a=db.scalar(select(FBAInventoryAllocation).where(FBAInventoryAllocation.id==allocation_id,FBAInventoryAllocation.fba_shipment_id==fba_id).with_for_update())
    if a is None:raise HTTPException(404,"Allocation not found")
    lot=get_lot(db,a.inventory_lot_id,True);vals=(p.pallet_qty if p.pallet_qty is not None else a.allocated_pallet_qty,p.carton_qty if p.carton_qty is not None else a.allocated_carton_qty,p.weight_lbs if p.weight_lbs is not None else a.allocated_weight_lbs,p.cbm if p.cbm is not None else a.allocated_cbm);current=(a.allocated_pallet_qty,a.allocated_carton_qty,a.allocated_weight_lbs,a.allocated_cbm)
    if not any(vals):raise HTTPException(422,"No quantity to release")
    if any(v>c for v,c in zip(vals,current)):raise HTTPException(409,"Release exceeds allocation")
    before=snapshot(lot);pallet,carton,weight,cbm=vals;a.allocated_pallet_qty-=pallet;a.allocated_carton_qty-=carton;a.allocated_weight_lbs-=weight;a.allocated_cbm-=cbm;lot.available_pallet_qty+=pallet;lot.available_carton_qty+=carton;lot.available_weight_lbs+=weight;lot.available_cbm+=cbm;lot.allocated_pallet_qty-=pallet;lot.allocated_carton_qty-=carton;lot.allocated_weight_lbs-=weight;lot.allocated_cbm-=cbm;derive_status(lot);_tx(db,lot,TransactionType.FBA_RELEASE,user_id,before,p=pallet,c=carton,w=weight,v=cbm,reference_type="FBA",reference_id=s.id,remark=p.remark or f"Released from {s.fba_no}");db.add(AuditLog(user_id=user_id,action="RELEASE_FBA_INVENTORY",entity_type="FBA",entity_id=s.id,after_data={"allocation_id":a.id,"pallet":str(pallet),"carton":str(carton)}))
    if commit:db.commit()
    return a
def allocation_list(db:Session,s:FBAShipment)->list[AllocationRead]:
    rows=db.scalars(select(FBAInventoryAllocation).options(joinedload(FBAInventoryAllocation.inventory_lot).joinedload(InventoryLot.location),joinedload(FBAInventoryAllocation.creator)).where(FBAInventoryAllocation.fba_shipment_id==s.id).order_by(FBAInventoryAllocation.id)).all();return[allocation_read(db,s,a)for a in rows]
def list_fba(db:Session,*,page=1,per_page=20,q=None,fba_no=None,customer_id=None,warehouse_id=None,amazon_fc_code=None,carrier_id=None,status=None,container_number=None,location_id=None,priority_level=None,aging_min=None,aging_max=None,appointment_from=None,appointment_to=None,sort_by="id",sort_order="desc",user:User|None=None)->FBAListResponse:
    filters=[]
    if user:filters.extend(x for x in (warehouse_clause(user,FBAShipment.warehouse_id),customer_clause(user,FBAShipment.customer_id)) if x is not None)
    if q:
        term=f"%{q}%";filters.append(or_(FBAShipment.fba_no.ilike(term),FBAShipment.amazon_fc_code.ilike(term),FBAShipment.reference_no.ilike(term),FBAShipment.shipment_id.ilike(term),FBAShipment.st_number.ilike(term),FBAShipment.remark.ilike(term),FBAShipment.allocations.any(FBAInventoryAllocation.inventory_lot.has(or_(InventoryLot.container_number.ilike(term),InventoryLot.lot_no.ilike(term))))))
    for val,col in((fba_no,FBAShipment.fba_no),(customer_id,FBAShipment.customer_id),(warehouse_id,FBAShipment.warehouse_id),(amazon_fc_code,FBAShipment.amazon_fc_code),(carrier_id,FBAShipment.carrier_id),(status,FBAShipment.status)):
        if val is not None:filters.append(col.ilike(f"%{val}%")if isinstance(val,str)else col==val)
    if container_number:filters.append(FBAShipment.allocations.any(FBAInventoryAllocation.inventory_lot.has(InventoryLot.container_number.ilike(f"%{container_number}%"))))
    if location_id:filters.append(FBAShipment.allocations.any(FBAInventoryAllocation.inventory_lot.has(InventoryLot.location_id==location_id)))
    if appointment_from:filters.append(FBAShipment.appointment_time>=appointment_from)
    if appointment_to:filters.append(FBAShipment.appointment_time<=appointment_to)
    items=[read_fba(db,x)for x in db.scalars(_query().where(*filters)).all()];items=[x for x in items if(priority_level is None or x.priority_level==priority_level)and(aging_min is None or(x.max_aging_days is not None and x.max_aging_days>=aging_min))and(aging_max is None or(x.max_aging_days is not None and x.max_aging_days<=aging_max))];key=lambda x:getattr(x,sort_by,None)or 0;items.sort(key=key,reverse=sort_order!="asc");total=len(items);return FBAListResponse(data=items[(page-1)*per_page:page*per_page],meta=PaginationMeta(page=page,per_page=per_page,total=total,total_pages=ceil(total/per_page)if total else 0))
TRANSITIONS={0:{1,8,9},1:{2,8,9},2:{3,8,9},3:{4,8,9},4:{5,8,9},5:{6},6:{7},8:{1,9}}
def change_status(db:Session,fba_id:int,target:int,user_id:int)->FBAShipment:
    s=get_fba(db,fba_id,True)
    if target not in TRANSITIONS.get(s.status,set()):raise HTTPException(409,f"Invalid status transition: {STATUS_NAMES[s.status]} to {STATUS_NAMES.get(target,'Unknown')}")
    before=s.status
    if target==FBAStatus.CANCELED:
        allocations=list(db.scalars(select(FBAInventoryAllocation).where(FBAInventoryAllocation.fba_shipment_id==s.id).with_for_update()).all())
        for a in allocations:
            if any((a.allocated_pallet_qty,a.allocated_carton_qty,a.allocated_weight_lbs,a.allocated_cbm)):release(db,s.id,a.id,ReleaseRequest(remark="Released by FBA cancellation"),user_id,False)
    s.status=target;db.add(AuditLog(user_id=user_id,action="CANCEL_FBA"if target==9 else"CHANGE_FBA_STATUS",entity_type="FBA",entity_id=s.id,before_data={"status":before},after_data={"status":target}));db.commit();return get_fba(db,s.id)
