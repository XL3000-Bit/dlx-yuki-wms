from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models.load import Load, LoadStatus
from app.models.operational_exception import ExceptionSeverity, ExceptionStatus, OperationalException, OperationalExceptionEvent
from app.models.outbound import OBStatus, OutboundOrder
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.work_order import WorkOrder, WorkOrderPriority, WorkOrderStatus
from app.models.work_order_event import WorkOrderEvent
from app.services.access_policy import customer_clause, warehouse_clause

# Central KPI definitions. Snapshot metrics deliberately ignore the reporting period.
ACTIVE_LOAD_STATUSES = (LoadStatus.PLANNED, LoadStatus.READY, LoadStatus.DISPATCHED)
ACTIVE_OUTBOUND_STATUSES = (OBStatus.NEW, OBStatus.HOLD, OBStatus.IN_PROGRESS, OBStatus.CONFIRMED, OBStatus.DISPATCHED, OBStatus.EXCEPTION)
READY_OUTBOUND_STATUSES = (OBStatus.CONFIRMED, OBStatus.DISPATCHED)
OPEN_WORK_ORDER_STATUSES = (WorkOrderStatus.OPEN, WorkOrderStatus.ASSIGNED, WorkOrderStatus.IN_PROGRESS)
OPEN_EXCEPTION_STATUSES = (ExceptionStatus.OPEN, ExceptionStatus.INVESTIGATING)


def _filters(user: User, column, warehouse_id: int | None) -> list:
    result = []
    scope = warehouse_clause(user, column)
    if scope is not None:
        result.append(scope)
    if warehouse_id is not None:
        result.append(column == warehouse_id)
    return result


def _group_counts(db: Session, column, *where) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).where(*where).group_by(column)).all()
    return {(key.value if hasattr(key, "value") else str(key)): count for key, count in rows}


def _age_counts(db: Session, model, start_column, now: datetime, boundaries: tuple[int, ...], *where) -> list[int]:
    expressions = []
    previous = None
    for hours in boundaries:
        lower = now - timedelta(hours=hours)
        condition = start_column > lower if previous is None else and_(start_column <= now - timedelta(hours=previous), start_column > lower)
        expressions.append(func.sum(case((condition, 1), else_=0)))
        previous = hours
    expressions.append(func.sum(case((start_column <= now - timedelta(hours=boundaries[-1]), 1), else_=0)))
    row = db.execute(select(*expressions).select_from(model).where(*where)).one()
    return [int(value or 0) for value in row]


