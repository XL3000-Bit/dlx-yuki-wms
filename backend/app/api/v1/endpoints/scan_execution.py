from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, require_outbound_write
from app.models import ScanEvent, ScanSessionStatus, User
from app.schemas.scan_execution import (
    PickConfirmationRequest,
    ScanEventListResponse,
    ScanResultResponse,
    ScanSessionCreate,
    ScanSessionResponse,
    ScanValueRequest,
)
from app.services.scan_execution import (
    confirm_pick,
    create_scan_session,
    get_scan_counters,
    get_scan_session,
    get_picking_execution_summary,
    recent_scan_events,
    reset_pick_step,
    scan_value,
    transition_scan_session,
)

router = APIRouter(prefix="/scan-sessions", tags=["Scan Execution"])


def _commit(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def _session_response(db: Session, session) -> ScanSessionResponse:
    return ScanSessionResponse(
        session=session,
        counters=get_scan_counters(db, session.id),
        picking_summary=get_picking_execution_summary(db, session),
    )


@router.post("", response_model=ScanSessionResponse, status_code=201)
def create(
    payload: ScanSessionCreate,
    db: DbSession,
    user: User = Depends(require_outbound_write),
):
    session = create_scan_session(db, payload, user)
    _commit(db)
    db.refresh(session)
    return _session_response(db, session)


@router.get("/{session_id}", response_model=ScanSessionResponse)
def detail(session_id: int, db: DbSession, user: CurrentUser):
    return _session_response(db, get_scan_session(db, session_id, user))


@router.get("/{session_id}/events", response_model=ScanEventListResponse)
def events(
    session_id: int,
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    session = get_scan_session(db, session_id, user)
    total = db.scalar(
        select(func.count())
        .select_from(ScanEvent)
        .where(ScanEvent.session_id == session.id)
    ) or 0
    rows = list(
        db.scalars(
            select(ScanEvent)
            .where(ScanEvent.session_id == session.id)
            .order_by(ScanEvent.scanned_at.desc(), ScanEvent.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return ScanEventListResponse(
        data=rows,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{session_id}/scan", response_model=ScanResultResponse)
def scan(
    session_id: int,
    payload: ScanValueRequest,
    db: DbSession,
    user: User = Depends(require_outbound_write),
):
    session = get_scan_session(db, session_id, user)
    event = scan_value(db, session, user, payload.value)
    _commit(db)
    db.refresh(session)
    db.refresh(event)
    return ScanResultResponse(
        event=event,
        session=session,
        counters=get_scan_counters(db, session.id),
        recent_events=recent_scan_events(db, session.id, limit=20),
        picking_summary=get_picking_execution_summary(db, session),
    )


@router.post("/{session_id}/confirm-pick", response_model=ScanResultResponse)
def confirm_pick_quantity(
    session_id: int,
    payload: PickConfirmationRequest,
    db: DbSession,
    user: User = Depends(require_outbound_write),
):
    get_scan_session(db, session_id, user)
    event = confirm_pick(db, session_id, payload, user)
    _commit(db)
    session = get_scan_session(db, session_id, user)
    db.refresh(event)
    return ScanResultResponse(
        event=event,
        session=session,
        counters=get_scan_counters(db, session.id),
        recent_events=recent_scan_events(db, session.id, limit=20),
        picking_summary=get_picking_execution_summary(db, session),
    )


@router.post("/{session_id}/reset-step", response_model=ScanSessionResponse)
def reset_step(
    session_id: int,
    db: DbSession,
    user: User = Depends(require_outbound_write),
):
    session = reset_pick_step(db, get_scan_session(db, session_id, user))
    _commit(db)
    db.refresh(session)
    return _session_response(db, session)


@router.post("/{session_id}/complete", response_model=ScanSessionResponse)
def complete(
    session_id: int,
    db: DbSession,
    user: User = Depends(require_outbound_write),
):
    session = transition_scan_session(
        db,
        get_scan_session(db, session_id, user),
        ScanSessionStatus.COMPLETED,
    )
    _commit(db)
    db.refresh(session)
    return _session_response(db, session)


@router.post("/{session_id}/cancel", response_model=ScanSessionResponse)
def cancel(
    session_id: int,
    db: DbSession,
    user: User = Depends(require_outbound_write),
):
    session = transition_scan_session(
        db,
        get_scan_session(db, session_id, user),
        ScanSessionStatus.CANCELED,
    )
    _commit(db)
    db.refresh(session)
    return _session_response(db, session)
