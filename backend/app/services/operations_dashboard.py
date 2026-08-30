from datetime import datetime, timedelta
from sqlalchemy import func, select
from app.models import Load, OperationalException, OperationalExceptionEvent, OutboundOrder, Warehouse, WorkOrder, WorkOrderEvent
from app.models.load import LoadStatus
from app.models.operational_exception import ExceptionSeverity, ExceptionStatus, ExceptionType
from app.models.outbound import OBStatus
from app.models.work_order import WorkOrderPriority, WorkOrderStatus
from app.services.access import apply_warehouse_scope, get_access_scope
from app.utils.business_time import business_day_range, get_business_now, get_business_today, to_business_datetime

ACTIVE_LOADS = (LoadStatus.PLANNED, LoadStatus.READY, LoadStatus.DISPATCHED)
OPEN_WO = (WorkOrderStatus.OPEN, WorkOrderStatus.ASSIGNED, WorkOrderStatus.IN_PROGRESS)
OPEN_EX = (ExceptionStatus.OPEN, ExceptionStatus.INVESTIGATING)
ACTIVE_OB = (OBStatus.NEW, OBStatus.HOLD, OBStatus.IN_PROGRESS, OBStatus.CONFIRMED, OBStatus.DISPATCHED, OBStatus.EXCEPTION)
READY_OB = (OBStatus.CONFIRMED, OBStatus.IN_PROGRESS)


def _period(preset: str | None, date_from, date_to):
    today = get_business_today()
    if date_from and date_to:
        start, _ = business_day_range(date_from)
        _, end = business_day_range(date_to)
        return start, end, "custom"
    key = (preset or "today").lower()
    if key == "yesterday":
        start, end = business_day_range(today - timedelta(days=1))
        return start, end, "yesterday"
    if key == "last_7_days":
        start, _ = business_day_range(today - timedelta(days=6))
        _, end = business_day_range(today)
        return start, end, "last_7_days"
    if key == "this_month":
        start, _ = business_day_range(today.replace(day=1))
        _, end = business_day_range(today)
        return start, end, "this_month"
    start, end = business_day_range(today)
    return start, end, "today"


def _key(value):
    return value.value if hasattr(value, "value") else value


def _count_map(db, stmt):
    return {_key(key): int(value) for key, value in db.execute(stmt).all()}


def _age_bucket(age: timedelta, kind: str) -> str:
    hours = age.total_seconds() / 3600
    if kind == "exception":
        if hours < 4:
            return "lt_4h"
        if hours < 12:
            return "h4_12"
        if hours < 24:
            return "h12_24"
        if hours < 72:
            return "d1_3"
        return "gt_3d"
    if hours < 4:
        return "lt_4h"
    if hours < 12:
        return "h4_12"
    if hours < 24:
        return "h12_24"
    return "gt_24h"