def build_operations_dashboard(db: Session, user: User, start: datetime, end: datetime, now: datetime, warehouse_id: int | None) -> dict:
    load_scope = _filters(user, Load.warehouse_id, warehouse_id)
    wo_scope = _filters(user, WorkOrder.warehouse_id, warehouse_id)
    ex_scope = _filters(user, OperationalException.warehouse_id, warehouse_id)
    ob_scope = _filters(user, OutboundOrder.warehouse_id, warehouse_id)
    customer_scope = customer_clause(user, OutboundOrder.customer_id)
    if customer_scope is not None:
        ob_scope.append(customer_scope)

    active_loads = db.scalar(select(func.count()).select_from(Load).where(*load_scope, Load.status.in_(ACTIVE_LOAD_STATUSES))) or 0
    outbound_ready = db.scalar(select(func.count()).select_from(OutboundOrder).where(*ob_scope, OutboundOrder.status.in_(READY_OUTBOUND_STATUSES))) or 0
    outbound_active = db.scalar(select(func.count()).select_from(OutboundOrder).where(*ob_scope, OutboundOrder.status.in_(ACTIVE_OUTBOUND_STATUSES))) or 0
    open_wo = db.scalar(select(func.count()).select_from(WorkOrder).where(*wo_scope, WorkOrder.status.in_(OPEN_WORK_ORDER_STATUSES))) or 0
    open_ex = db.scalar(select(func.count()).select_from(OperationalException).where(*ex_scope, OperationalException.status.in_(OPEN_EXCEPTION_STATUSES))) or 0
    critical = db.scalar(select(func.count()).select_from(OperationalException).where(*ex_scope, OperationalException.status.in_(OPEN_EXCEPTION_STATUSES), OperationalException.severity == ExceptionSeverity.CRITICAL)) or 0

    load_period = [*load_scope, Load.created_at >= start, Load.created_at < end]
    wo_period = [*wo_scope, WorkOrder.completed_at >= start, WorkOrder.completed_at < end]
    ex_resolved_period = [*ex_scope, OperationalException.status == ExceptionStatus.RESOLVED, OperationalException.resolved_at >= start, OperationalException.resolved_at < end]
    completed_wo = db.scalar(select(func.count()).select_from(WorkOrder).where(*wo_period)) or 0
    period_load_count = db.scalar(select(func.count()).select_from(Load).where(*load_period)) or 0
    outbound_count = db.scalar(select(func.count()).select_from(OutboundOrder).join(Load, OutboundOrder.load_id == Load.id).where(*load_period)) or 0

    if db.bind and db.bind.dialect.name == "sqlite":
        duration_hours = (func.julianday(OperationalException.resolved_at) - func.julianday(OperationalException.reported_at)) * 24
    else:
        duration_hours = func.extract("epoch", OperationalException.resolved_at - OperationalException.reported_at) / 3600
    avg_resolution = db.scalar(select(func.avg(duration_hours)).select_from(OperationalException).where(*ex_resolved_period))

    wo_open = [*wo_scope, WorkOrder.status.in_(OPEN_WORK_ORDER_STATUSES)]
    ex_open = [*ex_scope, OperationalException.status.in_(OPEN_EXCEPTION_STATUSES)]
    wo_status = _group_counts(db, WorkOrder.status, *wo_scope)
    wo_priority = _group_counts(db, WorkOrder.priority, *wo_open)
    ex_status = _group_counts(db, OperationalException.status, *ex_scope)
    ex_severity = _group_counts(db, OperationalException.severity, *ex_open)
    ex_types = _group_counts(db, OperationalException.exception_type, *ex_open)
    overdue = db.scalar(select(func.count()).select_from(WorkOrder).where(*wo_open, WorkOrder.scheduled_at.is_not(None), WorkOrder.scheduled_at < now)) or 0

    # Pre-aggregate each fact table before joining so warehouse totals do not create
    # a work-order x exception row multiplication for busy facilities.
    wo_by_warehouse = (
        select(WorkOrder.warehouse_id.label("warehouse_id"), func.count().label("open_work_orders"))
        .where(*wo_scope, WorkOrder.status.in_(OPEN_WORK_ORDER_STATUSES))
        .group_by(WorkOrder.warehouse_id)
        .subquery()
    )
    ex_by_warehouse = (
        select(OperationalException.warehouse_id.label("warehouse_id"), func.count().label("open_exceptions"))
        .where(*ex_scope, OperationalException.status.in_(OPEN_EXCEPTION_STATUSES))
        .group_by(OperationalException.warehouse_id)
        .subquery()
    )
    warehouse_rows = db.execute(
        select(
            Warehouse.id,
            Warehouse.warehouse_code,
            Warehouse.warehouse_name,
            func.coalesce(wo_by_warehouse.c.open_work_orders, 0),
            func.coalesce(ex_by_warehouse.c.open_exceptions, 0),
        )
        .outerjoin(wo_by_warehouse, wo_by_warehouse.c.warehouse_id == Warehouse.id)
        .outerjoin(ex_by_warehouse, ex_by_warehouse.c.warehouse_id == Warehouse.id)
        .where(*_filters(user, Warehouse.id, warehouse_id))
        .order_by(Warehouse.warehouse_code)
    ).all()

    wo_events = db.execute(select(WorkOrderEvent, WorkOrder.work_order_no).join(WorkOrder).where(*wo_scope).order_by(WorkOrderEvent.created_at.desc(), WorkOrderEvent.id.desc()).limit(10)).all()
    ex_events = db.execute(select(OperationalExceptionEvent, OperationalException.exception_no).join(OperationalException).where(*ex_scope).order_by(OperationalExceptionEvent.created_at.desc(), OperationalExceptionEvent.id.desc()).limit(10)).all()
    recent = ([{"kind": "WORK_ORDER", "entity_id": e.work_order_id, "reference": ref, "event_type": e.event_type, "message": e.message or e.note, "created_at": e.created_at} for e, ref in wo_events] +
              [{"kind": "EXCEPTION", "entity_id": e.operational_exception_id, "reference": ref, "event_type": e.event_type, "message": e.message, "created_at": e.created_at} for e, ref in ex_events])
    recent.sort(key=lambda item: item["created_at"], reverse=True)

    attention_ex = db.execute(select(OperationalException.id, OperationalException.exception_no, OperationalException.title, OperationalException.severity, OperationalException.reported_at).where(*ex_open, OperationalException.severity == ExceptionSeverity.CRITICAL).order_by(OperationalException.reported_at).limit(5)).all()
    attention_wo = db.execute(select(WorkOrder.id, WorkOrder.work_order_no, WorkOrder.priority, WorkOrder.status, WorkOrder.created_at).where(*wo_open, WorkOrder.priority == WorkOrderPriority.URGENT).order_by(WorkOrder.created_at).limit(5)).all()
    old_wo = db.execute(select(WorkOrder.id, WorkOrder.work_order_no, WorkOrder.priority, WorkOrder.status, WorkOrder.created_at).where(*wo_open, WorkOrder.created_at <= now - timedelta(hours=24)).order_by(WorkOrder.created_at).limit(5)).all()
    attention_candidates = ([{"kind":"EXCEPTION", "entity_id":r.id, "reference":r.exception_no, "label":r.title, "reason":"Critical open exception", "since":r.reported_at} for r in attention_ex] +
                            [{"kind":"WORK_ORDER", "entity_id":r.id, "reference":r.work_order_no, "label":r.status.value, "reason":"Urgent work order", "since":r.created_at} for r in attention_wo] +
                            [{"kind":"WORK_ORDER", "entity_id":r.id, "reference":r.work_order_no, "label":r.status.value, "reason":"Open longer than 24 hours", "since":r.created_at} for r in old_wo])
    attention = []
    seen_attention = set()
    for item in attention_candidates:
        key = (item["kind"], item["entity_id"])
        if key not in seen_attention:
            seen_attention.add(key)
            attention.append(item)
        if len(attention) == 12:
            break

    return {
        "meta": {"generated_at": now, "period_start": start, "period_end_exclusive": end, "warehouse_id": warehouse_id, "date_semantics": "Snapshot metrics ignore the date range; period metrics use [start, end)."},
        "summary": {"active_loads": active_loads, "outbound_ready": outbound_ready, "outbound_active": outbound_active, "open_work_orders": open_wo, "open_exceptions": open_ex, "critical_open_exceptions": critical, "completed_work_orders_period": completed_wo},
        "loads": {"created_period": period_load_count, "created_period_by_current_status": _group_counts(db, Load.status, *load_period), "active_snapshot": active_loads, "average_outbounds_per_period_load": round(outbound_count / period_load_count, 2) if period_load_count else None},
        "work_orders": {"status_snapshot": wo_status, "open_priority_snapshot": wo_priority, "completed_period": completed_wo, "overdue_snapshot": overdue, "aging_snapshot": dict(zip(("lt_4h","4_12h","12_24h","gt_24h"), _age_counts(db, WorkOrder, WorkOrder.created_at, now, (4,12,24), *wo_open)))},
        "exceptions": {"status_snapshot": ex_status, "open_severity_snapshot": ex_severity, "open_type_snapshot": ex_types, "resolved_period": db.scalar(select(func.count()).select_from(OperationalException).where(*ex_resolved_period)) or 0, "average_resolution_hours_period": round(float(avg_resolution), 2) if avg_resolution is not None else None, "aging_snapshot": dict(zip(("lt_4h","4_12h","12_24h","1_3d","gt_3d"), _age_counts(db, OperationalException, OperationalException.reported_at, now, (4,12,24,72), *ex_open)))},
        "execution_funnel": [{"stage": key, "count": wo_status.get(key, 0)} for key in ("OPEN","ASSIGNED","IN_PROGRESS","COMPLETED")],
        "warehouses": [{"warehouse_id":r[0], "warehouse_code":r[1], "warehouse_name":r[2], "open_work_orders":r[3], "open_exceptions":r[4]} for r in warehouse_rows],
        "attention": attention,
        "recent_activity": recent[:15],
    }
