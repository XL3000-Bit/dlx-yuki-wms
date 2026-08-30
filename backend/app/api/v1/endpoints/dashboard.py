from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DbSession
from app.services.access_policy import assert_warehouse_access
from app.services.operations_dashboard import build_operations_dashboard
from app.utils.business_time import business_day_range, get_business_now, get_business_today

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/operations")
def operations_dashboard(db: DbSession, user: CurrentUser, date_from: date | None = Query(None), date_to: date | None = Query(None), warehouse_id: int | None = Query(None)):
    today = get_business_today()
    first, last = date_from or today, date_to or date_from or today
    if last < first:
        raise HTTPException(422, "date_to must be on or after date_from")
    if (last - first).days > 366:
        raise HTTPException(422, "Dashboard range cannot exceed 367 days")
    assert_warehouse_access(user, warehouse_id)
    start, _ = business_day_range(first)
    _, end = business_day_range(last)
    return build_operations_dashboard(db, user, start, end, get_business_now(), warehouse_id)
