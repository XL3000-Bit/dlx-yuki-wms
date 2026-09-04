from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.customer import Customer
from app.models.bol import BOL, BOLStatus
from app.models.inbound import InboundRecord, InboundStatus
from app.models.inventory import InventoryLot
from app.models.outbound import OBStatus, OutboundInventoryAllocation, OutboundOrder
from app.models.operational_exception import ExceptionSeverity, ExceptionStatus, OperationalException
from app.models.picking import PickingList, PickingStatus
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.work_order import WorkOrder, WorkOrderPriority, WorkOrderStatus
from app.services.access_policy import scoped_statement
from app.utils.business_time import get_business_now, to_business_datetime


def _number(value: Decimal | int | float | None) -> float:
    return round(float(value or 0), 4)


def _within(value: date | datetime | None, first: date, last: date) -> bool:
    if value is None:
        return False
    day = value.date() if isinstance(value, datetime) else value
    return first <= day <= last


def build_threepl_overview(
    db: Session,
    user: User,
    first: date,
    last: date,
    customer_id: int | None,
    warehouse_id: int | None,
) -> dict:
    customer_stmt = scoped_statement(select(Customer), user, customer_column=Customer.id)
    if customer_id is not None:
        customer_stmt = customer_stmt.where(Customer.id == customer_id)
    customers = list(db.scalars(customer_stmt.order_by(Customer.customer_code)).all())
    customer_map = {item.id: item for item in customers}
    stats: dict[int, dict] = defaultdict(lambda: {
        "inventory_pallets": 0.0, "inventory_cartons": 0.0, "inventory_cbm": 0.0,
        "hold_pallets": 0.0, "open_inbounds": 0, "open_outbounds": 0,
        "completed_inbounds": 0, "completed_outbounds": 0,
        "oldest_inventory_days": None, "last_activity_at": None,
    })

    inventory_stmt = scoped_statement(
        select(InventoryLot), user,
        warehouse_column=InventoryLot.warehouse_id, customer_column=InventoryLot.customer_id,
    )
    inbound_stmt = scoped_statement(
        select(InboundRecord), user,
        warehouse_column=InboundRecord.warehouse_id, customer_column=InboundRecord.customer_id,
    )
    outbound_stmt = scoped_statement(
        select(OutboundOrder), user,
        warehouse_column=OutboundOrder.warehouse_id, customer_column=OutboundOrder.customer_id,
    )
    for statement, model in ((inventory_stmt, InventoryLot), (inbound_stmt, InboundRecord), (outbound_stmt, OutboundOrder)):
        if customer_id is not None:
            statement = statement.where(model.customer_id == customer_id)
        if warehouse_id is not None:
            statement = statement.where(model.warehouse_id == warehouse_id)
        if model is InventoryLot:
            inventory_stmt = statement
        elif model is InboundRecord:
            inbound_stmt = statement
        else:
            outbound_stmt = statement

    inventory = list(db.scalars(inventory_stmt).all())
    inbounds = list(db.scalars(inbound_stmt).all())
    outbounds = list(db.scalars(outbound_stmt).all())
    today = datetime.now(timezone.utc).date()

    for lot in inventory:
        if lot.customer_id not in customer_map:
            continue
        row = stats[lot.customer_id]
        row["inventory_pallets"] += _number(lot.available_pallet_qty) + _number(lot.allocated_pallet_qty) + _number(lot.hold_pallet_qty)
        row["inventory_cartons"] += _number(lot.available_carton_qty) + _number(lot.allocated_carton_qty) + _number(lot.hold_carton_qty)
        row["inventory_cbm"] += _number(lot.available_cbm) + _number(lot.allocated_cbm)
        row["hold_pallets"] += _number(lot.hold_pallet_qty)
        if lot.inbound_date:
            age = max((today - lot.inbound_date).days, 0)
            row["oldest_inventory_days"] = max(row["oldest_inventory_days"] or 0, age)
        row["last_activity_at"] = max(filter(None, [row["last_activity_at"], lot.updated_at]), default=None)

    receiving_orders = receiving_pallets = receiving_cartons = 0
    for item in inbounds:
        if item.customer_id not in customer_map:
            continue
        row = stats[item.customer_id]
        if item.status != InboundStatus.COMPLETED:
            row["open_inbounds"] += 1
        if item.status == InboundStatus.COMPLETED and _within(item.received_date, first, last):
            row["completed_inbounds"] += 1
            receiving_orders += 1
            receiving_pallets += _number(item.pallet_qty)
            receiving_cartons += _number(item.carton_qty)
        row["last_activity_at"] = max(filter(None, [row["last_activity_at"], item.updated_at]), default=None)

    period_outbound_ids: set[int] = set()
    for item in outbounds:
        if item.customer_id not in customer_map:
            continue
        row = stats[item.customer_id]
        if item.status not in (OBStatus.COMPLETED, OBStatus.CANCELED):
            row["open_outbounds"] += 1
        if item.status == OBStatus.COMPLETED and _within(item.completed_at or item.actual_outbound_time, first, last):
            row["completed_outbounds"] += 1
            period_outbound_ids.add(item.id)
        row["last_activity_at"] = max(filter(None, [row["last_activity_at"], item.updated_at]), default=None)

    outbound_pallets = outbound_cartons = 0.0
    if period_outbound_ids:
        allocations = db.scalars(select(OutboundInventoryAllocation).where(OutboundInventoryAllocation.outbound_order_id.in_(period_outbound_ids))).all()
        for allocation in allocations:
            outbound_pallets += _number(allocation.completed_pallet_qty)
            outbound_cartons += _number(allocation.completed_carton_qty)

    client_rows = []
    attention = []
    for customer in customers:
        row = stats[customer.id]
        client_rows.append({
            "customer_id": customer.id, "customer_code": customer.customer_code,
            "customer_name": customer.customer_name, "contact_name": customer.contact_name,
            "email": customer.email, "is_active": customer.is_active, **row,
        })
        if row["hold_pallets"] > 0:
            attention.append({"severity": "HIGH", "customer_id": customer.id, "customer_code": customer.customer_code,
                              "title": "Inventory on hold", "detail": f'{row["hold_pallets"]:,.2f} pallets require review', "target": "/inventory"})
        if row["oldest_inventory_days"] is not None and row["oldest_inventory_days"] >= 30:
            attention.append({"severity": "MEDIUM", "customer_id": customer.id, "customer_code": customer.customer_code,
                              "title": "Aging inventory", "detail": f'Oldest inventory is {row["oldest_inventory_days"]} days old', "target": "/inventory"})
        if customer.is_active and not customer.email:
            attention.append({"severity": "LOW", "customer_id": customer.id, "customer_code": customer.customer_code,
                              "title": "Missing billing contact", "detail": "Add an email before issuing client statements", "target": "/settings/customers"})

    days = (last - first).days + 1
    inventory_pallets = sum(row["inventory_pallets"] for row in stats.values())
    summary = {
        "active_clients": sum(1 for item in customers if item.is_active),
        "inventory_pallets": inventory_pallets,
        "inventory_cartons": sum(row["inventory_cartons"] for row in stats.values()),
        "inventory_cbm": sum(row["inventory_cbm"] for row in stats.values()),
        "hold_pallets": sum(row["hold_pallets"] for row in stats.values()),
        "open_inbounds": sum(row["open_inbounds"] for row in stats.values()),
        "open_outbounds": sum(row["open_outbounds"] for row in stats.values()),
    }
    return {
        "meta": {"generated_at": datetime.now(timezone.utc), "date_from": first, "date_to": last,
                 "customer_id": customer_id, "warehouse_id": warehouse_id,
                 "storage_basis": "Current pallet snapshot multiplied by selected calendar days; not a historical daily balance."},
        "summary": summary,
        "usage": {"receiving_orders": receiving_orders, "receiving_pallets": receiving_pallets,
                  "receiving_cartons": receiving_cartons, "outbound_orders": len(period_outbound_ids),
                  "outbound_pallets": outbound_pallets, "outbound_cartons": outbound_cartons,
                  "storage_pallet_days": round(inventory_pallets * days, 2)},
        "clients": sorted(client_rows, key=lambda row: (-row["inventory_pallets"], row["customer_code"])),
        "attention": sorted(attention, key=lambda item: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[item["severity"]]),
    }


