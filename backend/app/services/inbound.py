from app.services.history_policy import require_live_record
from datetime import date
from math import ceil
from fastapi import HTTPException,status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.orm import Session, joinedload
from app.models import AuditLog, Customer, InboundRecord, User, Warehouse, WarehouseLocation
from app.services.access_policy import customer_clause, warehouse_clause
from app.schemas.inbound import InboundCreate,InboundListParams,InboundListResponse,InboundRead,InboundUpdate,NamedRef,PaginationMeta,UserRef
from app.utils.business_time import get_business_today

SORTABLE={"id":InboundRecord.id,"inbound_no":InboundRecord.inbound_no,"container_number":InboundRecord.container_number,"unload_date":InboundRecord.unload_date,"received_date":InboundRecord.received_date,"fc_code":InboundRecord.fc_code,"pallet_qty":InboundRecord.pallet_qty,"created_at":InboundRecord.created_at}
def _validate_refs(db:Session,payload:InboundCreate|InboundUpdate)->None:
    if db.get(Warehouse,payload.warehouse_id) is None:raise HTTPException(422,"Warehouse not found")
    if payload.customer_id and db.get(Customer,payload.customer_id) is None:raise HTTPException(422,"Customer not found")
    if payload.location_id:
        loc=db.get(WarehouseLocation,payload.location_id)
        if loc is None or loc.warehouse_id!=payload.warehouse_id:raise HTTPException(422,"Location does not belong to warehouse")
def generate_inbound_no(db:Session,today:date|None=None)->str:
    day=today or get_business_today();prefix=f"IB{day:%y%m%d}"
    if db.bind and db.bind.dialect.name=="postgresql":db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),{"key":prefix})
    last=db.scalar(select(func.max(InboundRecord.inbound_no)).where(InboundRecord.inbound_no.like(f"{prefix}%")))
    return f"{prefix}{(int(last[-4:])+1 if last else 1):04d}"
def _read(row:InboundRecord)->InboundRead:
    return InboundRead.model_validate({**row.__dict__,"customer":NamedRef(id=row.customer.id,code=row.customer.customer_code,name=row.customer.customer_name) if row.customer else None,"warehouse":NamedRef(id=row.warehouse.id,code=row.warehouse.warehouse_code,name=row.warehouse.warehouse_name),"location":NamedRef(id=row.location.id,code=row.location.location_code,name=row.location.location_name) if row.location else None,"created_by":UserRef(id=row.creator.id,display_name=row.creator.display_name),"inventory_created":row.inventory_lot is not None,"inventory_lot_id":row.inventory_lot.id if row.inventory_lot else None})
def create_inbound(db:Session,payload:InboundCreate,user_id:int,import_job_id:int|None=None,commit:bool=True)->InboundRecord:
    _validate_refs(db,payload);record=InboundRecord(**payload.model_dump(mode="python"),inbound_no=generate_inbound_no(db),created_by=user_id,import_job_id=import_job_id);db.add(record);db.flush();db.add(AuditLog(user_id=user_id,action="CREATE",entity_type="INBOUND",entity_id=record.id,after_data=jsonable_encoder(payload)))
    if commit:db.commit();db.refresh(record)
    return record
def get_inbound(db:Session,record_id:int,user:User|None=None)->InboundRecord:
    filters=[InboundRecord.id==record_id]
    if user:
        filters.extend(x for x in (warehouse_clause(user,InboundRecord.warehouse_id),customer_clause(user,InboundRecord.customer_id)) if x is not None)
    row=db.scalar(select(InboundRecord).options(joinedload(InboundRecord.customer),joinedload(InboundRecord.warehouse),joinedload(InboundRecord.location),joinedload(InboundRecord.creator),joinedload(InboundRecord.inventory_lot)).where(*filters))
    if row is None:raise HTTPException(404,"Inbound record not found")
    return row
