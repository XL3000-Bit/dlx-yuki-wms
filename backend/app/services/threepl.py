from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.customer import Customer
from app.models.bol import BOL, BOLStatus
from app.models.inbound import InboundRecord, InboundStatus
from app.models.inventory import InventoryLot
from app.models.outbound import OBStatus, OutboundInventoryAllocation, OutboundOrder
from app.models.operational_exception import ExceptionSeverity, ExceptionStatus, OperationalException
from app.models.picking import PickingList, PickingStatus
from app.models.user import User
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
) -> dict:
    statement = scoped_statement(
        select(OutboundOrder).options(
            joinedload(OutboundOrder.customer), joinedload(OutboundOrder.warehouse), joinedload(OutboundOrder.carrier),
        ),
        user,
        warehouse_column=OutboundOrder.warehouse_id,
        customer_column=OutboundOrder.customer_id,
    ).where(OutboundOrder.status.notin_((OBStatus.COMPLETED, OBStatus.CANCELED)))
    if customer_id is not None:
        statement = statement.where(OutboundOrder.customer_id == customer_id)
    if warehouse_id is not None:
        statement = statement.where(OutboundOrder.warehouse_id == warehouse_id)
    outbounds = list(db.scalars(statement).unique().all())
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

    now = get_business_now()
    soon = now + timedelta(hours=24)
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

        derived_priority = "URGENT" if blocked or is_overdue else "HIGH" if business_due_at and business_due_at <= soon else "NORMAL"
        work_order_priority = primary_work_order.priority.value if primary_work_order else "LOW"
        priority = min((derived_priority, work_order_priority), key=lambda value: _PRIORITY_RANK[value])
        blocker = None
        if primary_exception:
            blocker = primary_exception.title
        elif outbound.exception_reason:
            blocker = outbound.exception_reason
        elif is_overdue:
            blocker = "Scheduled time has passed"
        elif due_soon_unassigned:
            blocker = "Execution owner not assigned"
        elif missing_carrier:
            blocker = "Carrier not assigned"
        elif missing_documents:
            blocker = "Picking list and BOL not issued" if not picking and not bol else "BOL not issued" if not bol else "Picking list not issued"

        if primary_exception:
            action_target = f"/trouble-shoot?selected={primary_exception.id}"
        elif primary_work_order:
            action_target = f"/work-orders?selected={primary_work_order.id}"
        else:
            action_target = f"/outbound/dispatch?selected_ob={outbound.id}"
        tasks.append({
            "id": outbound.id, "reference": outbound.ob_no,
            "customer_id": outbound.customer_id,
            "customer_code": outbound.customer.customer_code if outbound.customer else "UNASSIGNED",
            "customer_name": outbound.customer.customer_name if outbound.customer else "Unassigned client",
            "warehouse_id": outbound.warehouse_id,
            "warehouse_code": outbound.warehouse.warehouse_code,
            "status": int(outbound.status), "status_name": _STATUS_NAMES[OBStatus(outbound.status)],
            "priority": priority, "queue_state": queue_state, "due_at": business_due_at,
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
            "blocker": blocker, "carrier_name": outbound.carrier.carrier_name if outbound.carrier else None,
            "action_target": action_target,
        })

    tasks.sort(key=lambda item: (
        {"BLOCKED": 0, "AT_RISK": 1, "READY": 2}[item["queue_state"]],
        _PRIORITY_RANK[item["priority"]], _timestamp(item["due_at"]), item["reference"],
    ))
    return {
        "generated_at": now,
        "summary": {
            "total": len(tasks),
            "ready": sum(item["queue_state"] == "READY" for item in tasks),
            "at_risk": sum(item["queue_state"] == "AT_RISK" for item in tasks),
            "blocked": sum(item["queue_state"] == "BLOCKED" for item in tasks),
            "overdue": sum(item["is_overdue"] for item in tasks),
            "unassigned": sum(not item["owner_name"] for item in tasks),
        },
        "tasks": tasks,
    }
