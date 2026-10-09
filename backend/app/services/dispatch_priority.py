from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import case, func, select

from app.models import InventoryLot, OutboundInventoryAllocation, OutboundOrder, User
from app.models.outbound import OBStatus
from app.services.access_policy import customer_clause, warehouse_clause
from app.utils.business_time import get_business_today, to_business_date


class DispatchPriority(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    NORMAL = "NORMAL"


class DispatchReadiness(StrEnum):
    NOT_READY = "NOT_READY"
    READY = "READY"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"


ACTIVE_OUTBOUND_STATUSES = tuple(
    status.value for status in OBStatus if status not in (OBStatus.CANCELED, OBStatus.COMPLETED)
)
DISPATCH_PRIORITY_RANK = {
    DispatchPriority.CRITICAL: 0,
    DispatchPriority.HIGH: 1,
    DispatchPriority.MEDIUM: 2,
    DispatchPriority.NORMAL: 3,
}


def operational_date(value: date | datetime | None) -> date | None:
    """Return the configured warehouse business date for a date or timestamp."""
    return to_business_date(value)


def calculate_days_remaining(outbound_date: date | datetime | None, today: date | None = None) -> int | None:
    value = operational_date(outbound_date)
    return (value - (today or get_business_today())).days if value else None


def calculate_warehouse_days(inbound_date: date | None, today: date | None = None) -> int | None:
    return max(0, ((today or get_business_today()) - inbound_date).days) if inbound_date else None


def calculate_dispatch_priority(outbound_date: date | datetime | None, today: date | None = None) -> DispatchPriority:
    remaining = calculate_days_remaining(outbound_date, today)
    if remaining is None or remaining > 5:
        return DispatchPriority.NORMAL
    if remaining <= 0:
        return DispatchPriority.CRITICAL
    if remaining <= 2:
        return DispatchPriority.HIGH
    return DispatchPriority.MEDIUM


def calculate_dispatch_readiness(
    *, outbound_status: int | None, has_inventory: bool, has_allocation: bool,
    allocated_pallets: float = 0, completed_pallets: float = 0,
    available_inventory_pallets: float | None = None,
) -> DispatchReadiness:
    """Conservative readiness with terminal/exception states taking precedence."""
    if outbound_status == OBStatus.EXCEPTION:
        return DispatchReadiness.BLOCKED
    if outbound_status == OBStatus.COMPLETED or (has_allocation and allocated_pallets > 0 and completed_pallets >= allocated_pallets):
        return DispatchReadiness.COMPLETED
    if outbound_status == OBStatus.CANCELED or not has_inventory or not has_allocation or allocated_pallets <= 0:
        return DispatchReadiness.NOT_READY
    remaining = max(0, allocated_pallets - completed_pallets)
    if available_inventory_pallets is not None and available_inventory_pallets < remaining:
        return DispatchReadiness.NOT_READY
    if 0 < completed_pallets < allocated_pallets:
        return DispatchReadiness.PARTIAL
    return DispatchReadiness.READY


def container_dispatch_aggregate(user: User | None = None):
    """One grouped query for pending dispatch data by source container."""
    query = (
        select(
            InventoryLot.container_number.label("container_number"),
            func.min(OutboundOrder.schedule_pickup_at).label("earliest_outbound_at"),
            func.min(InventoryLot.inbound_date).label("inbound_date"),
            func.count(func.distinct(OutboundOrder.id)).label("outbound_task_count"),
            func.max(case((OutboundOrder.status == OBStatus.EXCEPTION, 1), else_=0)).label("has_exception"),
        )
        .join(OutboundInventoryAllocation, OutboundInventoryAllocation.inventory_lot_id == InventoryLot.id)
        .join(OutboundOrder, OutboundOrder.id == OutboundInventoryAllocation.outbound_order_id)
        .where(
            OutboundOrder.status.in_(ACTIVE_OUTBOUND_STATUSES),
            OutboundOrder.schedule_pickup_at.is_not(None),
            OutboundInventoryAllocation.allocated_pallet_qty > OutboundInventoryAllocation.completed_pallet_qty,
        )
    )
    if user is not None:
        for clause in (
            warehouse_clause(user, OutboundOrder.warehouse_id),
            customer_clause(user, OutboundOrder.customer_id),
            warehouse_clause(user, InventoryLot.warehouse_id),
            customer_clause(user, InventoryLot.customer_id),
        ):
            if clause is not None:
                query = query.where(clause)
    return query.group_by(InventoryLot.container_number).subquery("container_dispatch")


def dispatch_fields(earliest: date | datetime | None, inbound_date: date | None = None) -> dict:
    outbound_date = operational_date(earliest)
    priority = calculate_dispatch_priority(outbound_date)
    return {
        "inbound_date": inbound_date,
        "warehouse_days": calculate_warehouse_days(inbound_date),
        "earliest_outbound_date": outbound_date,
        "outbound_days_remaining": calculate_days_remaining(outbound_date),
        "dispatch_priority": priority.value,
        "dispatch_priority_rank": DISPATCH_PRIORITY_RANK[priority],
    }
