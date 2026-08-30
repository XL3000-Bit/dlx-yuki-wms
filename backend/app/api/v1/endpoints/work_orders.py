from datetime import date, datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload
from app.api.deps import CurrentUser, DbSession, require_warehouse_write
from app.models import WorkOrder, WorkOrderPriority, WorkOrderStatus, WorkOrderType, User
from app.models.work_order_event import WorkOrderEvent
from app.schemas.work_order import WorkOrderCreate, WorkOrderRead, WorkOrderStatusUpdate, WorkOrderUpdate
from app.services.access import apply_warehouse_scope, ensure_warehouse_writable, get_access_scope
from app.services.work_order import create_work_order, get_work_order, read_event, read_work_order, transition_work_order, update_work_order

router = APIRouter(prefix="/work-orders", tags=["Work Orders"])


def _visible_work_order(db, work_order_id, user):
    row = get_work_order(db, work_order_id)
    ensure_warehouse_writable(get_access_scope(db, user), row.warehouse_id, detail="Work order not found")
    return row


@router.get("", response_model=dict)
def list_work_orders(db: DbSession, user: CurrentUser, page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100), q: str | None = None, status: WorkOrderStatus | None = None, work_order_type: WorkOrderType | None = None, warehouse_id: int | None = None, priority: WorkOrderPriority | None = None, assigned_to: int | None = None):
    scope = get_access_scope(db, user)
    filters = []
    if q: filters.append(WorkOrder.work_order_no.ilike(f"%{q.strip()}%"))
    if status: filters.append(WorkOrder.status == status)
    if work_order_type: filters.append(WorkOrder.work_order_type == work_order_type)
    if warehouse_id:
        ensure_warehouse_writable(scope, warehouse_id, detail="Work order not found")
        filters.append(WorkOrder.warehouse_id == warehouse_id)
    if priority: filters.append(WorkOrder.priority == priority)
    if assigned_to: filters.append(WorkOrder.assigned_to == assigned_to)
    stmt = apply_warehouse_scope(select(WorkOrder), WorkOrder.warehouse_id, scope).where(*filters)
    rows = list(db.scalars(stmt.order_by(WorkOrder.id.desc())).all()); total = len(rows); rows = rows[(page-1)*per_page:page*per_page]
    return {"data": [read_work_order(x) for x in rows], "meta": {"page": page, "per_page": per_page, "total": total, "total_pages": (total + per_page - 1) // per_page}}


@router.post("", response_model=WorkOrderRead, status_code=201)
def create(payload: WorkOrderCreate, db: DbSession, user: User = Depends(require_warehouse_write)):
    ensure_warehouse_writable(get_access_scope(db, user), payload.warehouse_id)
    return read_work_order(create_work_order(db, payload, user.id))


@router.get("/{work_order_id}", response_model=WorkOrderRead)
def detail(work_order_id: int, db: DbSession, user: CurrentUser):
    return read_work_order(_visible_work_order(db, work_order_id, user))


@router.patch("/{work_order_id}", response_model=WorkOrderRead)
def update(work_order_id: int, payload: WorkOrderUpdate, db: DbSession, user: User = Depends(require_warehouse_write)):
    return read_work_order(update_work_order(db, _visible_work_order(db, work_order_id, user), payload))


@router.post("/{work_order_id}/status", response_model=WorkOrderRead)
def status(work_order_id: int, payload: WorkOrderStatusUpdate, db: DbSession, user: User = Depends(require_warehouse_write)):
    return read_work_order(transition_work_order(db, _visible_work_order(db, work_order_id, user), payload.status))


@router.get("/{work_order_id}/events")
def events(work_order_id: int, db: DbSession, user: CurrentUser, order: str = Query("desc", pattern="^(asc|desc)$"), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    _visible_work_order(db, work_order_id, user)
    total = db.scalar(select(func.count()).select_from(WorkOrderEvent).where(WorkOrderEvent.work_order_id == work_order_id)) or 0
    ordering = (WorkOrderEvent.created_at.asc(), WorkOrderEvent.id.asc()) if order == "asc" else (WorkOrderEvent.created_at.desc(), WorkOrderEvent.id.desc())
    rows = db.scalars(select(WorkOrderEvent).options(joinedload(WorkOrderEvent.actor)).where(WorkOrderEvent.work_order_id == work_order_id).order_by(*ordering).offset(offset).limit(limit)).all()
    return {"data": [read_event(row) for row in rows], "total": total, "limit": limit, "offset": offset}
