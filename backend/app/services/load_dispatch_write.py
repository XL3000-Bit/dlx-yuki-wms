"""Load facts reference existing reservations; they never reserve inventory twice.

Every mutation locks the load first. Final plans cover the complete reservation;
partial dispatch remains blocked until an explicit business rule is available.
"""
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models import Load, LoadStatus, OutboundOrder, InventoryLot
from app.models.outbound import OutboundInventoryAllocation, OBStatus
from app.models.load_dispatch import LoadAllocation, LoadDispatchPlan, LoadDispatchPlanLine
from app.models.user import ScopeMode, UserRole
from app.services.access_policy import scoped_statement


def operation_lock(db, namespace, operation_id):
    # Global operation IDs must serialize even when requests target different loads.
    if operation_id and db.bind.dialect.name == "postgresql":
        db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(namespace + operation_id, 0))))


def scoped_load(db, user, load_id, lock=False):
    stmt = scoped_statement(select(Load).where(Load.id == load_id), user, warehouse_column=Load.warehouse_id)
    if lock: stmt = stmt.with_for_update()
    load = db.scalar(stmt.execution_options(populate_existing=True))
    if load is None: raise HTTPException(404, "Load not found")
    ids = set(db.scalars(select(OutboundOrder.id).where(OutboundOrder.load_id == load_id)))
    visible = set(db.scalars(scoped_statement(select(OutboundOrder.id).where(
        OutboundOrder.id.in_(ids), OutboundOrder.warehouse_id == load.warehouse_id), user,
        warehouse_column=OutboundOrder.warehouse_id, customer_column=OutboundOrder.customer_id)))
    if ids != visible or (not ids and user.role != UserRole.ADMIN and user.customer_scope_mode == ScopeMode.SELECTED):
        raise HTTPException(404, "Load not found")
    return load


def mutable(db, load):
    load = db.scalar(select(Load).where(Load.id == load.id).with_for_update().execution_options(populate_existing=True))
    if load.status not in (LoadStatus.PLANNED, LoadStatus.READY):
        raise HTTPException(409, "Load execution and content are immutable at this status")
    return load


def validate_business(load, orders):
    domain = load.dispatch_business_type
    if domain not in ("FBA", "PRIVATE"):
        raise HTTPException(409, "DISPATCH_BUSINESS_TYPE_MISSING: explicitly classify the load")
    for order in orders:
        if order.warehouse_id != load.warehouse_id or order.customer_id is None:
            raise HTTPException(409, "ORDER_OWNERSHIP_INVALID: warehouse and customer are required")
        if order.dispatch_business_type != domain:
            raise HTTPException(409, "DISPATCH_BUSINESS_MISMATCH: explicitly classify every order; mixed business is forbidden")
        fba = order.ob_type == "FBA" and order.fba_shipment_id is not None
        if (domain == "FBA" and not fba) or (domain == "PRIVATE" and (order.ob_type == "FBA" or order.fba_shipment_id)):
            raise HTTPException(409, "DISPATCH_BUSINESS_SOURCE_CONFLICT")


def classify_order(db, user, order_id, domain):
    order = db.scalar(scoped_statement(select(OutboundOrder).where(OutboundOrder.id == order_id), user,
        warehouse_column=OutboundOrder.warehouse_id, customer_column=OutboundOrder.customer_id).with_for_update().execution_options(populate_existing=True))
    if order is None: raise HTTPException(404, "Outbound order not found")
    if order.load_id or order.status in (OBStatus.DISPATCHED, OBStatus.COMPLETED, OBStatus.CANCELED):
        raise HTTPException(409, "Only unassigned active orders can be classified")
    from types import SimpleNamespace
    previous = order.dispatch_business_type
    order.dispatch_business_type = domain
    try: validate_business(SimpleNamespace(dispatch_business_type=domain, warehouse_id=order.warehouse_id), [order])
    except Exception:
        order.dispatch_business_type = previous
        raise
    db.commit()
    return {"outbound_id": order.id, "dispatch_business_type": domain}


