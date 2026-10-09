"""Prevent archived history from changing stock before reconciliation."""
from fastapi import HTTPException
from app.models import ImportJob


def require_live_record(db, record):
    job_id = getattr(record, 'import_job_id', None)
    job = db.get(ImportJob, job_id) if job_id else None
    mode = (getattr(record, 'source_metadata', None) or {}).get('migration_mode')
    if mode == 'HISTORICAL' or (job and (job.profile_code == 'WEST_COAST_4_0_HISTORY' or (job.profile_code == 'WEST_COAST_4_0_OL' and mode != 'NEW_RECEIPT'))):
        raise HTTPException(409, '历史转换记录尚未核对库存；请先核对实际在仓数量，不能重复入库、分配或出库。')


HISTORY_LABEL = '历史记录 · 库存待核对'

def history_job_ids(db):
    from sqlalchemy import select
    return set(db.scalars(select(ImportJob.id).where(ImportJob.profile_code == 'WEST_COAST_4_0_HISTORY')))
