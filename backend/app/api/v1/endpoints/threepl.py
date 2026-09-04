from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.threepl import ThreePLDispatchQueue, ThreePLOverview
from app.services.access_policy import (
    Permission,
    ROLE_PERMISSIONS,
    assert_customer_access,
    assert_warehouse_access,
)
from app.services.threepl import build_threepl_dispatch_queue, build_threepl_overview
from app.utils.business_time import get_business_today

router = APIRouter(prefix="/3pl", tags=["3PL"])


@router.get("/dispatch-queue", response_model=ThreePLDispatchQueue)
def threepl_dispatch_queue(
    db: DbSession,
    user: CurrentUser,
    customer_id: int | None = Query(None),
    warehouse_id: int | None = Query(None),
    status: int | None = Query(None),
    readiness: Literal["READY", "AT_RISK", "BLOCKED"] | None = Query(None),
    blocker: Literal[
        "ACTIVE_EXCEPTION", "OUTBOUND_EXCEPTION", "OUTBOUND_HOLD", "OVERDUE",
        "OWNER_UNASSIGNED", "CARRIER_MISSING", "DOCUMENTS_MISSING",
        "BOL_MISSING", "PICKING_MISSING",
    ] | None = Query(None),
    priority: Literal["URGENT", "HIGH", "NORMAL", "LOW"] | None = Query(None),
    search: str | None = Query(None, max_length=200),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: Literal["queue", "priority", "due_at", "updated_at", "reference"] = Query("queue"),
):
    if Permission.READ not in ROLE_PERMISSIONS.get(user.role, set()):
        raise HTTPException(403, "3PL dispatch queue read permission is required")
    if status is not None and status not in (0, 1, 2, 3, 4, 7):
        raise HTTPException(422, "status must be one of 0, 1, 2, 3, 4, or 7")
    if date_from and date_to and date_to < date_from:
        raise HTTPException(422, "date_to must be on or after date_from")
    assert_customer_access(user, customer_id)
    assert_warehouse_access(user, warehouse_id)
    return build_threepl_dispatch_queue(
        db, user, customer_id, warehouse_id, status=status, readiness=readiness,
        blocker=blocker, priority=priority, search=search, date_from=date_from,
        date_to=date_to, page=page, page_size=page_size, sort=sort,
    )


@router.get("/overview", response_model=ThreePLOverview)
def threepl_overview(
    db: DbSession,
    user: CurrentUser,
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    customer_id: int | None = Query(None),
    warehouse_id: int | None = Query(None),
):
    today = get_business_today()
    first = date_from or today.replace(day=1)
    last = date_to or today
    if last < first:
        raise HTTPException(422, "date_to must be on or after date_from")
    if (last - first).days > 366:
        raise HTTPException(422, "3PL reporting range cannot exceed 367 days")
    assert_customer_access(user, customer_id)
    assert_warehouse_access(user, warehouse_id)
    return build_threepl_overview(db, user, first, last, customer_id, warehouse_id)
