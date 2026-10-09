from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from app.api.deps import CurrentUser, DbSession
from app.models import OperationalNotification
from app.services.operational_notification import evaluate_time_notifications, read_notification, visible_notifications_stmt

router=APIRouter(prefix="/notifications",tags=["Notifications"])

def _refresh(db,user): evaluate_time_notifications(db,user); db.commit()

@router.get("")
def list_notifications(db:DbSession,user:CurrentUser,page:int=Query(1,ge=1),per_page:int=Query(20,ge=1,le=100),unread_only:bool=False):
    _refresh(db,user); stmt=visible_notifications_stmt(user)
    if unread_only: stmt=stmt.where(OperationalNotification.is_read.is_(False))
    total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows=db.scalars(stmt.order_by(OperationalNotification.created_at.desc(),OperationalNotification.id.desc()).offset((page-1)*per_page).limit(per_page)).all()
    return {"data":[read_notification(row) for row in rows],"meta":{"page":page,"per_page":per_page,"total":total,"total_pages":(total+per_page-1)//per_page}}

@router.get("/unread-count")
def unread_count(db:DbSession,user:CurrentUser):
    _refresh(db,user); count=db.scalar(select(func.count()).select_from(visible_notifications_stmt(user).where(OperationalNotification.is_read.is_(False)).subquery())) or 0
    return {"count":count}

@router.post("/mark-all-read")
def mark_all_read(db:DbSession,user:CurrentUser):
    rows=db.scalars(visible_notifications_stmt(user).where(OperationalNotification.is_read.is_(False))).all(); now=datetime.now(timezone.utc)
    for row in rows: row.is_read=True; row.read_at=now
    db.commit(); return {"updated":len(rows)}

@router.post("/{notification_id}/read")
def mark_read(notification_id:int,db:DbSession,user:CurrentUser):
    row=db.scalar(visible_notifications_stmt(user).where(OperationalNotification.id==notification_id))
    if row is None: raise HTTPException(404,"Notification not found")
    if not row.is_read: row.is_read=True; row.read_at=datetime.now(timezone.utc); db.commit()
    return read_notification(row)

@router.post("/refresh")
def refresh(db:DbSession,user:CurrentUser): _refresh(db,user); return {"status":"ok"}
