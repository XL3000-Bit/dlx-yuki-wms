import json
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import ContainerTracking, Load, LoadStatus, OutboundOrder, PickingList, User, Warehouse, WorkOrderEvent
from app.models.work_order import WorkOrder, WorkOrderPriority, WorkOrderStatus, WorkOrderType
from app.services.operational_notification import sync_work_order_notifications

TRANSITIONS = {
    WorkOrderStatus.OPEN: {WorkOrderStatus.ASSIGNED, WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.CANCELED},
    WorkOrderStatus.ASSIGNED: {WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.CANCELED},
    WorkOrderStatus.IN_PROGRESS: {WorkOrderStatus.COMPLETED},
    WorkOrderStatus.COMPLETED: set(), WorkOrderStatus.CANCELED: set(),
}


def generate_work_order_no(db, today: date | None = None):
    day = today or date.today(); prefix = f"WO-{day:%Y%m%d}-"
    last = db.scalar(select(func.max(WorkOrder.work_order_no)).where(WorkOrder.work_order_no.like(prefix + "%")))
    return f"{prefix}{(int(last[-4:]) + 1 if last else 1):04d}"


def _enum(enum_type, value, label):
    try: return enum_type(str(value).upper())
    except ValueError as exc: raise HTTPException(422, f"Invalid {label}") from exc


def _text(value):
    if value is None: return None
    if hasattr(value, "value"): return str(value.value)
    if isinstance(value, datetime): return value.isoformat()
    return str(value)


def _assignment_value(user_id, team):
    return None if user_id is None and team is None else json.dumps({"user_id": user_id, "team": team}, separators=(",", ":"))


def _datetime_key(value):
    if value is None: return None
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _add_event(db, wo, event_type, user_id, *, field_name=None, old_value=None, new_value=None, message=None, **legacy):
    db.add(WorkOrderEvent(work_order_id=wo.id, event_type=event_type, actor_user_id=user_id,
        field_name=field_name, old_value=_text(old_value), new_value=_text(new_value), message=message, **legacy))


def _validate_refs(db, p):
    if not db.get(Warehouse, p.warehouse_id): raise HTTPException(422, "Warehouse not found")
    load = db.get(Load, p.load_id) if p.load_id else None
    outbound = db.get(OutboundOrder, p.outbound_id) if p.outbound_id else None
    picking = db.get(PickingList, p.picking_list_id) if p.picking_list_id else None
    container = db.get(ContainerTracking, p.container_tracking_id) if p.container_tracking_id else None
    if p.load_id and not load: raise HTTPException(404, "Load not found")
    if p.outbound_id and not outbound: raise HTTPException(404, "Outbound order not found")
    if p.picking_list_id and not picking: raise HTTPException(404, "Picking list not found")
    if p.container_tracking_id and not container: raise HTTPException(404, "Container tracking not found")
    if load and (load.warehouse_id != p.warehouse_id or load.status in (LoadStatus.COMPLETED, LoadStatus.CANCELED)): raise HTTPException(409, "Load is invalid for this work order")
    if outbound and (outbound.warehouse_id != p.warehouse_id or outbound.status in (5, 6)): raise HTTPException(409, "Outbound order is invalid for this work order")
    if picking and outbound and picking.outbound_order_id != outbound.id: raise HTTPException(409, "Picking list does not belong to outbound order")
    if picking and not outbound: outbound = db.get(OutboundOrder, picking.outbound_order_id)
    if outbound and outbound.warehouse_id != p.warehouse_id: raise HTTPException(409, "Related outbound warehouse differs")
    if container and container.warehouse_id and container.warehouse_id != p.warehouse_id: raise HTTPException(409, "Container warehouse differs")


def create_work_order(db, p, user_id):
    _validate_refs(db, p); data = p.model_dump()
    data["work_order_type"] = _enum(WorkOrderType, data.pop("work_order_type"), "work order type")
    data["priority"] = _enum(WorkOrderPriority, data["priority"], "priority"); data["created_by"] = user_id
    if data.get("assigned_to") and not db.get(User, data["assigned_to"]): raise HTTPException(422, "Assignee not found")
    wo = WorkOrder(work_order_no=generate_work_order_no(db), **data); db.add(wo); db.flush()
    _add_event(db, wo, "WORK_ORDER_CREATED", user_id, new_value=wo.work_order_no,
        message=f"Work order {wo.work_order_no} created", assigned_to_after=wo.assigned_to,
        assigned_team_after=wo.assigned_team, priority_after=wo.priority.value, note=wo.notes)
    sync_work_order_notifications(db, wo)
    sync_work_order_notifications(db, wo); db.commit(); return get_work_order(db, wo.id)