def list_inbounds(db:Session,p:InboundListParams,user:User|None=None)->InboundListResponse:
    filters=[]
    if user:filters.extend(x for x in (warehouse_clause(user,InboundRecord.warehouse_id),customer_clause(user,InboundRecord.customer_id)) if x is not None)
    if p.q:
        term=f"%{p.q}%";filters.append(or_(InboundRecord.inbound_no.ilike(term),InboundRecord.container_number.ilike(term),InboundRecord.fc_code.ilike(term),InboundRecord.marking.ilike(term),InboundRecord.remark.ilike(term)))
    for value,column in [(p.container_number,InboundRecord.container_number),(p.customer_id,InboundRecord.customer_id),(p.warehouse_id,InboundRecord.warehouse_id),(p.fc_code,InboundRecord.fc_code),(p.location_id,InboundRecord.location_id),(p.status,InboundRecord.status)]:
        if value is not None:filters.append(column.ilike(f"%{value}%") if isinstance(value,str) else column==value)
    for value,column,op in [(p.unload_date_from,InboundRecord.unload_date,"ge"),(p.unload_date_to,InboundRecord.unload_date,"le"),(p.received_date_from,InboundRecord.received_date,"ge"),(p.received_date_to,InboundRecord.received_date,"le")]:
        if value:filters.append(column>=value if op=="ge" else column<=value)
    total=db.scalar(select(func.count()).select_from(InboundRecord).where(*filters)) or 0;sort=SORTABLE.get(p.sort_by,InboundRecord.id);order=sort.asc() if p.sort_order=="asc" else sort.desc();rows=db.scalars(select(InboundRecord).options(joinedload(InboundRecord.customer),joinedload(InboundRecord.warehouse),joinedload(InboundRecord.location),joinedload(InboundRecord.creator),joinedload(InboundRecord.inventory_lot)).where(*filters).order_by(order).offset((p.page-1)*p.per_page).limit(p.per_page)).all()
    return InboundListResponse(data=[_read(r) for r in rows],meta=PaginationMeta(page=p.page,per_page=p.per_page,total=total,total_pages=ceil(total/p.per_page) if total else 0))
def update_inbound(db:Session,row:InboundRecord,payload:InboundUpdate,user_id:int)->InboundRecord:
    require_live_record(db,row)
    # Serialize generic edits against container receiving and invalidate open drafts.
    db.execute(select(InboundRecord.id).where(InboundRecord.id == row.id).with_for_update())
    db.refresh(row)
    receipt = dict((row.source_metadata or {}).get("ocean_receipt") or {})
    if receipt.get("confirmed_by"):
        protected = ("container_number", "warehouse_id", "customer_id", "unload_date", "carton_qty", "pallet_qty", "location_id", "received_date")
        if any(getattr(row, key) != getattr(payload, key) for key in protected) or payload.status not in (2, 3, 4, 5):
            raise HTTPException(409, "Confirmed ocean receipt quantities and identity are locked")
    receipt["version"] = receipt.get("version", 0) + 1
    if not receipt.get("confirmed_by"):
        receipt.update(expected_qty=str(payload.carton_qty), expected_pallets=str(payload.pallet_qty))
    row.source_metadata = {**(row.source_metadata or {}), "ocean_receipt": receipt}
    _validate_refs(db,payload);before=jsonable_encoder({k:getattr(row,k) for k in type(payload).model_fields});
    for k,v in payload.model_dump(mode="python").items():setattr(row,k,v)
    db.add(AuditLog(user_id=user_id,action="UPDATE",entity_type="INBOUND",entity_id=row.id,before_data=before,after_data=jsonable_encoder(payload)));db.commit();return get_inbound(db,row.id)
def delete_inbound(db:Session,row:InboundRecord,user_id:int)->None:
    require_live_record(db,row)
    db.add(AuditLog(user_id=user_id,action="DELETE",entity_type="INBOUND",entity_id=row.id,before_data=jsonable_encoder({"inbound_no":row.inbound_no,"container_number":row.container_number})));db.delete(row);db.commit()
