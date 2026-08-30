from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from app.models import (ExceptionSeverity, ExceptionStatus, Load, LoadStatus, NotificationSeverity,
    NotificationType, OperationalException, OperationalNotification, User, UserRole, WorkOrder,
    WorkOrderPriority, WorkOrderStatus)
from app.models.user import ScopeMode
from app.services.access_policy import warehouse_clause

OPEN_WORK_ORDERS = (WorkOrderStatus.OPEN, WorkOrderStatus.ASSIGNED, WorkOrderStatus.IN_PROGRESS)
UPCOMING_WINDOW = timedelta(hours=2)


def _utc(value=None):
    value = value or datetime.now(timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _recipients(db, warehouse_id, assigned_to=None, owner_id=None):
    for candidate in (assigned_to, owner_id):
        user = db.get(User, candidate) if candidate else None
        if user and user.is_active:
            return [user.id]
    users = db.scalars(select(User).where(User.is_active.is_(True), User.role.in_([UserRole.MANAGER, UserRole.WAREHOUSE]))).all()
    return [user.id for user in users if user.warehouse_scope_mode == ScopeMode.ALL or warehouse_id in user.warehouse_ids]


def _sync(db, *, active, notification_type, severity, title, message, warehouse_id,
          source_type, source_id, reference, target_route, recipient_ids, expires_at=None):
    key = f"{notification_type.value}:{source_type}:{source_id}"
    rows = list(db.scalars(select(OperationalNotification).where(
        OperationalNotification.source_type == source_type,
        OperationalNotification.source_id == source_id,
        OperationalNotification.notification_type == notification_type)).all())
    desired = set(recipient_ids if active else [])
    now = _utc()
    by_user = {row.user_id: row for row in rows}
    for row in rows:
        if row.user_id not in desired and row.is_active:
            row.is_active = False; row.resolved_at = now
    for user_id in desired:
        row = by_user.get(user_id)
        if row is None:
            db.add(OperationalNotification(notification_type=notification_type, severity=severity, title=title,
                message=message, user_id=user_id, warehouse_id=warehouse_id, source_type=source_type,
                source_id=source_id, reference=reference, target_route=target_route, dedupe_key=key,
                expires_at=expires_at))
        else:
            row.severity=severity; row.title=title; row.message=message; row.target_route=target_route
            row.expires_at=expires_at; row.is_active=True; row.resolved_at=None


def sync_exception_notification(db, row):
    active = row.severity == ExceptionSeverity.CRITICAL and row.status in (ExceptionStatus.OPEN, ExceptionStatus.INVESTIGATING)
    _sync(db, active=active, notification_type=NotificationType.EXCEPTION_CRITICAL,
        severity=NotificationSeverity.CRITICAL, title="Critical operational exception",
        message=f"{row.exception_no}: {row.title}", warehouse_id=row.warehouse_id,
        source_type="operational_exception", source_id=row.id, reference=row.exception_no,
        target_route=f"/trouble-shoot?selected={row.id}",
        recipient_ids=_recipients(db,row.warehouse_id,row.assigned_to,row.reported_by))


def sync_work_order_notifications(db, row, now=None):
    now = _utc(now); open_status = row.status in OPEN_WORK_ORDERS
    recipients = _recipients(db,row.warehouse_id,row.assigned_to,row.created_by)
    _sync(db, active=open_status and row.priority == WorkOrderPriority.URGENT,
        notification_type=NotificationType.WORK_ORDER_URGENT, severity=NotificationSeverity.HIGH,
        title="Urgent work order", message=f"{row.work_order_no} requires attention",
        warehouse_id=row.warehouse_id, source_type="work_order", source_id=row.id,
        reference=row.work_order_no, target_route=f"/work-orders?selected={row.id}", recipient_ids=recipients)
    overdue = open_status and row.scheduled_at is not None and _utc(row.scheduled_at) < now
    _sync(db, active=overdue, notification_type=NotificationType.WORK_ORDER_OVERDUE,
        severity=NotificationSeverity.HIGH, title="Overdue work order",
        message=f"{row.work_order_no} is past its scheduled time", warehouse_id=row.warehouse_id,
        source_type="work_order", source_id=row.id, reference=row.work_order_no,
        target_route=f"/work-orders?selected={row.id}", recipient_ids=recipients)


def sync_load_notification(db, row, now=None):
    now = _utc(now); appointment = _utc(row.appointment_time) if row.appointment_time else None
    active = row.status in (LoadStatus.PLANNED, LoadStatus.READY) and appointment is not None and now <= appointment <= now + UPCOMING_WINDOW
    _sync(db, active=active, notification_type=NotificationType.LOAD_APPOINTMENT_UPCOMING,
        severity=NotificationSeverity.WARNING, title="Load appointment upcoming",
        message=f"{row.load_no} appointment is within two hours", warehouse_id=row.warehouse_id,
        source_type="load", source_id=row.id, reference=row.load_no,
        target_route=f"/loads?selected={row.id}", recipient_ids=_recipients(db,row.warehouse_id,None,row.created_by),
        expires_at=appointment)


def evaluate_time_notifications(db, user, now=None):
    now = _utc(now)
    wo_stmt=select(WorkOrder).where(WorkOrder.status.in_(OPEN_WORK_ORDERS),WorkOrder.scheduled_at.is_not(None),WorkOrder.scheduled_at < now)
    load_stmt=select(Load).where(Load.status.in_([LoadStatus.PLANNED,LoadStatus.READY]),Load.appointment_time >= now,Load.appointment_time <= now+UPCOMING_WINDOW)
    for stmt, column, sync in ((wo_stmt,WorkOrder.warehouse_id,sync_work_order_notifications),(load_stmt,Load.warehouse_id,sync_load_notification)):
        clause=warehouse_clause(user,column)
        for row in db.scalars(stmt.where(clause) if clause is not None else stmt).all(): sync(db,row,now)


def visible_notifications_stmt(user):
    now=_utc()
    stmt=select(OperationalNotification).where(OperationalNotification.user_id==user.id,
        OperationalNotification.is_active.is_(True),or_(OperationalNotification.expires_at.is_(None),OperationalNotification.expires_at>=now))
    clause=warehouse_clause(user,OperationalNotification.warehouse_id)
    return stmt.where(clause) if clause is not None else stmt


def read_notification(row):
    return {"id":row.id,"type":row.notification_type.value,"severity":row.severity.value,"title":row.title,
        "message":row.message,"warehouse_id":row.warehouse_id,"source_type":row.source_type,"source_id":row.source_id,
        "reference":row.reference,"target_route":row.target_route,"is_read":row.is_read,"read_at":row.read_at,
        "created_at":row.created_at,"expires_at":row.expires_at}
