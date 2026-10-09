from datetime import date
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import joinedload, selectinload
from app.models import Carrier, ExceptionStatus, Load, LoadStatus, OperationalException, OutboundOrder, Warehouse, WorkOrder
from app.models.outbound import OBStatus
from app.services.operational_notification import sync_load_notification
from app.services.outbound import totals
from app.services.load_dispatch_write import mutable, validate_business, latest_plan
from app.services.access_policy import customer_clause, warehouse_clause
from app.models.load_dispatch import LoadAllocation

TRANSITIONS = {LoadStatus.PLANNED: {LoadStatus.READY, LoadStatus.CANCELED}, LoadStatus.READY: {LoadStatus.DISPATCHED, LoadStatus.CANCELED}, LoadStatus.DISPATCHED: {LoadStatus.COMPLETED}, LoadStatus.COMPLETED: set(), LoadStatus.CANCELED: set()}

def generate_load_no(db, today: date | None = None) -> str:
    day = today or date.today(); prefix = f"LD-{day:%Y%m%d}-"
    if db.bind.dialect.name == "postgresql": db.execute(text("SELECT pg_advisory_xact_lock(107005)"))
    last = db.scalar(select(func.max(Load.load_no)).where(Load.load_no.like(f"{prefix}%")))
    return f"{prefix}{(int(last[-4:]) + 1 if last else 1):04d}"

def load_query():
    return select(Load).options(joinedload(Load.warehouse), joinedload(Load.carrier), selectinload(Load.outbounds).joinedload(OutboundOrder.customer), selectinload(Load.outbounds).selectinload(OutboundOrder.allocations), selectinload(Load.work_orders).joinedload(WorkOrder.assignee), selectinload(Load.operational_exceptions))

def _validate_outbounds(db, warehouse_id, ids, load_id=None, user=None):
    if len(ids) != len(set(ids)): raise HTTPException(422, "Duplicate outbound IDs")
    orders = list(db.scalars(select(OutboundOrder).where(OutboundOrder.id.in_(ids)).order_by(OutboundOrder.id).with_for_update().execution_options(populate_existing=True))) if ids else []
    if len(orders) != len(ids): raise HTTPException(404, "Outbound order not found")
    if user is not None:
        stmt = select(OutboundOrder.id).where(OutboundOrder.id.in_(ids))
        for scope in (warehouse_clause(user, OutboundOrder.warehouse_id), customer_clause(user, OutboundOrder.customer_id)):
            if scope is not None: stmt = stmt.where(scope)
        if set(db.scalars(stmt)) != set(ids): raise HTTPException(404, "Outbound order not found")
    if any(o.warehouse_id != warehouse_id for o in orders): raise HTTPException(409, "All outbound orders must belong to the load warehouse")
    if any(o.status in (OBStatus.DISPATCHED, OBStatus.COMPLETED, OBStatus.CANCELED) for o in orders): raise HTTPException(409, "Completed or canceled outbound cannot be assigned")
    if any(o.load_id and o.load_id != load_id for o in orders): raise HTTPException(409, "Outbound order already belongs to an active load")
    return orders

def create_load(db, payload, user_id, user=None):
    if not db.get(Warehouse, payload.warehouse_id): raise HTTPException(422, "Warehouse not found")
    if payload.carrier_id and not db.get(Carrier, payload.carrier_id): raise HTTPException(422, "Carrier not found")
    orders = _validate_outbounds(db, payload.warehouse_id, payload.outbound_ids, user=user)
    load = Load(load_no=generate_load_no(db), created_by=user_id, **payload.model_dump(exclude={"outbound_ids"}))
    validate_business(load, orders)
    db.add(load); db.flush()
    for order in orders: order.load_id = load.id
    sync_load_notification(db, load)
    db.commit(); return get_load(db, load.id)

def get_load(db, load_id):
    load = db.scalar(load_query().where(Load.id == load_id).execution_options(populate_existing=True))
    if not load: raise HTTPException(404, "Load not found")
    return load

def update_load(db, load, payload):
    load = mutable(db, load)
    if load.status in (LoadStatus.COMPLETED, LoadStatus.CANCELED): raise HTTPException(409, "Completed or canceled load is immutable")
    if payload.carrier_id and not db.get(Carrier, payload.carrier_id): raise HTTPException(422, "Carrier not found")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(load, key, value)
    sync_load_notification(db, load)
    db.commit(); return get_load(db, load.id)

def add_outbounds(db, load, ids, user=None):
    load = mutable(db, load)
    if latest_plan(db, load.id): raise HTTPException(409, "PLAN_EXISTS_MEMBERSHIP_FROZEN")
    if load.status in (LoadStatus.COMPLETED, LoadStatus.CANCELED): raise HTTPException(409, "Load does not accept outbound orders")
    orders = _validate_outbounds(db, load.warehouse_id, ids, load.id, user=user)
    validate_business(load, orders)
    for order in orders: order.load_id = load.id
    db.commit(); return get_load(db, load.id)