_STATUS_NAMES = {
    OBStatus.NEW: "New", OBStatus.HOLD: "On hold", OBStatus.IN_PROGRESS: "In progress",
    OBStatus.CONFIRMED: "Confirmed", OBStatus.DISPATCHED: "Dispatched",
    OBStatus.COMPLETED: "Completed", OBStatus.CANCELED: "Canceled", OBStatus.EXCEPTION: "Exception",
}
_PRIORITY_RANK = {"URGENT": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3}
_EXCEPTION_RANK = {ExceptionSeverity.CRITICAL: 0, ExceptionSeverity.HIGH: 1,
                   ExceptionSeverity.MEDIUM: 2, ExceptionSeverity.LOW: 3}
_PICKING_STATUS_NAMES = {
    PickingStatus.NEW: "New", PickingStatus.PRINTED: "Printed",
    PickingStatus.IN_PROGRESS: "In Progress", PickingStatus.COMPLETED: "Completed",
    PickingStatus.CANCELED: "Canceled", PickingStatus.EXCEPTION: "Exception",
}
_BOL_STATUS_NAMES = {
    BOLStatus.DRAFT: "Draft", BOLStatus.GENERATED: "Generated",
    BOLStatus.PRINTED: "Printed", BOLStatus.COMPLETED: "Completed",
    BOLStatus.CANCELED: "Canceled",
}


