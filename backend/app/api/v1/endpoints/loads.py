from datetime import date, datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from app.api.deps import CurrentUser, DbSession, require_outbound_write
from app.models import Load, LoadStatus, OutboundOrder, User
from app.schemas.load import LoadCreate, LoadRead, LoadStatusUpdate, LoadUpdate
from app.schemas.load_dispatch import DispatchReadiness
from app.services.load_dispatch_gate import integrated_readiness as dispatch_readiness, dispatch_load
from app.services import load_dispatch_write as dispatch_writer
from app.schemas.load_dispatch_write import BusinessClassification, AllocationWrite, PlanWrite, PlanFinalize
from app.models.load_dispatch import LoadAllocation, LoadDispatchPlan
from app.services.load import add_outbounds, create_load, get_load, read_load, remove_outbound, transition_load, update_load, load_query
from app.services.access_policy import customer_clause, warehouse_clause, assert_warehouse_access
from app.schemas.staging import StageRequest, VerificationCompleteRequest, VerificationScanRequest, VerificationStartRequest
from app.services.staging import execution_summary, stage as stage_load, verification_complete, verification_scan, verification_start

router = APIRouter(prefix="/loads", tags=["Loads"])


@router.get("/{load_id}/dispatch-readiness", response_model=DispatchReadiness)
def get_dispatch_readiness(load_id: int, db: DbSession, user: CurrentUser):
    return dispatch_readiness(db, user, load_id)


Writer = require_outbound_write

