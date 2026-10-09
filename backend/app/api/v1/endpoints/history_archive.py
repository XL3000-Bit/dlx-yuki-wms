"""Read-only archive access using the same warehouse/customer policy as live data."""
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import String, cast, func, select
from app.api.deps import CurrentUser, DbSession
from app.models import Customer, ImportJob, ImportRow, Warehouse
from app.models.user import ScopeMode, UserRole
from app.services.access_policy import assert_customer_access, assert_warehouse_access, customer_clause, warehouse_ids

PROFILE = "WEST_COAST_4_0_HISTORY"
router = APIRouter(prefix="/history-archive", tags=["History archive"])


def archive_job(db, job_id):
    job = db.get(ImportJob, job_id)
    if job is None or job.profile_code != PROFILE:
        raise HTTPException(404, "Historical archive not found")
    return job


def job_warehouse_id(db, job):
    options = job.options or {}
    if options.get("warehouse_id") is not None:
        try:
            return int(options["warehouse_id"])
        except (TypeError, ValueError):
            return None
    ids = db.scalars(select(Warehouse.id).where(Warehouse.warehouse_name == options.get("warehouse_name"))).all()
    return ids[0] if len(ids) == 1 else None


def warehouse_visible(db, user, job, warehouse_id=None):
    resolved = job_warehouse_id(db, job)
    if warehouse_id is not None and resolved != warehouse_id:
        return False
    return user.role == UserRole.ADMIN or user.warehouse_scope_mode == ScopeMode.ALL or resolved in warehouse_ids(user)


def row_filters(user, job_id, customer_id=None):
    # Historical rows store the original customer name. Ambiguous/unmapped names
    # must never inherit access from one arbitrarily chosen customer.
    resolved_customer = (select(func.min(Customer.id))
        .where(Customer.customer_name == ImportRow.raw_data["客户"].as_string())
        .having(func.count(Customer.id) == 1).correlate(ImportRow).scalar_subquery())
    filters = [ImportRow.import_job_id == job_id]
    clause = customer_clause(user, resolved_customer)
    if clause is not None:
        filters.append(clause)
    if customer_id is not None:
        filters.append(resolved_customer == customer_id)
    return filters


def visible_count(db, user, job_id, customer_id=None):
    return db.scalar(select(func.count()).select_from(ImportRow).where(*row_filters(user, job_id, customer_id)))


@router.get("")
def sheets(db: DbSession, user: CurrentUser, warehouse_id: int | None = None, customer_id: int | None = None):
    assert_warehouse_access(user, warehouse_id)
    assert_customer_access(user, customer_id)
    jobs = db.scalars(select(ImportJob).where(ImportJob.profile_code == PROFILE).order_by(ImportJob.id)).all()
    result = []
    for job in jobs:
        if not warehouse_visible(db, user, job, warehouse_id):
            continue
        count = visible_count(db, user, job.id, customer_id)
        restricted = user.role != UserRole.ADMIN and user.customer_scope_mode == ScopeMode.SELECTED
        if not count and (restricted or customer_id is not None):
            continue
        result.append({"id": job.id, "sheet": job.source_sheet, "file_name": job.original_file_name,
                       "total_rows": count, "columns": job.detected_columns,
                       "warehouse": (job.options or {}).get("warehouse_name"), "file_hash": job.file_hash})
    return result


@router.get("/{job_id}/records")
def records(job_id: int, db: DbSession, user: CurrentUser,
            q: str = Query("", max_length=200), page: int = Query(1, ge=1),
            page_size: int = Query(50, ge=1, le=200),
            warehouse_id: int | None = None, customer_id: int | None = None):
    assert_warehouse_access(user, warehouse_id)
    assert_customer_access(user, customer_id)
    job = archive_job(db, job_id)
    if not warehouse_visible(db, user, job, warehouse_id):
        raise HTTPException(403, "Warehouse is outside your assigned scope")
    filters = row_filters(user, job_id, customer_id)
    if q.strip():
        filters.append(cast(ImportRow.raw_data, String).icontains(q.strip(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(ImportRow).where(*filters))
    rows = db.scalars(select(ImportRow).where(*filters).order_by(ImportRow.row_number)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "rows": [{"id": r.id, "row_number": r.row_number, "data": r.raw_data,
            "conversion": r.mapped_data, "entity_type": r.created_entity_type, "entity_id": r.created_entity_id} for r in rows]}


@router.get("/{job_id}/source")
def source(job_id: int, db: DbSession, user: CurrentUser):
    job = archive_job(db, job_id)
    if not warehouse_visible(db, user, job):
        raise HTTPException(403, "Warehouse is outside your assigned scope")
    # A source workbook can contain sheets/customers outside this archive job.
    if user.role != UserRole.ADMIN and (user.warehouse_scope_mode != ScopeMode.ALL or user.customer_scope_mode != ScopeMode.ALL):
        raise HTTPException(403, "Source workbook requires unrestricted warehouse and customer access")
    path = Path(job.stored_file_path or "")
    if not path.is_file():
        raise HTTPException(404, "Source workbook is unavailable")
    return FileResponse(path, filename=job.original_file_name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