def _timestamp(value: datetime | None) -> float:
    converted = to_business_datetime(value)
    return converted.timestamp() if converted else float("inf")


def build_threepl_dispatch_queue(
    db: Session,
    user: User,
    customer_id: int | None,
    warehouse_id: int | None,
    *,
    status: int | None = None,
    readiness: str | None = None,
    blocker: str | None = None,
    priority: str | None = None,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "queue",
) -> dict:
    now = get_business_now()
    soon = now + timedelta(hours=24)
    active_work_order = WorkOrder.status.notin_((WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELED))
    active_exception = OperationalException.status.notin_((ExceptionStatus.RESOLVED, ExceptionStatus.CANCELED))
    work_priority_rank = case(
        (WorkOrder.priority == WorkOrderPriority.URGENT, 0),
        (WorkOrder.priority == WorkOrderPriority.HIGH, 1),
        (WorkOrder.priority == WorkOrderPriority.NORMAL, 2),
        else_=3,
    )
    work_null_due_rank = case((WorkOrder.scheduled_at.is_(None), 1), else_=0)
    primary_work_order_id = select(WorkOrder.id).where(
        WorkOrder.outbound_id == OutboundOrder.id, active_work_order,
    ).order_by(work_priority_rank, work_null_due_rank, WorkOrder.scheduled_at, WorkOrder.id).limit(1).correlate(OutboundOrder).scalar_subquery()
    primary_work_due = select(WorkOrder.scheduled_at).where(
        WorkOrder.id == primary_work_order_id,
    ).correlate(OutboundOrder).scalar_subquery()
    primary_work_priority = select(WorkOrder.priority).where(
        WorkOrder.id == primary_work_order_id,
    ).correlate(OutboundOrder).scalar_subquery()
    primary_work_has_owner = select(WorkOrder.id).where(
        WorkOrder.id == primary_work_order_id,
        or_(WorkOrder.assigned_to.is_not(None), func.trim(func.coalesce(WorkOrder.assigned_team, "")) != ""),
    ).correlate(OutboundOrder).exists()

    exception_rank = case(
        (OperationalException.severity == ExceptionSeverity.CRITICAL, 0),
        (OperationalException.severity == ExceptionSeverity.HIGH, 1),
        (OperationalException.severity == ExceptionSeverity.MEDIUM, 2),
        else_=3,
    )
    primary_exception_id = select(OperationalException.id).where(
        OperationalException.outbound_id == OutboundOrder.id, active_exception,
    ).order_by(exception_rank, OperationalException.reported_at, OperationalException.id).limit(1).correlate(OutboundOrder).scalar_subquery()
    has_picking = select(PickingList.id).where(
        PickingList.outbound_order_id == OutboundOrder.id,
        PickingList.status != PickingStatus.CANCELED,
    ).correlate(OutboundOrder).exists()
    has_bol = select(BOL.id).where(
        BOL.outbound_order_id == OutboundOrder.id,
        BOL.status != BOLStatus.CANCELED,
    ).correlate(OutboundOrder).exists()

    def _earliest(left, right):
        return case(
            (left.is_(None), right),
            (right.is_(None), left),
            (left <= right, left),
            else_=right,
        )

    due_at = _earliest(_earliest(primary_work_due, OutboundOrder.schedule_pickup_at), OutboundOrder.delivery_appointment_time)
    owner_present = or_(
        func.trim(func.coalesce(OutboundOrder.loading_team, "")) != "",
        primary_work_has_owner,
    )
    owner_missing = ~owner_present
    is_overdue = and_(due_at.is_not(None), due_at < now)
    is_due_soon = and_(due_at.is_not(None), due_at <= soon)
    is_blocked = or_(
        OutboundOrder.status.in_((OBStatus.HOLD, OBStatus.EXCEPTION)),
        primary_exception_id.is_not(None),
    )
    missing_carrier = and_(
        OutboundOrder.carrier_id.is_(None),
        OutboundOrder.status.in_((OBStatus.CONFIRMED, OBStatus.DISPATCHED)),
    )
    missing_documents = and_(
        OutboundOrder.status == OBStatus.CONFIRMED,
        or_(~has_picking, ~has_bol),
    )
    due_soon_unassigned = and_(is_due_soon, owner_missing)
    queue_state = case(
        (is_blocked, "BLOCKED"),
        (or_(is_overdue, missing_carrier, missing_documents, due_soon_unassigned), "AT_RISK"),
        else_="READY",
    )
    blocker_code = case(
        (primary_exception_id.is_not(None), "ACTIVE_EXCEPTION"),
        (func.trim(func.coalesce(OutboundOrder.exception_reason, "")) != "", "OUTBOUND_EXCEPTION"),
        (OutboundOrder.status == OBStatus.HOLD, "OUTBOUND_HOLD"),
        (is_overdue, "OVERDUE"),
        (due_soon_unassigned, "OWNER_UNASSIGNED"),
        (missing_carrier, "CARRIER_MISSING"),
        (and_(missing_documents, ~has_picking, ~has_bol), "DOCUMENTS_MISSING"),
        (and_(missing_documents, ~has_bol), "BOL_MISSING"),
        (missing_documents, "PICKING_MISSING"),
    )
    priority_rank = case(
        (or_(is_blocked, is_overdue, primary_work_priority == WorkOrderPriority.URGENT), 0),
        (or_(is_due_soon, primary_work_priority == WorkOrderPriority.HIGH), 1),
        (or_(primary_work_priority == WorkOrderPriority.NORMAL, due_at.is_not(None)), 2),
        else_=3,
    )
    priority_name = case(
        (priority_rank == 0, "URGENT"),
        (priority_rank == 1, "HIGH"),
        (priority_rank == 2, "NORMAL"),
        else_="LOW",
    )

    source = scoped_statement(
        select(
            OutboundOrder.id.label("id"), OutboundOrder.ob_no.label("reference"),
            due_at.label("due_at"), queue_state.label("queue_state"),
            blocker_code.label("blocker_code"), priority_rank.label("priority_rank"),
            priority_name.label("priority"), is_overdue.label("is_overdue"),
            owner_missing.label("owner_missing"), OutboundOrder.updated_at.label("updated_at"),
        ),
        user,
        warehouse_column=OutboundOrder.warehouse_id,
        customer_column=OutboundOrder.customer_id,
    ).where(OutboundOrder.status.notin_((OBStatus.COMPLETED, OBStatus.CANCELED)))
    if customer_id is not None:
        source = source.where(OutboundOrder.customer_id == customer_id)
    if warehouse_id is not None:
        source = source.where(OutboundOrder.warehouse_id == warehouse_id)
    if status is not None:
        source = source.where(OutboundOrder.status == status)
    needle = (search or "").strip().lower()
    if needle:
        escaped_needle = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped_needle}%"
        source = source.where(or_(
            func.lower(OutboundOrder.ob_no).like(pattern, escape="\\"),
            func.lower(func.coalesce(OutboundOrder.reference_no, "")).like(pattern, escape="\\"),
            select(Customer.id).where(
                Customer.id == OutboundOrder.customer_id,
                or_(func.lower(Customer.customer_code).like(pattern, escape="\\"), func.lower(Customer.customer_name).like(pattern, escape="\\")),
            ).correlate(OutboundOrder).exists(),
            select(Warehouse.id).where(
                Warehouse.id == OutboundOrder.warehouse_id,
                func.lower(Warehouse.warehouse_code).like(pattern, escape="\\"),
            ).correlate(OutboundOrder).exists(),
            select(WorkOrder.id).where(
                WorkOrder.outbound_id == OutboundOrder.id, active_work_order,
                or_(func.lower(WorkOrder.work_order_no).like(pattern, escape="\\"), func.lower(func.coalesce(WorkOrder.assigned_team, "")).like(pattern, escape="\\")),
            ).correlate(OutboundOrder).exists(),
            select(OperationalException.id).where(
                OperationalException.outbound_id == OutboundOrder.id, active_exception,
                or_(func.lower(OperationalException.exception_no).like(pattern, escape="\\"), func.lower(OperationalException.title).like(pattern, escape="\\")),
            ).correlate(OutboundOrder).exists(),
            select(PickingList.id).where(
                PickingList.outbound_order_id == OutboundOrder.id,
                PickingList.status != PickingStatus.CANCELED,
                func.lower(PickingList.picking_no).like(pattern, escape="\\"),
            ).correlate(OutboundOrder).exists(),
            select(BOL.id).where(
                BOL.outbound_order_id == OutboundOrder.id,
                BOL.status != BOLStatus.CANCELED,
                func.lower(BOL.bol_no).like(pattern, escape="\\"),
            ).correlate(OutboundOrder).exists(),
        ))
    derived = source.cte("threepl_dispatch_derived")
    filtered = select(derived)
    if readiness is not None:
        filtered = filtered.where(derived.c.queue_state == readiness)
    if blocker is not None:
        filtered = filtered.where(derived.c.blocker_code == blocker)
    if priority is not None:
        filtered = filtered.where(derived.c.priority == priority)
    if date_from is not None:
        filtered = filtered.where(func.date(derived.c.due_at) >= date_from)
    if date_to is not None:
        filtered = filtered.where(func.date(derived.c.due_at) <= date_to)
    filtered = filtered.cte("threepl_dispatch_filtered")

    summary_row = db.execute(select(
        func.count().label("total"),
        func.coalesce(func.sum(case((filtered.c.queue_state == "READY", 1), else_=0)), 0).label("ready"),
        func.coalesce(func.sum(case((filtered.c.queue_state == "AT_RISK", 1), else_=0)), 0).label("at_risk"),
        func.coalesce(func.sum(case((filtered.c.queue_state == "BLOCKED", 1), else_=0)), 0).label("blocked"),
        func.coalesce(func.sum(case((filtered.c.is_overdue, 1), else_=0)), 0).label("overdue"),
        func.coalesce(func.sum(case((filtered.c.owner_missing, 1), else_=0)), 0).label("unassigned"),
    )).one()
    total = int(summary_row.total)
    orderings = {
        "queue": (case((filtered.c.queue_state == "BLOCKED", 0), (filtered.c.queue_state == "AT_RISK", 1), else_=2), filtered.c.priority_rank, case((filtered.c.due_at.is_(None), 1), else_=0), filtered.c.due_at, filtered.c.id),
        "priority": (filtered.c.priority_rank, case((filtered.c.due_at.is_(None), 1), else_=0), filtered.c.due_at, filtered.c.id),
        "due_at": (case((filtered.c.due_at.is_(None), 1), else_=0), filtered.c.due_at, filtered.c.priority_rank, filtered.c.id),
        "updated_at": (filtered.c.updated_at.desc(), filtered.c.id),
        "reference": (func.lower(filtered.c.reference), filtered.c.id),
    }
    id_rows = db.execute(
        select(filtered.c.id).order_by(*orderings[sort]).offset((page - 1) * page_size).limit(page_size)
    ).all()
    outbound_ids = [row.id for row in id_rows]
    outbounds_by_id = {
        item.id: item for item in db.scalars(
            select(OutboundOrder).options(
                joinedload(OutboundOrder.customer), joinedload(OutboundOrder.warehouse), joinedload(OutboundOrder.carrier),
            ).where(OutboundOrder.id.in_(outbound_ids))
        ).unique().all()
    }
    outbounds = [outbounds_by_id[item_id] for item_id in outbound_ids]
    outbound_ids = [item.id for item in outbounds]

    work_orders_by_outbound: dict[int, list[WorkOrder]] = defaultdict(list)
    exceptions_by_outbound: dict[int, list[OperationalException]] = defaultdict(list)
    pickings_by_outbound: dict[int, PickingList] = {}
    bols_by_outbound: dict[int, BOL] = {}
    if outbound_ids:
        work_orders = db.scalars(
            select(WorkOrder).options(joinedload(WorkOrder.assignee)).where(
                WorkOrder.outbound_id.in_(outbound_ids),
                WorkOrder.status.notin_((WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELED)),
            )
        ).all()
        for item in work_orders:
            if item.outbound_id is not None:
                work_orders_by_outbound[item.outbound_id].append(item)
        exceptions = db.scalars(
            select(OperationalException).options(joinedload(OperationalException.assignee)).where(
                OperationalException.outbound_id.in_(outbound_ids),
                OperationalException.status.notin_((ExceptionStatus.RESOLVED, ExceptionStatus.CANCELED)),
            )
        ).all()
        for item in exceptions:
            if item.outbound_id is not None:
                exceptions_by_outbound[item.outbound_id].append(item)
        pickings = db.scalars(
            select(PickingList).where(
                PickingList.outbound_order_id.in_(outbound_ids),
                PickingList.status != PickingStatus.CANCELED,
            ).order_by(PickingList.id.desc())
        ).all()
        for item in pickings:
            pickings_by_outbound.setdefault(item.outbound_order_id, item)
        bols = db.scalars(
            select(BOL).where(
                BOL.outbound_order_id.in_(outbound_ids),
                BOL.status != BOLStatus.CANCELED,
            ).order_by(BOL.id.desc())
        ).all()
        for item in bols:
            bols_by_outbound.setdefault(item.outbound_order_id, item)

    tasks = []
    for outbound in outbounds:
        primary_work_order = min(
            work_orders_by_outbound[outbound.id],
            key=lambda item: (_PRIORITY_RANK[item.priority.value], _timestamp(item.scheduled_at), item.id),
            default=None,
        )
        primary_exception = min(
            exceptions_by_outbound[outbound.id],
            key=lambda item: (_EXCEPTION_RANK[item.severity], _timestamp(item.reported_at), item.id),
            default=None,
        )
        due_candidates = [
            value for value in (
                primary_work_order.scheduled_at if primary_work_order else None,
                outbound.schedule_pickup_at,
                outbound.delivery_appointment_time,
            ) if value is not None
        ]
        due_at = min(due_candidates, key=_timestamp, default=None)
        business_due_at = to_business_datetime(due_at)
        is_overdue = bool(business_due_at and business_due_at < now)

        owner_name = None
        if primary_work_order:
            if primary_work_order.assignee:
                owner_name = primary_work_order.assignee.display_name
            else:
                owner_name = primary_work_order.assigned_team
        owner_name = owner_name or outbound.loading_team

        picking = pickings_by_outbound.get(outbound.id)
        bol = bols_by_outbound.get(outbound.id)
        document_state = "READY" if picking and bol else "PARTIAL" if picking or bol else "MISSING"
        missing_documents = outbound.status == OBStatus.CONFIRMED and document_state != "READY"
        blocked = outbound.status in (OBStatus.HOLD, OBStatus.EXCEPTION) or primary_exception is not None
        missing_carrier = outbound.carrier_id is None and outbound.status in (OBStatus.CONFIRMED, OBStatus.DISPATCHED)
        due_soon_unassigned = bool(business_due_at and business_due_at <= soon and not owner_name)
        if blocked:
            queue_state = "BLOCKED"
        elif is_overdue or missing_carrier or missing_documents or due_soon_unassigned:
            queue_state = "AT_RISK"
        else:
            queue_state = "READY"

        derived_priority = (
            "URGENT" if blocked or is_overdue
            else "HIGH" if business_due_at and business_due_at <= soon
            else "NORMAL" if business_due_at
            else "LOW"
        )
        work_order_priority = primary_work_order.priority.value if primary_work_order else "LOW"
        priority = min((derived_priority, work_order_priority), key=lambda value: _PRIORITY_RANK[value])
        blocker_code = None
        blocker_label = None
        blocker_detail = None
        if primary_exception:
            blocker_code = "ACTIVE_EXCEPTION"
            blocker_label = "Active exception"
            blocker_detail = primary_exception.title
        elif outbound.exception_reason:
            blocker_code = "OUTBOUND_EXCEPTION"
            blocker_label = "Outbound exception"
            blocker_detail = outbound.exception_reason
        elif outbound.status == OBStatus.HOLD:
            blocker_code = "OUTBOUND_HOLD"
            blocker_label = "Outbound on hold"
            blocker_detail = "Outbound order is on hold"
        elif is_overdue:
            blocker_code = "OVERDUE"
            blocker_label = "Overdue"
            blocker_detail = "Scheduled time has passed"
        elif due_soon_unassigned:
            blocker_code = "OWNER_UNASSIGNED"
            blocker_label = "Owner missing"
            blocker_detail = "Execution owner not assigned"
        elif missing_carrier:
            blocker_code = "CARRIER_MISSING"
            blocker_label = "Carrier missing"
            blocker_detail = "Carrier not assigned"
        elif missing_documents:
            blocker_code = "DOCUMENTS_MISSING" if not picking and not bol else "BOL_MISSING" if not bol else "PICKING_MISSING"
            blocker_label = "Documents missing" if not picking and not bol else "BOL missing" if not bol else "Picking list missing"
            blocker_detail = "Picking list and BOL not issued" if not picking and not bol else "BOL not issued" if not bol else "Picking list not issued"

        if primary_exception:
            action_target = f"/trouble-shoot?selected={primary_exception.id}"
        elif primary_work_order:
            action_target = f"/work-orders?selected={primary_work_order.id}"
        else:
            action_target = f"/outbound/dispatch?selected_ob={outbound.id}"
        internal_action = action_target.startswith("/") and not action_target.startswith("//")
        action_allowed = internal_action and not blocked
        if blocked:
            action_disabled_reason = blocker_detail or "Resolve this dispatch blocker before continuing"
        elif internal_action:
            action_disabled_reason = None
        else:
            action_disabled_reason = "No authorized internal destination is available"
        updated_at = max(
            (value for value in (
                outbound.updated_at,
                primary_work_order.updated_at if primary_work_order else None,
                primary_exception.updated_at if primary_exception else None,
                picking.updated_at if picking else None,
                bol.updated_at if bol else None,
            ) if value is not None),
            default=outbound.created_at,
        )
        if priority == "URGENT":
            priority_reason = blocker_label or "Scheduled time has passed"
        elif priority == "HIGH":
            priority_reason = "Due within 24 hours" if business_due_at and business_due_at <= soon else "High-priority work order"
        elif priority == "NORMAL":
            priority_reason = "Normal dispatch sequence"
        else:
            priority_reason = "No scheduled urgency"
        tasks.append({
            "id": outbound.id, "reference": outbound.ob_no,
            "customer_id": outbound.customer_id,
            "customer_code": outbound.customer.customer_code if outbound.customer else "UNASSIGNED",
            "customer_name": outbound.customer.customer_name if outbound.customer else "Unassigned client",
            "warehouse_id": outbound.warehouse_id,
            "warehouse_code": outbound.warehouse.warehouse_code,
            "status": int(outbound.status), "status_name": _STATUS_NAMES[OBStatus(outbound.status)],
            "priority": priority, "priority_reason": priority_reason,
            "queue_state": queue_state, "due_at": business_due_at,
            "is_overdue": is_overdue, "owner_name": owner_name,
            "work_order_id": primary_work_order.id if primary_work_order else None,
            "work_order_no": primary_work_order.work_order_no if primary_work_order else None,
            "work_order_type": primary_work_order.work_order_type.value if primary_work_order else None,
            "exception_id": primary_exception.id if primary_exception else None,
            "exception_no": primary_exception.exception_no if primary_exception else None,
            "exception_severity": primary_exception.severity.value if primary_exception else None,
            "picking_id": picking.id if picking else None,
            "picking_no": picking.picking_no if picking else None,
            "picking_status": int(picking.status) if picking else None,
            "picking_status_name": _PICKING_STATUS_NAMES[int(picking.status)] if picking else None,
            "bol_id": bol.id if bol else None,
            "bol_no": bol.bol_no if bol else None,
            "bol_status": int(bol.status) if bol else None,
            "bol_status_name": _BOL_STATUS_NAMES[int(bol.status)] if bol else None,
            "document_state": document_state,
            "blocker_code": blocker_code, "blocker_label": blocker_label,
            "blocker": blocker_detail, "carrier_name": outbound.carrier.carrier_name if outbound.carrier else None,
            "action_target": action_target, "action_allowed": action_allowed,
            "action_disabled_reason": action_disabled_reason,
            "picking_download_url": f"/picking-lists/{picking.id}/xlsx" if picking else None,
            "bol_download_url": f"/bols/{bol.id}/pdf" if bol else None,
            "updated_at": updated_at,
        })

    summary = {
        "total": total, "ready": int(summary_row.ready), "at_risk": int(summary_row.at_risk),
        "blocked": int(summary_row.blocked), "overdue": int(summary_row.overdue),
        "unassigned": int(summary_row.unassigned),
    }
    return {
        "generated_at": now,
        "summary_scope": "FILTERED_RESULT", "summary": summary,
        "page": page, "page_size": page_size, "total": total,
        "pages": (total + page_size - 1) // page_size,
        "sort": sort, "tasks": tasks,
    }
