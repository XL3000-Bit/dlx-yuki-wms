from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from app.api.deps import CurrentUser, DbSession, require_outbound_write
from app.models import Load, LoadStatus, OutboundOrder, User
from app.schemas.load import LoadCreate, LoadRead, LoadStatusUpdate, LoadUpdate
from app.services.load import add_outbounds, create_load, get_load, read_load, remove_outbound, transition_load, update_load, load_query
from app.services.access_policy import customer_clause, warehouse_clause, assert_warehouse_access
from app.schemas.staging import StageRequest, VerificationCompleteRequest, VerificationScanRequest, VerificationStartRequest
from app.services.staging import execution_summary, stage as stage_load, verification_complete, verification_scan, verification_start

router = APIRouter(prefix="/loads", tags=["Loads"])
Writer = require_outbound_write

@router.get("", response_model=dict)
def list_loads(db: DbSession, user: CurrentUser, page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100), q: str | None = None, status: LoadStatus | None = None, warehouse_id: int | None = None, appointment_from: date | None = None, appointment_to: date | None = None):
    stmt = load_query(); filters = []
    scope=warehouse_clause(user,Load.warehouse_id)
    if scope is not None: filters.append(scope)
    if q: filters.append(Load.load_no.ilike(f"%{q.strip()}%"))
    if status: filters.append(Load.status == status)
    if warehouse_id: filters.append(Load.warehouse_id == warehouse_id)
    if appointment_from: filters.append(Load.appointment_time >= datetime.combine(appointment_from, datetime.min.time()))
    if appointment_to: filters.append(Load.appointment_time < datetime.combine(appointment_to, datetime.max.time()))
    rows = list(db.scalars(stmt.where(*filters).order_by(Load.id.desc())).unique()); total = len(rows)
    rows = rows[(page - 1) * per_page:page * per_page]
    return {"data": [read_load(row) for row in rows], "meta": {"page": page, "per_page": per_page, "total": total, "total_pages": (total + per_page - 1) // per_page}}

@router.post("", response_model=LoadRead, status_code=201)
def create(payload: LoadCreate, db: DbSession, user: User = Depends(require_outbound_write)):
    assert_warehouse_access(user,payload.warehouse_id)
    return read_load(create_load(db, payload, user.id))

def _scoped_load(db,user,load_id):
    stmt=load_query().where(Load.id==load_id); scope=warehouse_clause(user,Load.warehouse_id)
    row=db.scalar(stmt.where(scope) if scope is not None else stmt)
    if row is None: raise HTTPException(404,"Load not found")
    return row

@router.get("/{load_id}", response_model=LoadRead)
def detail(load_id: int, db: DbSession, user: CurrentUser): return read_load(_scoped_load(db,user,load_id))

@router.patch("/{load_id}", response_model=LoadRead)
def update(load_id: int, payload: LoadUpdate, db: DbSession, user: User = Depends(require_outbound_write)):
    return read_load(update_load(db, _scoped_load(db,user,load_id), payload))

@router.post("/{load_id}/outbounds", response_model=LoadRead)
def attach(load_id: int, outbound_ids: list[int], db: DbSession, user: User = Depends(require_outbound_write)):
    stmt=select(OutboundOrder.id).where(OutboundOrder.id.in_(outbound_ids))
    for scope in (warehouse_clause(user,OutboundOrder.warehouse_id),customer_clause(user,OutboundOrder.customer_id)):
        if scope is not None:stmt=stmt.where(scope)
    if len(set(db.scalars(stmt).all())) != len(set(outbound_ids)): raise HTTPException(404,"Outbound order not found")
    return read_load(add_outbounds(db, _scoped_load(db,user,load_id), outbound_ids))

@router.delete("/{load_id}/outbounds/{outbound_id}", response_model=LoadRead)
def detach(load_id: int, outbound_id: int, db: DbSession, user: User = Depends(require_outbound_write)):
    return read_load(remove_outbound(db, _scoped_load(db,user,load_id), outbound_id))

@router.post("/{load_id}/status", response_model=LoadRead)
def status(load_id: int, payload: LoadStatusUpdate, db: DbSession, user: User = Depends(require_outbound_write)):
    return read_load(transition_load(db, _scoped_load(db,user,load_id), payload.status))

@router.post("/{load_id}/stage")
def stage(load_id: int, payload: StageRequest, db: DbSession, user: User = Depends(require_outbound_write)):
    return stage_load(db, _scoped_load(db,user,load_id), payload, user.id)

@router.post("/{load_id}/verify/start")
def verify_start(load_id: int, payload: VerificationStartRequest, db: DbSession, user: User = Depends(require_outbound_write)):
    return verification_start(db, _scoped_load(db,user,load_id), payload, user.id)

@router.post("/{load_id}/verify/scan")
def verify_scan(load_id: int, payload: VerificationScanRequest, db: DbSession, user: User = Depends(require_outbound_write)):
    return verification_scan(db, _scoped_load(db,user,load_id), payload, user.id)

@router.post("/{load_id}/verify/complete")
def verify_complete(load_id: int, payload: VerificationCompleteRequest, db: DbSession, user: User = Depends(require_outbound_write)):
    return verification_complete(db, _scoped_load(db,user,load_id), payload, user.id)

@router.get("/{load_id}/execution-summary")
def get_execution_summary(load_id: int, db: DbSession, user: CurrentUser):
    return execution_summary(db, _scoped_load(db,user,load_id))
