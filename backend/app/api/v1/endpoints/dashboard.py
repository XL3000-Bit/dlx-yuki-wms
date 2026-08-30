from datetime import date
from fastapi import APIRouter, Query
from app.api.deps import CurrentUser, DbSession
from app.services.operations_dashboard import operations_dashboard

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/operations")
def operations(db: DbSession, user: CurrentUser, warehouse_id: int | None = None, preset: str | None = Query("today"), date_from: date | None = None, date_to: date | None = None):
    return operations_dashboard(db, user, warehouse_id=warehouse_id, preset=preset, date_from=date_from, date_to=date_to)
