import json
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from app.models import (BOL, ContainerTracking, ExceptionSeverity, ExceptionStatus, ExceptionType, Load,
    OperationalException, OperationalExceptionEvent, OutboundOrder, PickingList, User, Warehouse, WorkOrder)
from app.utils.business_time import get_business_today

TRANSITIONS = {ExceptionStatus.OPEN: {ExceptionStatus.INVESTIGATING, ExceptionStatus.RESOLVED, ExceptionStatus.CANCELED},
    ExceptionStatus.INVESTIGATING: {ExceptionStatus.RESOLVED, ExceptionStatus.CANCELED}, ExceptionStatus.RESOLVED: set(), ExceptionStatus.CANCELED: set()}
REFS = (("outbound_id", OutboundOrder, "Outbound order"), ("load_id", Load, "Load"),
    ("container_tracking_id", ContainerTracking, "Container tracking"), ("picking_list_id", PickingList, "Picking list"), ("bol_id", BOL, "BOL"))


def _enum(cls, value, label):
    if isinstance(value, cls):
        return value
    try: return cls(str(value).upper())
    except ValueError as exc: raise HTTPException(422, f"Invalid {label}") from exc


def generate_exception_no(db, today: date | None = None):
    day = today or get_business_today(); prefix = f"EX-{day:%Y%m%d}-"
    last = db.scalar(select(func.max(OperationalException.exception_no)).where(OperationalException.exception_no.like(prefix + "%")))
    return f"{prefix}{(int(last[-4:]) + 1 if last else 1):04d}"


def exception_query():
    return select(OperationalException).options(joinedload(OperationalException.assignee), joinedload(OperationalException.warehouse),
        joinedload(OperationalException.outbound), joinedload(OperationalException.load), joinedload(OperationalException.container_tracking),
        joinedload(OperationalException.picking_list), joinedload(OperationalException.bol), selectinload(OperationalException.work_orders))


def get_exception(db, exception_id):
    row = db.scalar(exception_query().where(OperationalException.id == exception_id))
    if not row: raise HTTPException(404, "Operational exception not found")
    return row


def _event(db, row, event_type, actor_id, *, field_name=None, old=None, new=None, message=None):
    def text(value):
        if value is None: return None
        if hasattr(value, "value"): return value.value
        return str(value)
    db.add(OperationalExceptionEvent(operational_exception_id=row.id, event_type=event_type, actor_user_id=actor_id,
        field_name=field_name, old_value=text(old), new_value=text(new), message=message, created_at=datetime.now(timezone.utc)))


def _warehouse_for(obj):
    if isinstance(obj, PickingList): return obj.outbound.warehouse_id
    return getattr(obj, "warehouse_id", None)


def _validate_refs(db, payload):
    if not db.get(Warehouse, payload.warehouse_id): raise HTTPException(422, "Warehouse not found")
    objects = []
    for field, model, label in REFS:
        value = getattr(payload, field, None)
        if value:
            obj = db.get(model, value)
            if not obj: raise HTTPException(404, f"{label} not found")
            objects.append((field, obj))
    if getattr(payload, "work_order_id", None):
        work_order = db.get(WorkOrder, payload.work_order_id)
        if not work_order: raise HTTPException(404, "Work order not found")
        objects.append(("work_order_id", work_order))
    if not objects: raise HTTPException(422, "At least one related operational object is required")
    if getattr(payload, "outbound_id", None) and getattr(payload, "load_id", None):
        outbound = next(obj for field, obj in objects if field == "outbound_id")
        if outbound.load_id != payload.load_id: raise HTTPException(409, "Outbound order does not belong to the related load")
    if getattr(payload, "outbound_id", None) and getattr(payload, "picking_list_id", None):
        picking = next(obj for field, obj in objects if field == "picking_list_id")
        if picking.outbound_order_id != payload.outbound_id: raise HTTPException(409, "Picking list does not belong to the related outbound order")
    if getattr(payload, "outbound_id", None) and getattr(payload, "bol_id", None):
        bol = next(obj for field, obj in objects if field == "bol_id")
        if bol.outbound_order_id != payload.outbound_id: raise HTTPException(409, "BOL does not belong to the related outbound order")
    for _, obj in objects:
        warehouse_id = _warehouse_for(obj)
        if warehouse_id and warehouse_id != payload.warehouse_id: raise HTTPException(409, "Related object warehouse differs from exception warehouse")
    return objects


