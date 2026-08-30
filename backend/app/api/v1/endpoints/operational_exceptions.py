from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession, require_warehouse_write
from app.models import ExceptionSeverity, ExceptionStatus, ExceptionType, OperationalException, OperationalExceptionEvent, User
from app.schemas.operational_exception import (ExceptionAssign, ExceptionCreate, ExceptionEventRead, ExceptionRead, ExceptionResolve,
    ExceptionStatusUpdate, ExceptionUpdate, ExceptionWorkOrderCreate)
from app.schemas.work_order import WorkOrderCreate
from app.services.operational_exception import (assign_exception, create_exception, get_exception, read_event, read_exception,
    transition_exception, update_exception, _event)
from app.services.work_order import create_work_order
from app.services.access_policy import assert_warehouse_access, warehouse_clause

router = APIRouter(prefix="/operational-exceptions", tags=["Operational Exceptions"])


@router.get("")
def list_exceptions(db: DbSession, user: CurrentUser, page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100), q: str | None = None,
    status: ExceptionStatus | None = None, severity: ExceptionSeverity | None = None, exception_type: ExceptionType | None = None,
    warehouse_id: int | None = None, assigned_to: int | None = None, reported_from: datetime | None = None, reported_to: datetime | None = None):
    filters = []
    scope=warehouse_clause(user,OperationalException.warehouse_id)
    if scope is not None: filters.append(scope)
    if q: filters.append(or_(OperationalException.exception_no.ilike(f"%{q.strip()}%"), OperationalException.title.ilike(f"%{q.strip()}%"), OperationalException.description.ilike(f"%{q.strip()}%")))
    if severity: filters.append(OperationalException.severity == severity)
    if exception_type: filters.append(OperationalException.exception_type == exception_type)
    if warehouse_id: filters.append(OperationalException.warehouse_id == warehouse_id)
    if assigned_to: filters.append(OperationalException.assigned_to == assigned_to)
    if reported_from: filters.append(OperationalException.reported_at >= reported_from)
    if reported_to: filters.append(OperationalException.reported_at <= reported_to)
    scoped_filters = list(filters)
    if status: filters.append(OperationalException.status == status)
    total = db.scalar(select(func.count()).select_from(OperationalException).where(*filters)) or 0
    rows = db.scalars(select(OperationalException).where(*filters).order_by(OperationalException.reported_at.desc(), OperationalException.id.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    counts = dict(db.execute(select(OperationalException.status, func.count()).where(*scoped_filters).group_by(OperationalException.status)).all())
    return {"data": [read_exception(get_exception(db, row.id)) for row in rows], "meta": {"page": page, "per_page": per_page, "total": total, "total_pages": (total + per_page - 1) // per_page},
        "counts": {key.value: counts.get(key, 0) for key in ExceptionStatus}}


@router.post("", response_model=ExceptionRead, status_code=201)
def create(payload: ExceptionCreate, db: DbSession, user: User = Depends(require_warehouse_write)):
    assert_warehouse_access(user,payload.warehouse_id); return read_exception(create_exception(db, payload, user.id))


def _scoped_exception(db,user,exception_id):
    stmt=select(OperationalException.id).where(OperationalException.id==exception_id); scope=warehouse_clause(user,OperationalException.warehouse_id)
    found=db.scalar(stmt.where(scope) if scope is not None else stmt)
    if found is None: raise HTTPException(404,"Operational exception not found")
    return get_exception(db,found)


@router.get("/{exception_id}", response_model=ExceptionRead)
def detail(exception_id: int, db: DbSession, user: CurrentUser): return read_exception(_scoped_exception(db,user,exception_id))


@router.patch("/{exception_id}", response_model=ExceptionRead)
def update(exception_id: int, payload: ExceptionUpdate, db: DbSession, user: User = Depends(require_warehouse_write)): return read_exception(update_exception(db, _scoped_exception(db,user,exception_id), payload, user.id))


@router.post("/{exception_id}/assign", response_model=ExceptionRead)
def assign(exception_id: int, payload: ExceptionAssign, db: DbSession, user: User = Depends(require_warehouse_write)): return read_exception(assign_exception(db, _scoped_exception(db,user,exception_id), payload, user.id))


@router.post("/{exception_id}/status", response_model=ExceptionRead)
def status(exception_id: int, payload: ExceptionStatusUpdate, db: DbSession, user: User = Depends(require_warehouse_write)): return read_exception(transition_exception(db, _scoped_exception(db,user,exception_id), payload.status, user.id))


@router.post("/{exception_id}/resolve", response_model=ExceptionRead)
def resolve(exception_id: int, payload: ExceptionResolve, db: DbSession, user: User = Depends(require_warehouse_write)): return read_exception(transition_exception(db, _scoped_exception(db,user,exception_id), ExceptionStatus.RESOLVED, user.id, payload.resolution))


@router.get("/{exception_id}/events")
def events(exception_id: int, db: DbSession, user: CurrentUser, order: str = Query("desc", pattern="^(asc|desc)$"), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    _scoped_exception(db,user,exception_id); total = db.scalar(select(func.count()).select_from(OperationalExceptionEvent).where(OperationalExceptionEvent.operational_exception_id == exception_id)) or 0
    ordering = (OperationalExceptionEvent.created_at.asc(), OperationalExceptionEvent.id.asc()) if order == "asc" else (OperationalExceptionEvent.created_at.desc(), OperationalExceptionEvent.id.desc())
    rows = db.scalars(select(OperationalExceptionEvent).options(joinedload(OperationalExceptionEvent.actor)).where(OperationalExceptionEvent.operational_exception_id == exception_id).order_by(*ordering).offset(offset).limit(limit)).all()
    return {"data": [read_event(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/{exception_id}/work-orders")
def create_linked_work_order(exception_id: int, payload: ExceptionWorkOrderCreate, db: DbSession, user: User = Depends(require_warehouse_write)):
    row = _scoped_exception(db,user,exception_id)
    if row.status in (ExceptionStatus.RESOLVED, ExceptionStatus.CANCELED):
        from fastapi import HTTPException
        raise HTTPException(409, "Terminal exception is immutable")
    wo = create_work_order(db, WorkOrderCreate(work_order_type="CHECK", warehouse_id=row.warehouse_id, load_id=row.load_id,
        outbound_id=row.outbound_id, picking_list_id=row.picking_list_id, container_tracking_id=row.container_tracking_id,
        priority="HIGH", assigned_to=payload.assigned_to, assigned_team=payload.assigned_team, notes=payload.notes), user.id)
    wo.operational_exception_id = row.id; _event(db, row, "WORK_ORDER_LINKED", user.id, new=wo.work_order_no); db.commit()
    return {"id": wo.id, "work_order_no": wo.work_order_no}