@router.get("", response_model=dict)
def list_loads(db: DbSession, user: CurrentUser, page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100), q: str | None = None, status: LoadStatus | None = None, warehouse_id: int | None = None, appointment_from: date | None = None, appointment_to: date | None = None, business_type: Literal['FBA', 'PRIVATE'] | None = None):
    stmt = load_query(); filters = []
    scope=warehouse_clause(user,Load.warehouse_id)
    if scope is not None: filters.append(scope)
    if q: filters.append(Load.load_no.ilike(f"%{q.strip()}%"))
    if status: filters.append(Load.status == status)
    if business_type: filters.append(Load.dispatch_business_type == business_type)
    if warehouse_id: filters.append(Load.warehouse_id == warehouse_id)
    if appointment_from: filters.append(Load.appointment_time >= datetime.combine(appointment_from, datetime.min.time()))
    if appointment_to: filters.append(Load.appointment_time < datetime.combine(appointment_to, datetime.max.time()))
    candidates = list(db.scalars(stmt.where(*filters).order_by(Load.id.desc())).unique())
    rows = []
    for row in candidates:
        try: dispatch_writer.scoped_load(db, user, row.id)
        except HTTPException as exc:
            if exc.status_code == 404: continue
            raise
        rows.append(row)
    total = len(rows)
    rows = rows[(page - 1) * per_page:page * per_page]
    return {"data": [read_load(row) for row in rows], "meta": {"page": page, "per_page": per_page, "total": total, "total_pages": (total + per_page - 1) // per_page}}

@router.post("", response_model=LoadRead, status_code=201)
def create(payload: LoadCreate, db: DbSession, user: User = Depends(require_outbound_write)):
    assert_warehouse_access(user,payload.warehouse_id)
    return read_load(create_load(db, payload, user.id, user=user))

def _scoped_load(db,user,load_id):
    dispatch_writer.scoped_load(db, user, load_id)
    return get_load(db, load_id)

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
    return read_load(add_outbounds(db, _scoped_load(db,user,load_id), outbound_ids, user=user))

@router.delete("/{load_id}/outbounds/{outbound_id}", response_model=LoadRead)
def detach(load_id: int, outbound_id: int, db: DbSession, user: User = Depends(require_outbound_write)):
    return read_load(remove_outbound(db, _scoped_load(db,user,load_id), outbound_id))

@router.post("/{load_id}/status", response_model=LoadRead)
def status(load_id: int, payload: LoadStatusUpdate, db: DbSession, user: User = Depends(require_outbound_write)):
    if payload.status == LoadStatus.DISPATCHED:
        return read_load(dispatch_load(db, user, load_id, payload))
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


@router.patch("/orders/{order_id}/business")
def classify(order_id: int, payload: BusinessClassification, db: DbSession, user: User = Depends(require_outbound_write)):
    return dispatch_writer.classify_order(db, user, order_id, payload.business_type)


@router.get("/{load_id}/allocations")
def allocations(load_id: int, db: DbSession, user: CurrentUser):
    dispatch_writer.scoped_load(db, user, load_id)
    return [dispatch_writer.allocation_read(a) for a in db.scalars(select(LoadAllocation).where(LoadAllocation.load_id == load_id).order_by(LoadAllocation.id))]


@router.post("/{load_id}/allocations", status_code=201)
def allocate(load_id: int, payload: AllocationWrite, db: DbSession, user: User = Depends(require_outbound_write)):
    return dispatch_writer.write_allocation(db, user, load_id, payload)


@router.get("/{load_id}/plans")
def plans(load_id: int, db: DbSession, user: CurrentUser):
    dispatch_writer.scoped_load(db, user, load_id)
    return [dispatch_writer.plan_read(db, p) for p in db.scalars(select(LoadDispatchPlan).where(LoadDispatchPlan.load_id == load_id).order_by(LoadDispatchPlan.version.desc()))]


@router.post("/{load_id}/plans", status_code=201)
def create_plan(load_id: int, db: DbSession, user: User = Depends(require_outbound_write)):
    return dispatch_writer.create_plan(db, user, load_id)


@router.put("/{load_id}/plans/{plan_id}/lines")
def plan_lines(load_id: int, plan_id: int, payload: PlanWrite, db: DbSession, user: User = Depends(require_outbound_write)):
    return dispatch_writer.replace_lines(db, user, load_id, plan_id, payload)


@router.post("/{load_id}/plans/{plan_id}/finalize")
def finalize(load_id: int, plan_id: int, payload: PlanFinalize, db: DbSession, user: User = Depends(require_outbound_write)):
    return dispatch_writer.finalize_plan(db, user, load_id, plan_id, payload)


from pydantic import BaseModel, ConfigDict, Field
from app.schemas.dispatch_evidence import EvidenceReviewWrite
from app.services import dispatch_evidence

class EvidenceBolWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outbound_id: int = Field(gt=0)

class ExceptionResolutionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolution: str = Field(min_length=1, max_length=4000)

@router.get("/{load_id}/evidence")
def get_evidence(load_id: int, db: DbSession, user: CurrentUser):
    return dispatch_evidence.evidence_view(db, user, load_id)

@router.post("/{load_id}/evidence/reviews")
def review_evidence(load_id: int, payload: EvidenceReviewWrite, db: DbSession, user: CurrentUser):
    return dispatch_evidence.write_review(db, user, load_id, payload)

@router.post("/{load_id}/evidence/documents/bol")
def generate_evidence_bol(load_id: int, payload: EvidenceBolWrite, db: DbSession, user: User = Depends(require_outbound_write)):
    from app.services.picking_bol import generate_bol
    from app.services.operational_document import register_generated_bol
    try:
        dispatch_evidence.evidence_lock(db)
        load = dispatch_writer.scoped_load(db, user, load_id, True)
        if load.status not in (LoadStatus.PLANNED, LoadStatus.READY): raise HTTPException(409, "LOAD_NOT_MUTABLE")
        order = db.get(OutboundOrder, payload.outbound_id)
        if not order or order.load_id != load.id: raise HTTPException(409, "DOCUMENT_LOAD_MEMBERSHIP_MISMATCH")
        bol = generate_bol(db, order.id, user.id, commit=False)
        document = register_generated_bol(db, bol, user.id)
        db.flush(); result = dispatch_evidence.row_data(document); db.commit(); return result
    except Exception:
        db.rollback(); raise

@router.post("/{load_id}/evidence/exceptions/{exception_id}/resolve")
def resolve_evidence_exception(load_id: int, exception_id: int, payload: ExceptionResolutionWrite, db: DbSession, user: CurrentUser):
    from app.models.user import UserRole
    from app.models.operational_exception import ExceptionStatus
    from app.services.operational_exception import transition_exception
    if user.role not in (UserRole.ADMIN, UserRole.MANAGER, UserRole.INBOUND, UserRole.WAREHOUSE): raise HTTPException(403, "WAREHOUSE_WRITE_PERMISSION_REQUIRED")
    try:
        dispatch_evidence.evidence_lock(db)
        load = dispatch_writer.scoped_load(db, user, load_id, True)
        if load.status not in (LoadStatus.PLANNED, LoadStatus.READY): raise HTTPException(409, "LOAD_NOT_MUTABLE")
        row = next((e for e in dispatch_evidence.related_exceptions(db, load) if e.id == exception_id), None)
        if not row: raise HTTPException(404, "Exception not found")
        row = transition_exception(db, row, ExceptionStatus.RESOLVED, user.id, resolution=payload.resolution.strip(), commit=False)
        db.flush(); result = dispatch_evidence.row_data(row); db.commit(); return result
    except Exception:
        db.rollback(); raise