def write_allocation(db, user, load_id, payload):
    operation_lock(db, "load-allocation:", payload.operation_id)
    load = scoped_load(db, user, load_id, lock=True)
    prior = db.scalar(select(LoadAllocation).where(LoadAllocation.operation_id == payload.operation_id))
    if prior:
        if (prior.load_id != load.id or prior.created_by != user.id or
            any(getattr(prior, k) != getattr(payload, k) for k in ("inventory_allocation_id", "carton_qty", "pallet_qty"))):
            raise HTTPException(409, "OPERATION_ID_CONFLICT")
        return allocation_read(prior)
    mutable(db, load)
    plan = latest_plan(db, load.id)
    if plan and plan.status == "FINAL": raise HTTPException(409, "FINAL_PLAN_ALLOCATION_IMMUTABLE")
    inv = db.get(OutboundInventoryAllocation, payload.inventory_allocation_id)
    if inv is None: raise HTTPException(404, "Inventory allocation not found")
    order = db.scalar(scoped_statement(select(OutboundOrder).where(OutboundOrder.id == inv.outbound_order_id), user,
        warehouse_column=OutboundOrder.warehouse_id, customer_column=OutboundOrder.customer_id).with_for_update().execution_options(populate_existing=True))
    if order is None: raise HTTPException(404, "Outbound order not found")
    inv = db.scalar(select(OutboundInventoryAllocation).where(
        OutboundInventoryAllocation.id == payload.inventory_allocation_id).with_for_update().execution_options(populate_existing=True))
    if inv is None: raise HTTPException(409, "INVENTORY_RESERVATION_CHANGED")
    if order.load_id != load.id: raise HTTPException(409, "ALLOCATION_ORDER_NOT_LOAD_MEMBER")
    validate_business(load, [order])
    lock_fba_shipments(db, [order])
    lot = db.scalar(select(InventoryLot).where(InventoryLot.id == inv.inventory_lot_id).with_for_update().execution_options(populate_existing=True))
    validate_reservation_source(db, order, inv, lock=True)
    if lot is None or lot.warehouse_id != load.warehouse_id or lot.customer_id != order.customer_id:
        raise HTTPException(409, "INVENTORY_OWNERSHIP_MISMATCH")
    validate_lot_reservations(db, lot)
    if order.status in (OBStatus.DISPATCHED, OBStatus.COMPLETED, OBStatus.CANCELED):
        raise HTTPException(409, "ORDER_NOT_ACTIVE")
    if payload.carton_qty + payload.pallet_qty <= 0: raise HTTPException(422, "POSITIVE_ALLOCATION_REQUIRED")
    existing = list(db.scalars(select(LoadAllocation).where(LoadAllocation.inventory_allocation_id == inv.id)))
    for unit in ("carton", "pallet"):
        assigned = sum((getattr(a, f"{unit}_qty") for a in existing), Decimal(0))
        remaining = getattr(inv, f"allocated_{unit}_qty") - getattr(inv, f"completed_{unit}_qty")
        if assigned + getattr(payload, f"{unit}_qty") > remaining:
            raise HTTPException(409, f"ALLOCATION_EXCEEDS_RESERVED_{unit.upper()}")
    row = LoadAllocation(load_id=load.id, outbound_id=order.id, created_by=user.id, **payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return allocation_read(row)


def allocation_read(row):
    return {k: getattr(row, k) for k in ("id", "load_id", "outbound_id", "inventory_allocation_id", "carton_qty", "pallet_qty", "operation_id", "created_by")}


def latest_plan(db, load_id):
    return db.scalar(select(LoadDispatchPlan).where(LoadDispatchPlan.load_id == load_id).order_by(LoadDispatchPlan.version.desc()).limit(1).execution_options(populate_existing=True))


def lock_fba_shipments(db, orders, lock=True):
    # Shared order: Load -> Orders -> Reservations -> Shipments -> Lots -> Sources.
    from app.models import FBAShipment
    from app.services.history_policy import require_live_record
    fba_orders = [o for o in orders if o.ob_type == "FBA" or o.dispatch_business_type == "FBA"]
    stmt = select(FBAShipment).where(FBAShipment.id.in_([o.fba_shipment_id for o in fba_orders])).order_by(FBAShipment.id)
    shipments = {s.id: s for s in db.scalars((stmt.with_for_update() if lock else stmt).execution_options(populate_existing=True))}
    for order in fba_orders:
        shipment = shipments.get(order.fba_shipment_id)
        if shipment is None or order.customer_id is None or (shipment.warehouse_id, shipment.customer_id) != (order.warehouse_id, order.customer_id):
            raise HTTPException(409, "FBA_SHIPMENT_OWNERSHIP_MISMATCH")
        if shipment.status in (7, 9): raise HTTPException(409, "FBA_SHIPMENT_NOT_ACTIVE")
        require_live_record(db, shipment)
    return shipments


def validate_reservation_source(db, order, inv, lock=False):
    from app.models import FBAInventoryAllocation, FBAShipment
    if order.ob_type == "FBA" or order.dispatch_business_type == "FBA":
        stmt = select(FBAInventoryAllocation).where(FBAInventoryAllocation.id == inv.fba_allocation_id)
        source = db.scalar((stmt.with_for_update() if lock else stmt).execution_options(populate_existing=True)) if inv.fba_allocation_id else None
        if source is None or source.fba_shipment_id != order.fba_shipment_id or source.inventory_lot_id != inv.inventory_lot_id:
            raise HTTPException(409, "FBA_RESERVATION_SOURCE_MISMATCH")
        shipment = db.scalar(select(FBAShipment).where(FBAShipment.id == source.fba_shipment_id).execution_options(populate_existing=True))
        if shipment is None or shipment.warehouse_id != order.warehouse_id or shipment.customer_id != order.customer_id:
            raise HTTPException(409, "FBA_SHIPMENT_OWNERSHIP_MISMATCH")
        if shipment.status in (7, 9): raise HTTPException(409, "FBA_SHIPMENT_NOT_ACTIVE")
        units = ("carton_qty", "pallet_qty", "weight_lbs", "cbm")
        reserved = db.execute(select(*(func.coalesce(func.sum(getattr(OutboundInventoryAllocation, f"allocated_{unit}") - getattr(OutboundInventoryAllocation, f"completed_{unit}")), 0) for unit in units)).where(OutboundInventoryAllocation.fba_allocation_id == source.id)).one()
        if any(q < 0 or q > getattr(source, f"allocated_{unit}") for unit, q in zip(units, reserved)):
            raise HTTPException(409, "FBA_RESERVATION_QUANTITY_MISMATCH")
        return source
    elif inv.fba_allocation_id:
        raise HTTPException(409, "PRIVATE_RESERVATION_HAS_FBA_SOURCE")


def validate_lot_reservations(db, lot):
    """Check every reservation while the caller holds the lot lock.

    FBA outbound reservations consume their upstream source; counting both
    would double-count stock. Private reservations consume the lot directly.
    """
    from app.models import FBAInventoryAllocation
    from app.services.history_policy import require_live_record
    require_live_record(db, lot.source_inbound)
    units = ("carton_qty", "pallet_qty", "weight_lbs", "cbm")
    sources = list(db.scalars(select(FBAInventoryAllocation).where(FBAInventoryAllocation.inventory_lot_id == lot.id).execution_options(populate_existing=True)))
    reservations = list(db.scalars(select(OutboundInventoryAllocation).where(OutboundInventoryAllocation.inventory_lot_id == lot.id).execution_options(populate_existing=True)))
    for unit in units:
        source_qty = [getattr(s, f"allocated_{unit}") for s in sources]
        remaining = [getattr(a, f"allocated_{unit}") - getattr(a, f"completed_{unit}") for a in reservations]
        if any(q < 0 for q in source_qty + remaining):
            raise HTTPException(409, "INVENTORY_REMAINDER_INVALID")
        reserved = sum(source_qty, Decimal(0)) + sum((q for a, q in zip(reservations, remaining) if a.fba_allocation_id is None), Decimal(0))
        if reserved > getattr(lot, f"allocated_{unit}") or getattr(lot, f"allocated_{unit}") < 0:
            raise HTTPException(409, "INVENTORY_RESERVATION_QUANTITY_MISMATCH")


def plan_read(db, plan):
    if plan is None: return None
    return {**{k: getattr(plan, k) for k in ("id", "load_id", "version", "status", "content_revision", "created_by", "finalized_by")},
            "lines": [{k: getattr(l, k) for k in ("id", "allocation_id", "carton_qty", "pallet_qty")} for l in db.scalars(
                select(LoadDispatchPlanLine).where(LoadDispatchPlanLine.plan_id == plan.id).order_by(LoadDispatchPlanLine.id))]}


def create_plan(db, user, load_id):
    load = mutable(db, scoped_load(db, user, load_id, True))
    previous = latest_plan(db, load.id)
    if previous and previous.status == "DRAFT": return plan_read(db, previous)
    plan = LoadDispatchPlan(load_id=load.id, version=(previous.version + 1 if previous else 1), status="DRAFT", content_revision=0, created_by=user.id)
    db.add(plan); db.commit(); db.refresh(plan)
    return plan_read(db, plan)


def editable_plan(db, user, load_id, plan_id, revision):
    load = mutable(db, scoped_load(db, user, load_id, True))
    plan = latest_plan(db, load_id)
    if plan is None or plan.id != plan_id: raise HTTPException(409, "LATEST_PLAN_REQUIRED")
    if plan.status != "DRAFT": raise HTTPException(409, "FINAL_PLAN_IMMUTABLE")
    if plan.content_revision != revision: raise HTTPException(409, "PLAN_REVISION_CONFLICT")
    return load, plan


def replace_lines(db, user, load_id, plan_id, payload):
    load, plan = editable_plan(db, user, load_id, plan_id, payload.expected_revision)
    facts = {a.id: a for a in db.scalars(select(LoadAllocation).where(LoadAllocation.load_id == load.id))}
    ids = [l.allocation_id for l in payload.lines]
    if len(ids) != len(set(ids)): raise HTTPException(422, "DUPLICATE_PLAN_ALLOCATION")
    for line in payload.lines:
        fact = facts.get(line.allocation_id)
        if fact is None: raise HTTPException(409, "PLAN_ALLOCATION_NOT_IN_LOAD")
        if line.carton_qty + line.pallet_qty <= 0 or line.carton_qty > fact.carton_qty or line.pallet_qty > fact.pallet_qty:
            raise HTTPException(409, "PLAN_QUANTITY_OUTSIDE_ALLOCATION")
    for old in db.scalars(select(LoadDispatchPlanLine).where(LoadDispatchPlanLine.plan_id == plan.id)): db.delete(old)
    db.flush()
    for line in payload.lines: db.add(LoadDispatchPlanLine(plan_id=plan.id, **line.model_dump()))
    db.flush()
    if db.bind.dialect.name != "postgresql": plan.content_revision += 1
    db.commit(); db.refresh(plan)
    return plan_read(db, plan)


def validate_complete_plan(db, load, plan, lock=True):
    stmt = select(OutboundOrder).where(OutboundOrder.load_id == load.id).order_by(OutboundOrder.id)
    orders = list(db.scalars((stmt.with_for_update() if lock else stmt).execution_options(populate_existing=True)))
    if not orders: raise HTTPException(409, "LOAD_HAS_NO_ORDERS")
    validate_business(load, orders)
    if any(o.status != OBStatus.CONFIRMED for o in orders): raise HTTPException(409, "ALL_ORDERS_MUST_BE_CONFIRMED")
    stmt = select(OutboundInventoryAllocation).where(OutboundInventoryAllocation.outbound_order_id.in_([o.id for o in orders])).order_by(OutboundInventoryAllocation.id)
    inventory = list(db.scalars((stmt.with_for_update() if lock else stmt).execution_options(populate_existing=True)))
    lock_fba_shipments(db, orders, lock=lock)
    lot_stmt = select(InventoryLot).where(InventoryLot.id.in_([i.inventory_lot_id for i in inventory])).order_by(InventoryLot.id)
    lots = {l.id: l for l in db.scalars((lot_stmt.with_for_update() if lock else lot_stmt).execution_options(populate_existing=True))}
    for lot in lots.values(): validate_lot_reservations(db, lot)
    facts = list(db.scalars(select(LoadAllocation).where(LoadAllocation.load_id == load.id)))
    lines = list(db.scalars(select(LoadDispatchPlanLine).where(LoadDispatchPlanLine.plan_id == plan.id)))
    if not lines or {l.allocation_id for l in lines} != {a.id for a in facts}:
        raise HTTPException(409, "PLAN_MUST_COVER_ALL_LOAD_ALLOCATIONS")
    if not plan.created_by: raise HTTPException(409, "PLAN_AUTHOR_MISSING")
    by_id = {a.id: a for a in facts}; quantities = {}
    for line in lines:
        fact = by_id[line.allocation_id]
        if not fact.created_by or (line.carton_qty, line.pallet_qty) != (fact.carton_qty, fact.pallet_qty):
            raise HTTPException(409, "PARTIAL_OR_UNATTRIBUTED_PLAN_UNSUPPORTED")
        q = quantities.setdefault(fact.inventory_allocation_id, [Decimal(0), Decimal(0)])
        q[0] += line.carton_qty; q[1] += line.pallet_qty
    expected = {}
    order_map = {o.id: o for o in orders}
    for inv in inventory:
        lot = lots.get(inv.inventory_lot_id)
        order = order_map[inv.outbound_order_id]
        validate_reservation_source(db, order, inv, lock=lock)
        if lot is None or lot.warehouse_id != load.warehouse_id or lot.customer_id != order.customer_id:
            raise HTTPException(409, "INVENTORY_OWNERSHIP_MISMATCH")
        q = [inv.allocated_carton_qty - inv.completed_carton_qty, inv.allocated_pallet_qty - inv.completed_pallet_qty]
        if any(v < 0 for v in q): raise HTTPException(409, "INVENTORY_REMAINDER_INVALID")
        if any(q): expected[inv.id] = q
    inv_by_id = {a.id: a for a in inventory}
    if any(a.inventory_allocation_id not in inv_by_id or inv_by_id[a.inventory_allocation_id].outbound_order_id != a.outbound_id for a in facts):
        raise HTTPException(409, "ALLOCATION_ORDER_OWNERSHIP_MISMATCH")
    if not expected or quantities != expected: raise HTTPException(409, "PLAN_MUST_COVER_COMPLETE_RESERVED_INVENTORY")
    if {a.outbound_id for a in facts} != set(order_map): raise HTTPException(409, "ORDER_ALLOCATION_MISSING")
    return facts, lines


def finalize_plan(db, user, load_id, plan_id, payload):
    load = scoped_load(db, user, load_id, True)
    plan = latest_plan(db, load_id)
    if plan and plan.id == plan_id and plan.status == "FINAL" and plan.content_revision == payload.expected_revision:
        return plan_read(db, plan)
    load, plan = editable_plan(db, user, load_id, plan_id, payload.expected_revision)
    validate_complete_plan(db, load, plan)
    plan.status = "FINAL"; plan.finalized_by = user.id
    db.commit(); db.refresh(plan)
    return plan_read(db, plan)