def remove_outbound(db, load, outbound_id):
    load = mutable(db, load)
    if latest_plan(db, load.id) or db.scalar(select(LoadAllocation.id).where(LoadAllocation.load_id == load.id, LoadAllocation.outbound_id == outbound_id)):
        raise HTTPException(409, "ALLOCATION_OR_PLAN_EXISTS_MEMBERSHIP_FROZEN")
    if load.status in (LoadStatus.DISPATCHED, LoadStatus.COMPLETED, LoadStatus.CANCELED): raise HTTPException(409, "Load membership is immutable at this status")
    order = db.scalar(select(OutboundOrder).where(OutboundOrder.id == outbound_id, OutboundOrder.load_id == load.id).with_for_update().execution_options(populate_existing=True))
    if not order: raise HTTPException(404, "Outbound order is not assigned to this load")
    order.load_id = None; db.commit(); return get_load(db, load.id)

def transition_load(db, load, target):
    load = db.scalar(select(Load).where(Load.id == load.id).with_for_update().execution_options(populate_existing=True))
    if target.upper() == "DISPATCHED": raise HTTPException(409, "TRANSACTIONAL_DISPATCH_REQUIRED")
    try: status = LoadStatus(target.upper())
    except ValueError as exc: raise HTTPException(422, "Unknown load status") from exc
    if status not in TRANSITIONS[load.status]: raise HTTPException(409, f"Invalid status transition: {load.status} to {status}")
    if status == LoadStatus.READY:
        orders = _validate_outbounds(db, load.warehouse_id, [o.id for o in db.scalars(select(OutboundOrder).where(OutboundOrder.load_id == load.id))], load.id)
        validate_business(load, orders)
    if status == LoadStatus.CANCELED and db.scalar(select(LoadAllocation.id).where(LoadAllocation.load_id == load.id)):
        raise HTTPException(409, "ALLOCATED_LOAD_CANNOT_BE_CANCELED")
    if status == LoadStatus.COMPLETED and db.scalar(select(OutboundOrder.id).where(OutboundOrder.load_id == load.id, OutboundOrder.status != OBStatus.COMPLETED)):
        raise HTTPException(409, "OUTBOUNDS_NOT_COMPLETED")
    load.status = status
    sync_load_notification(db, load)
    db.commit(); return get_load(db, load.id)

def read_load(load):
    sums = [totals(order) for order in load.outbounds]
    vals = [sum((row[i] for row in sums), Decimal("0")) for i in range(4)] if sums else [Decimal("0")] * 4
    outbounds = []
    for order in load.outbounds:
        row = totals(order)
        outbounds.append({"id": order.id, "ob_no": order.ob_no, "warehouse_id": order.warehouse_id, "dispatch_business_type": order.dispatch_business_type, "customer_id": order.customer_id, "inventory_allocations": [{"id": a.id, "carton_qty": a.allocated_carton_qty-a.completed_carton_qty, "pallet_qty": a.allocated_pallet_qty-a.completed_pallet_qty} for a in order.allocations], "fba_reference": order.fba_shipment.fba_no if order.fba_shipment else None, "destination": order.fc_code, "pallet_qty": row[0], "carton_qty": row[1], "weight_lbs": row[2], "cbm": row[3], "status": OBStatus(order.status).name})
    work_orders = [{"id": wo.id, "work_order_no": wo.work_order_no, "work_order_type": wo.work_order_type.value, "status": wo.status.value, "priority": wo.priority.value, "assigned_to": wo.assigned_to, "assigned_team": wo.assigned_team, "assignee_name": wo.assignee.display_name if wo.assignee else None, "created_at": wo.created_at, "started_at": wo.started_at, "completed_at": wo.completed_at} for wo in load.work_orders]
    active_exceptions = [{"id": row.id, "exception_no": row.exception_no, "severity": row.severity.value, "status": row.status.value, "title": row.title} for row in load.operational_exceptions if row.status in (ExceptionStatus.OPEN, ExceptionStatus.INVESTIGATING)]
    return {**{k: getattr(load, k) for k in ("id", "load_no", "dispatch_business_type", "warehouse_id", "carrier_id", "status", "appointment_reference", "appointment_time", "destination_name", "destination_address", "driver_name", "driver_phone", "tractor_no", "trailer_no", "seal_no", "notes", "created_at", "updated_at")}, "status": load.status.value, "warehouse": {"id": load.warehouse.id, "code": load.warehouse.warehouse_code, "name": load.warehouse.warehouse_name} if load.warehouse else None, "carrier": {"id": load.carrier.id, "code": load.carrier.carrier_code, "name": load.carrier.carrier_name} if load.carrier else None, "outbound_count": len(load.outbounds), "total_pallet_qty": vals[0], "total_carton_qty": vals[1], "total_weight_lbs": vals[2], "total_cbm": vals[3], "outbounds": outbounds, "work_orders": work_orders, "active_exception_count": len(active_exceptions), "active_exceptions": active_exceptions[:5]}