def get_work_order(db, id):
    wo = db.get(WorkOrder, id)
    if not wo: raise HTTPException(404, "Work order not found")
    return wo


def update_work_order(db, wo, p, user_id):
    if wo.status in (WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELED): raise HTTPException(409, "Terminal work order is immutable")
    data = p.model_dump(exclude_unset=True)
    before = {k: getattr(wo, k) for k in ("assigned_to", "assigned_team", "priority", "scheduled_at", "notes")}
    if "priority" in data and data["priority"] is not None: data["priority"] = _enum(WorkOrderPriority, data["priority"], "priority")
    if "assigned_to" in data and data["assigned_to"] and not db.get(User, data["assigned_to"]): raise HTTPException(422, "Assignee not found")
    for key, value in data.items(): setattr(wo, key, value)
    was, now = (before["assigned_to"], before["assigned_team"]), (wo.assigned_to, wo.assigned_team)
    if was != now:
        event_type = "UNASSIGNED" if now == (None, None) else "ASSIGNED" if was == (None, None) else "REASSIGNED"
        _add_event(db, wo, event_type, user_id, field_name="assignment", old_value=_assignment_value(*was), new_value=_assignment_value(*now),
            assigned_to_before=was[0], assigned_to_after=now[0], assigned_team_before=was[1], assigned_team_after=now[1])
    if before["priority"] != wo.priority:
        _add_event(db, wo, "PRIORITY_CHANGED", user_id, field_name="priority", old_value=before["priority"], new_value=wo.priority,
            priority_before=before["priority"].value, priority_after=wo.priority.value)
    if before["notes"] != wo.notes:
        _add_event(db, wo, "NOTE_UPDATED", user_id, field_name="notes", old_value=before["notes"], new_value=wo.notes, note=wo.notes)
    if _datetime_key(before["scheduled_at"]) != _datetime_key(wo.scheduled_at):
        _add_event(db, wo, "WORK_ORDER_UPDATED", user_id, field_name="scheduled_at", old_value=before["scheduled_at"], new_value=wo.scheduled_at)
    db.commit(); return get_work_order(db, wo.id)


def transition_work_order(db, wo, target, user_id):
    status = _enum(WorkOrderStatus, target, "work order status")
    if status not in TRANSITIONS[wo.status]: raise HTTPException(409, f"Invalid status transition: {wo.status.value} to {status.value}")
    old = wo.status; wo.status = status; now = datetime.now(timezone.utc)
    if status == WorkOrderStatus.IN_PROGRESS: wo.started_at = now
    if status == WorkOrderStatus.COMPLETED: wo.completed_at = now
    _add_event(db, wo, "STATUS_CHANGED", user_id, field_name="status", old_value=old, new_value=status, from_status=old.value, to_status=status.value)
    sync_work_order_notifications(db, wo)
    db.commit(); return get_work_order(db, wo.id)


def read_work_order(wo):
    keys = ("id", "work_order_no", "work_order_type", "status", "warehouse_id", "load_id", "outbound_id", "picking_list_id", "container_tracking_id", "operational_exception_id", "priority", "assigned_to", "assigned_team", "scheduled_at", "started_at", "completed_at", "notes", "created_by", "created_at", "updated_at")
    return {**{k: getattr(wo, k) for k in keys}, "work_order_type": wo.work_order_type.value, "status": wo.status.value,
        "priority": wo.priority.value, "assignee_name": wo.assignee.display_name if wo.assignee else None}


def read_event(event):
    actor = {"id": event.actor.id, "username": event.actor.username, "display_name": event.actor.display_name} if event.actor else None
    return {"id": event.id, "event_type": event.event_type, "field_name": event.field_name, "old_value": event.old_value,
        "new_value": event.new_value, "message": event.message, "from_status": event.from_status, "to_status": event.to_status,
        "actor_user_id": event.actor_user_id, "actor_name": event.actor.display_name if event.actor else "System", "actor": actor,
        "assigned_to_before": event.assigned_to_before, "assigned_to_after": event.assigned_to_after,
        "assigned_team_before": event.assigned_team_before, "assigned_team_after": event.assigned_team_after,
        "priority_before": event.priority_before, "priority_after": event.priority_after, "note": event.note, "created_at": event.created_at}
