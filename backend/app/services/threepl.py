from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.inbound import InboundRecord, InboundStatus
from app.models.inventory import InventoryLot
from app.models.outbound import OBStatus, OutboundInventoryAllocation, OutboundOrder
from app.models.user import User
from app.services.access_policy import scoped_statement


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
