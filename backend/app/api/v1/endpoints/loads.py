from datetime import date, datetime
from fastapi import APIRouter, Depends, Query
from app.api.deps import CurrentUser, DbSession, require_outbound_write
from app.models import Load, LoadStatus, User
from app.schemas.load import LoadCreate, LoadRead, LoadStatusUpdate, LoadUpdate
from app.services.access import apply_warehouse_scope, ensure_warehouse_writable, get_access_scope
from app.services.load import add_outbounds, create_load, get_load, read_load, remove_outbound, transition_load, update_load, load_query

router = APIRouter(prefix="/loads", tags=["Loads"])


def _visible_load(db, load_id, user):
    load = get_load(db, load_id)
    ensure_warehouse_writable(get_access_scope(db, user), load.warehouse_id, detail="Load not found")
    return load


@router.get("", response_model=dict)
def list_loads(db: DbSession, user: CurrentUser, page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100), q: str | None = None, status: LoadStatus | None = None, warehouse_id: int | None = None, appointment_from: date | None = None, appointment_to: date | None = None):
    scope = get_access_scope(db, user)
    stmt = apply_warehouse_scope(load_query(), Load.warehouse_id, scope)
    filters = []
    if q: filters.append(Load.load_no.ilike(f"%{q.strip()}%"))
    if status: filters.append(Load.status == status)
    if warehouse_id:
        ensure_warehouse_writable(scope, warehouse_id, detail="Load not found")
        filters.append(Load.warehouse_id == warehouse_id)
    if appointment_from: filters.append(Load.appointment_time >= datetime.combine(appointment_from, datetime.min.time()))
    if appointment_to: filters.append(Load.appointment_time < datetime.combine(appointment_to, datetime.max.time()))
    rows = list(db.scalars(stmt.where(*filters).order_by(Load.id.desc())).unique()); total = len(rows)
    rows = rows[(page - 1) * per_page:page * per_page]
    return {"data": [read_load(row) for row in rows], "meta": {"page": page, "per_page": per_page, "total": total, "total_pages": (total + per_page - 1) // per_page}}


@router.post("", response_model=LoadRead, status_code=201)
def create(payload: LoadCreate, db: DbSession, user: User = Depends(require_outbound_write)):
    ensure_warehouse_writable(get_access_scope(db, user), payload.warehouse_id)
    return read_load(create_load(db, payload, user.id))


@router.get("/{load_id}", response_model=LoadRead)
def detail(load_id: int, db: DbSession, user: CurrentUser):
    return read_load(_visible_load(db, load_id, user))


@router.patch("/{load_id}", response_model=LoadRead)
def update(load_id: int, payload: LoadUpdate, db: DbSession, user: User = Depends(require_outbound_write)):
    return read_load(update_load(db, _visible_load(db, load_id, user), payload))


@router.post("/{load_id}/outbounds", response_model=LoadRead)
def attach(load_id: int, outbound_ids: list[int], db: DbSession, user: User = Depends(require_outbound_write)):
    return read_load(add_outbounds(db, _visible_load(db, load_id, user), outbound_ids))


@router.delete("/{load_id}/outbounds/{outbound_id}", response_model=LoadRead)
def detach(load_id: int, outbound_id: int, db: DbSession, user: User = Depends(require_outbound_write)):
    return read_load(remove_outbound(db, _visible_load(db, load_id, user), outbound_id))


@router.post("/{load_id}/status", response_model=LoadRead)
def status(load_id: int, payload: LoadStatusUpdate, db: DbSession, user: User = Depends(require_outbound_write)):
    return read_load(transition_load(db, _visible_load(db, load_id, user), payload.status))
