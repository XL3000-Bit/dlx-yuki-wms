from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.threepl import ThreePLDispatchQueue, ThreePLOverview
from app.services.access_policy import assert_customer_access, assert_warehouse_access
from app.services.threepl import build_threepl_dispatch_queue, build_threepl_overview
from app.utils.business_time import get_business_today

router = APIRouter(prefix="/3pl", tags=["3PL"])


@router.get("/dispatch-queue", response_model=ThreePLDispatchQueue)
def threepl_dispatch_queue(
    db: DbSession,
    user: CurrentUser,
    customer_id: int | None = Query(None),
    warehouse_id: int | None = Query(None),
):
    assert_customer_access(user, customer_id)
    assert_warehouse_access(user, warehouse_id)
    return build_threepl_dispatch_queue(db, user, customer_id, warehouse_id)


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