def create_exception(db, payload, user_id, *, commit=True):
    objects = _validate_refs(db, payload)
    if payload.assigned_to and not db.get(User, payload.assigned_to): raise HTTPException(422, "Assignee not found")
    exception_type = _enum(ExceptionType, payload.exception_type, "exception type")
    severity = _enum(ExceptionSeverity, payload.severity, "severity")
    duplicate_terms = [getattr(OperationalException, field) == getattr(payload, field) for field, _ in objects if field != "work_order_id"]
    work_order = next((obj for field, obj in objects if field == "work_order_id"), None)
    if work_order and work_order.operational_exception_id:
        linked = db.get(OperationalException, work_order.operational_exception_id)
        if linked and linked.exception_type == exception_type and linked.status in (ExceptionStatus.OPEN, ExceptionStatus.INVESTIGATING):
            raise HTTPException(409, f"Active duplicate exists: {linked.exception_no}")
    duplicate = db.scalar(select(OperationalException).where(OperationalException.exception_type == exception_type,
        OperationalException.status.in_([ExceptionStatus.OPEN, ExceptionStatus.INVESTIGATING]), or_(*duplicate_terms))) if duplicate_terms else None
    if duplicate: raise HTTPException(409, f"Active duplicate exists: {duplicate.exception_no}")
    data = payload.model_dump(exclude={"work_order_id"}); data.update(exception_type=exception_type, severity=severity, status=ExceptionStatus.OPEN,
        exception_no=generate_exception_no(db), reported_at=datetime.now(timezone.utc), reported_by=user_id)
    row = OperationalException(**data); db.add(row); db.flush()
    if work_order: work_order.operational_exception_id = row.id
    _event(db, row, "EXCEPTION_CREATED", user_id, new=row.exception_no, message=f"Exception {row.exception_no} created")
    if row.assigned_to or row.assigned_team: _event(db, row, "ASSIGNED", user_id, field_name="assignment", new=json.dumps({"user_id": row.assigned_to, "team": row.assigned_team}))
    if commit: db.commit(); return get_exception(db, row.id)
    return row


def update_exception(db, row, payload, user_id):
    if row.status in (ExceptionStatus.RESOLVED, ExceptionStatus.CANCELED): raise HTTPException(409, "Terminal exception is immutable")
    data = payload.model_dump(exclude_unset=True)
    if "severity" in data: data["severity"] = _enum(ExceptionSeverity, data["severity"], "severity")
    mapping = {"severity": "SEVERITY_CHANGED", "description": "DESCRIPTION_UPDATED", "resolution": "RESOLUTION_UPDATED"}
    for field, value in data.items():
        old = getattr(row, field)
        if old != value: setattr(row, field, value); _event(db, row, mapping[field], user_id, field_name=field, old=old, new=value)
    db.commit(); return get_exception(db, row.id)


def assign_exception(db, row, payload, user_id):
    if row.status in (ExceptionStatus.RESOLVED, ExceptionStatus.CANCELED): raise HTTPException(409, "Terminal exception is immutable")
    if payload.assigned_to and not db.get(User, payload.assigned_to): raise HTTPException(422, "Assignee not found")
    old = (row.assigned_to, row.assigned_team); new = (payload.assigned_to, payload.assigned_team)
    if old != new:
        row.assigned_to, row.assigned_team = new
        event = "UNASSIGNED" if new == (None, None) else "ASSIGNED" if old == (None, None) else "REASSIGNED"
        _event(db, row, event, user_id, field_name="assignment", old=json.dumps({"user_id": old[0], "team": old[1]}), new=json.dumps({"user_id": new[0], "team": new[1]}))
    db.commit(); return get_exception(db, row.id)


def transition_exception(db, row, target, user_id, resolution=None, *, commit=True):
    status = _enum(ExceptionStatus, target, "exception status")
    if status not in TRANSITIONS[row.status]: raise HTTPException(409, f"Invalid status transition: {row.status.value} to {status.value}")
    if status == ExceptionStatus.RESOLVED and not (resolution and resolution.strip()): raise HTTPException(422, "Resolution is required")
    old = row.status; row.status = status
    if status == ExceptionStatus.RESOLVED:
        if row.resolution != resolution: _event(db, row, "RESOLUTION_UPDATED", user_id, field_name="resolution", old=row.resolution, new=resolution)
        row.resolution = resolution.strip(); row.resolved_at = datetime.now(timezone.utc); row.resolved_by = user_id
    _event(db, row, "STATUS_CHANGED", user_id, field_name="status", old=old, new=status)
    if commit: db.commit(); return get_exception(db, row.id)
    return row


def read_exception(row):
    related = {}
    if row.outbound: related["outbound"] = {"id": row.outbound.id, "label": row.outbound.ob_no}
    if row.load: related["load"] = {"id": row.load.id, "label": row.load.load_no}
    if row.container_tracking: related["container"] = {"id": row.container_tracking.id, "label": row.container_tracking.container_number}
    if row.picking_list: related["picking"] = {"id": row.picking_list.id, "label": row.picking_list.picking_no}
    if row.bol: related["bol"] = {"id": row.bol.id, "label": row.bol.bol_no}
    keys = ("id", "exception_no", "title", "description", "warehouse_id", "outbound_id", "load_id", "container_tracking_id", "picking_list_id", "bol_id", "assigned_to", "assigned_team", "reported_at", "reported_by", "resolved_at", "resolved_by", "resolution", "created_at", "updated_at")
    work_orders = [{"id": wo.id, "work_order_no": wo.work_order_no, "status": wo.status.value, "priority": wo.priority.value} for wo in row.work_orders]
    return {**{key: getattr(row, key) for key in keys}, "exception_type": row.exception_type.value, "severity": row.severity.value,
        "status": row.status.value, "assignee_name": row.assignee.display_name if row.assignee else None, "related": related, "work_orders": work_orders}


def read_event(row):
    return {"id": row.id, "event_type": row.event_type, "actor_user_id": row.actor_user_id,
        "actor_name": row.actor.display_name if row.actor else "System", "field_name": row.field_name,
        "old_value": row.old_value, "new_value": row.new_value, "message": row.message, "created_at": row.created_at}