def operations_dashboard(db, user, *, warehouse_id: int | None = None, preset: str | None = None, date_from=None, date_to=None):
    scope = get_access_scope(db, user)
    if warehouse_id is not None and not scope.allows_warehouse(warehouse_id):
        warehouse_id = -1
    period_start, period_end, period_key = _period(preset, date_from, date_to)
    now = get_business_now()
    today_start, today_end = business_day_range(get_business_today())

    def scoped(stmt, column):
        stmt = apply_warehouse_scope(stmt, column, scope)
        if warehouse_id is not None:
            stmt = stmt.where(column == warehouse_id)
        return stmt

    load_status = _count_map(db, scoped(select(Load.status, func.count()), Load.warehouse_id).group_by(Load.status))
    wo_status = _count_map(db, scoped(select(WorkOrder.status, func.count()), WorkOrder.warehouse_id).group_by(WorkOrder.status))
    wo_priority = _count_map(db, scoped(select(WorkOrder.priority, func.count()), WorkOrder.warehouse_id).where(WorkOrder.status.in_(OPEN_WO)).group_by(WorkOrder.priority))
    ex_status = _count_map(db, scoped(select(OperationalException.status, func.count()), OperationalException.warehouse_id).group_by(OperationalException.status))
    ex_sev = _count_map(db, scoped(select(OperationalException.severity, func.count()), OperationalException.warehouse_id).where(OperationalException.status.in_(OPEN_EX)).group_by(OperationalException.severity))
    ex_type = _count_map(db, scoped(select(OperationalException.exception_type, func.count()), OperationalException.warehouse_id).where(OperationalException.status.in_(OPEN_EX)).group_by(OperationalException.exception_type))
    ob_status = _count_map(db, scoped(select(OutboundOrder.status, func.count()), OutboundOrder.warehouse_id).group_by(OutboundOrder.status))

    loads_created = db.scalar(scoped(select(func.count()), Load.warehouse_id).where(Load.created_at >= period_start, Load.created_at < period_end)) or 0
    wo_completed_period = db.scalar(scoped(select(func.count()), WorkOrder.warehouse_id).where(WorkOrder.completed_at >= period_start, WorkOrder.completed_at < period_end)) or 0
    wo_completed_today = db.scalar(scoped(select(func.count()), WorkOrder.warehouse_id).where(WorkOrder.completed_at >= today_start, WorkOrder.completed_at < today_end)) or 0
    loads_completed_period = db.scalar(scoped(select(func.count()), Load.warehouse_id).where(Load.status == LoadStatus.COMPLETED, Load.updated_at >= period_start, Load.updated_at < period_end)) or 0
    active_load_ids = scoped(select(Load.id), Load.warehouse_id).where(Load.status.in_(ACTIVE_LOADS))
    outbound_on_active = db.scalar(select(func.count()).select_from(OutboundOrder).where(OutboundOrder.load_id.in_(active_load_ids))) or 0
    active_load_count = int(sum(load_status.get(status.value, 0) for status in ACTIVE_LOADS))
    avg_ob_per_load = (outbound_on_active / active_load_count) if active_load_count else None

    resolved_rows = list(db.execute(scoped(select(OperationalException.reported_at, OperationalException.resolved_at), OperationalException.warehouse_id).where(OperationalException.status == ExceptionStatus.RESOLVED, OperationalException.resolved_at.is_not(None))).all())
    if resolved_rows:
        seconds = []
        for reported, resolved in resolved_rows:
            start = to_business_datetime(reported)
            end = to_business_datetime(resolved)
            if start and end and end >= start:
                seconds.append((end - start).total_seconds())
        avg_resolution_seconds = sum(seconds) / len(seconds) if seconds else None
    else:
        avg_resolution_seconds = None

    open_exceptions = list(db.execute(scoped(select(OperationalException.id, OperationalException.exception_no, OperationalException.severity, OperationalException.status, OperationalException.warehouse_id, OperationalException.reported_at, OperationalException.title, OperationalException.load_id, OperationalException.outbound_id), OperationalException.warehouse_id).where(OperationalException.status.in_(OPEN_EX))).all())
    open_wos = list(db.execute(scoped(select(WorkOrder.id, WorkOrder.work_order_no, WorkOrder.priority, WorkOrder.status, WorkOrder.warehouse_id, WorkOrder.created_at, WorkOrder.scheduled_at, WorkOrder.load_id, WorkOrder.outbound_id), WorkOrder.warehouse_id).where(WorkOrder.status.in_(OPEN_WO))).all())

    ex_aging = {"lt_4h": 0, "h4_12": 0, "h12_24": 0, "d1_3": 0, "gt_3d": 0}
    wo_aging = {"lt_4h": 0, "h4_12": 0, "h12_24": 0, "gt_24h": 0}
    attention = []
    for row in open_exceptions:
        reported = to_business_datetime(row.reported_at) or now
        age = now - reported
        bucket = _age_bucket(age, "exception")
        ex_aging[bucket] += 1
        score = 0
        if row.severity == ExceptionSeverity.CRITICAL:
            score += 100
        if age >= timedelta(hours=24):
            score += 40
        if age >= timedelta(hours=72):
            score += 20
        attention.append({"score": score, "kind": "EXCEPTION", "id": row.id, "reference": row.exception_no, "status": _key(row.status), "severity_or_priority": _key(row.severity), "age_hours": round(age.total_seconds() / 3600, 1), "title": row.title, "target_route": f"/trouble-shoot?selected={row.id}"})
    overdue_wo = 0
    for row in open_wos:
        created = to_business_datetime(row.created_at) or now
        age = now - created
        wo_aging[_age_bucket(age, "work_order")] += 1
        scheduled = to_business_datetime(row.scheduled_at)
        if scheduled and scheduled < now:
            overdue_wo += 1
        score = 0
        if row.priority == WorkOrderPriority.URGENT:
            score += 80
        if age >= timedelta(hours=24):
            score += 30
        attention.append({"score": score, "kind": "WORK_ORDER", "id": row.id, "reference": row.work_order_no, "status": _key(row.status), "severity_or_priority": _key(row.priority), "age_hours": round(age.total_seconds() / 3600, 1), "title": _key(row.status), "target_route": f"/work-orders?selected={row.id}"})
    attention.sort(key=lambda item: (-item["score"], -item["age_hours"]))
    attention = [{k: v for k, v in item.items() if k != "score"} for item in attention[:20]]

    warehouses = list(db.scalars(apply_warehouse_scope(select(Warehouse), Warehouse.id, scope)).all())
    if warehouse_id is not None:
        warehouses = [row for row in warehouses if row.id == warehouse_id]
    breakdown = []
    if len(warehouses) > 1 or scope.warehouse_all:
        for warehouse in warehouses:
            breakdown.append({
                "warehouse_id": warehouse.id,
                "warehouse_code": warehouse.warehouse_code,
                "active_loads": db.scalar(select(func.count()).select_from(Load).where(Load.warehouse_id == warehouse.id, Load.status.in_(ACTIVE_LOADS))) or 0,
                "open_work_orders": db.scalar(select(func.count()).select_from(WorkOrder).where(WorkOrder.warehouse_id == warehouse.id, WorkOrder.status.in_(OPEN_WO))) or 0,
                "open_exceptions": db.scalar(select(func.count()).select_from(OperationalException).where(OperationalException.warehouse_id == warehouse.id, OperationalException.status.in_(OPEN_EX))) or 0,
                "critical_exceptions": db.scalar(select(func.count()).select_from(OperationalException).where(OperationalException.warehouse_id == warehouse.id, OperationalException.status.in_(OPEN_EX), OperationalException.severity == ExceptionSeverity.CRITICAL)) or 0,
            })

    wo_events = list(db.execute(scoped(select(WorkOrderEvent.created_at, WorkOrderEvent.event_type, WorkOrder.work_order_no, WorkOrderEvent.actor_user_id, WorkOrderEvent.note, WorkOrderEvent.message, WorkOrder.id), WorkOrder.warehouse_id).join(WorkOrder, WorkOrder.id == WorkOrderEvent.work_order_id).order_by(WorkOrderEvent.created_at.desc()).limit(20)).all())
    ex_events = list(db.execute(scoped(select(OperationalExceptionEvent.created_at, OperationalExceptionEvent.event_type, OperationalException.exception_no, OperationalExceptionEvent.actor_user_id, OperationalExceptionEvent.message, OperationalException.id), OperationalException.warehouse_id).join(OperationalException, OperationalException.id == OperationalExceptionEvent.operational_exception_id).order_by(OperationalExceptionEvent.created_at.desc()).limit(20)).all())
    recent = []
    for row in wo_events:
        recent.append({"created_at": row[0], "kind": "WORK_ORDER", "event_type": row[1], "reference": row[2], "actor_user_id": row[3], "summary": row[5] or row[4] or row[1], "target_route": f"/work-orders?selected={row[6]}"})
    for row in ex_events:
        recent.append({"created_at": row[0], "kind": "EXCEPTION", "event_type": row[1], "reference": row[2], "actor_user_id": row[3], "summary": row[4] or row[1], "target_route": f"/trouble-shoot?selected={row[5]}"})
    recent.sort(key=lambda item: item["created_at"] or datetime.min.replace(tzinfo=None), reverse=True)
    recent = recent[:15]

    open_exceptions_count = int(sum(ex_status.get(status.value, 0) for status in OPEN_EX))
    open_wo_count = int(sum(wo_status.get(status.value, 0) for status in OPEN_WO))
    outbound_ready = int(sum(ob_status.get(status.value, 0) for status in READY_OB))
    outbound_active = int(sum(ob_status.get(status.value, 0) for status in ACTIVE_OB))

    return {
        "filters": {"warehouse_id": warehouse_id, "period": period_key, "period_start": period_start, "period_end": period_end},
        "definitions": {
            "active_load": "PLANNED/READY/DISPATCHED",
            "open_work_order": "OPEN/ASSIGNED/IN_PROGRESS",
            "open_exception": "OPEN/INVESTIGATING",
            "work_order_age_from": "created_at",
            "exception_age_from": "reported_at",
            "overdue_work_order": "scheduled_at present and scheduled_at < now",
            "completed_today": "work_order.completed_at within America/Los_Angeles business day",
        },
        "summary": {
            "active_loads": {"value": active_load_count, "kind": "snapshot", "href": "/loads"},
            "outbound_ready_active": {"value": outbound_ready, "active": outbound_active, "kind": "snapshot", "href": "/outbound/dispatch"},
            "open_work_orders": {"value": open_wo_count, "kind": "snapshot", "href": "/work-orders?status=OPEN"},
            "open_exceptions": {"value": open_exceptions_count, "kind": "snapshot", "href": "/trouble-shoot?status=OPEN"},
            "critical_exceptions": {"value": int(ex_sev.get(ExceptionSeverity.CRITICAL.value, 0)), "kind": "snapshot", "href": "/trouble-shoot?severity=CRITICAL"},
            "completed_today": {"value": wo_completed_today, "kind": "period", "href": "/work-orders?status=COMPLETED"},
        },
        "loads": {
            "created_in_period": loads_created,
            "status": {status.value: int(load_status.get(status.value, 0)) for status in LoadStatus},
            "active": active_load_count,
            "completed_in_period": loads_completed_period,
            "average_outbounds_per_active_load": avg_ob_per_load,
        },
        "work_orders": {
            "status": {status.value: int(wo_status.get(status.value, 0)) for status in WorkOrderStatus},
            "priority_open": {status.value: int(wo_priority.get(status.value, 0)) for status in WorkOrderPriority},
            "completed_today": wo_completed_today,
            "completed_in_period": wo_completed_period,
            "overdue": overdue_wo,
            "aging": wo_aging,
            "funnel": [{"key": status.value, "value": int(wo_status.get(status.value, 0))} for status in (WorkOrderStatus.OPEN, WorkOrderStatus.ASSIGNED, WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.COMPLETED)],
        },
        "exceptions": {
            "status": {status.value: int(ex_status.get(status.value, 0)) for status in ExceptionStatus},
            "severity_open": {status.value: int(ex_sev.get(status.value, 0)) for status in ExceptionSeverity},
            "types_open": sorted(({"type": key, "count": int(value)} for key, value in ex_type.items()), key=lambda item: (-item["count"], item["type"])),
            "average_resolution_seconds": avg_resolution_seconds,
            "aging": ex_aging,
        },
        "warehouse_breakdown": breakdown,
        "attention": attention,
        "recent_activity": recent,
    }
