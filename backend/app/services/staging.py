import hashlib
import json
import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import (Load, LoadVerificationTransaction, OutboundOrder, PickingList,
                        PickingListItem, StageTransaction, WarehouseLocation)

ZERO = Decimal("0")


def _member_item(db, load: Load, outbound_id: int, picking_item_id: int):
    outbound = db.get(OutboundOrder, outbound_id)
    if outbound is None or outbound.load_id != load.id:
        raise HTTPException(409, "Outbound is not a member of this load")
    item = db.scalar(select(PickingListItem).join(PickingList).where(
        PickingListItem.id == picking_item_id,
        PickingList.outbound_order_id == outbound_id,
    ))
    if item is None:
        raise HTTPException(409, "Picking item does not belong to the load member")
    from app.models.outbound import OutboundInventoryAllocation
    from app.models import InventoryLot
    from app.models.picking import PickingStatus
    picking = db.get(PickingList, item.picking_list_id)
    inv = db.get(OutboundInventoryAllocation, item.outbound_allocation_id)
    lot = db.get(InventoryLot, item.inventory_lot_id)
    if (outbound.warehouse_id != load.warehouse_id or not outbound.customer_id
        or outbound.dispatch_business_type != load.dispatch_business_type
        or not inv or inv.outbound_order_id != outbound.id or inv.inventory_lot_id != item.inventory_lot_id
        or not lot or lot.warehouse_id != load.warehouse_id or lot.customer_id != outbound.customer_id
        or picking.status != PickingStatus.COMPLETED or not picking.completed_by):
        raise HTTPException(409, "PICKING_RESERVATION_OWNERSHIP_OR_COMPLETION_INVALID")
    return item


def _unit_value(item, unit: str) -> Decimal:
    unit = unit.upper()
    if unit == "PALLET": return item.picked_pallet_qty
    if unit == "CARTON": return item.picked_carton_qty
    raise HTTPException(422, "quantity_unit must be PALLET or CARTON")


def _staged(db, load_id: int, item_id: int, unit: str) -> Decimal:
    rows = db.execute(select(StageTransaction.action, StageTransaction.quantity).where(
        StageTransaction.load_id == load_id,
        StageTransaction.picking_item_id == item_id,
        StageTransaction.quantity_unit == unit,
    )).all()
    return sum((q if action == "STAGE" else -q for action, q in rows), ZERO)


def _lock(db, load):
    return db.scalar(select(Load).where(Load.id == load.id).with_for_update().execution_options(populate_existing=True))


def _verify_prior(db, load, payload, user_id, kind):
    if not payload.client_operation_id: return None
    prior = db.scalar(select(LoadVerificationTransaction).where(LoadVerificationTransaction.client_operation_id == payload.client_operation_id))
    if prior:
        matches = prior.load_id == load.id and prior.performed_by == user_id and prior.transaction_type == kind
        if kind != "START": matches = matches and prior.verification_run_id == (payload.verification_run_id or payload.verification_id)
        if kind == "SCAN":
            matches = matches and all(getattr(prior, k) == getattr(payload, k) for k in ("outbound_id", "picking_item_id", "quantity")) and prior.quantity_unit == payload.quantity_unit.upper()
        if not matches: raise HTTPException(409, "OPERATION_ID_CONFLICT")
    return prior


def stage(db, load: Load, payload, user_id: int):
    load = _lock(db, load)
    if payload.client_operation_id:
        prior = db.scalar(select(StageTransaction).where(StageTransaction.client_operation_id == payload.client_operation_id))
        if prior:
            if (prior.load_id != load.id or prior.performed_by != user_id
                or any(getattr(prior, k) != getattr(payload, k) for k in ("outbound_id", "picking_item_id", "quantity"))
                or prior.action != payload.action.upper() or prior.quantity_unit != payload.quantity_unit.upper()
                or prior.staging_location_id != (payload.staging_location_id or payload.location_id)):
                raise HTTPException(409, "OPERATION_ID_CONFLICT")
            return _stage_read(prior)
    from app.services.load_dispatch_write import mutable
    mutable(db, load)
    item = _member_item(db, load, payload.outbound_id, payload.picking_item_id)
    location_id = payload.staging_location_id or payload.location_id
    location = db.get(WarehouseLocation, location_id) if location_id else None
    if location is None or location.warehouse_id != load.warehouse_id:
        raise HTTPException(409, "Staging location is not in the load warehouse")
    action, unit = payload.action.upper(), payload.quantity_unit.upper()
    if action not in ("STAGE", "UNSTAGE"):
        raise HTTPException(422, "action must be STAGE or UNSTAGE")
    current = _staged(db, load.id, item.id, unit)
    if action == "STAGE" and current + payload.quantity > _unit_value(item, unit):
        raise HTTPException(409, "Staged quantity exceeds picked quantity")
    if action == "UNSTAGE" and payload.quantity > current:
        raise HTTPException(409, "Unstage quantity exceeds staged quantity")
    tx = StageTransaction(load_id=load.id, outbound_id=payload.outbound_id,
        picking_item_id=item.id, staging_location_id=location.id, action=action,
        quantity=payload.quantity, quantity_unit=unit,
        client_operation_id=payload.client_operation_id, performed_by=user_id)
    db.add(tx); db.commit(); db.refresh(tx)
    return _stage_read(tx)


def _stage_read(tx):
    return {"id": tx.id, "load_id": tx.load_id, "outbound_id": tx.outbound_id,
        "picking_item_id": tx.picking_item_id, "staging_location_id": tx.staging_location_id,
        "action": tx.action, "quantity": tx.quantity, "quantity_unit": tx.quantity_unit,
        "client_operation_id": tx.client_operation_id, "performed_by": tx.performed_by,
        "created_at": tx.created_at}


def manifest_fingerprint(db, load_id: int) -> str:
    members = db.execute(select(OutboundOrder.id).where(OutboundOrder.load_id == load_id).order_by(OutboundOrder.id)).scalars().all()
    staged = db.execute(select(StageTransaction.outbound_id, StageTransaction.picking_item_id,
        StageTransaction.quantity_unit, StageTransaction.action, StageTransaction.quantity)
        .where(StageTransaction.load_id == load_id).order_by(StageTransaction.id)).all()
    totals = {}
    for outbound_id, item_id, unit, action, quantity in staged:
        key = (outbound_id, item_id, unit); totals[key] = totals.get(key, ZERO) + (quantity if action == "STAGE" else -quantity)
    from app.services.load_dispatch_write import latest_plan
    load = db.get(Load, load_id)
    plan = latest_plan(db, load_id)
    context = {k: str(getattr(load, k)) for k in ("warehouse_id", "dispatch_business_type", "carrier_id", "destination_name", "destination_address", "driver_name", "driver_phone", "tractor_no", "trailer_no", "seal_no", "appointment_time", "appointment_reference")}
    context["plan"] = [plan.id, plan.content_revision] if plan else None
    canonical = json.dumps(context, sort_keys=True) + "|members:" + ",".join(map(str, members)) + "|staged:" + ";".join(
        f"{a}:{b}:{c}:{totals[(a,b,c)].normalize()}" for a,b,c in sorted(totals) if totals[(a,b,c)] != ZERO)
    return hashlib.sha256(canonical.encode()).hexdigest()


def verification_start(db, load: Load, payload, user_id: int):
    load = _lock(db, load)
    prior = _verify_prior(db, load, payload, user_id, "START")
    if prior: return _verify_read(prior)
    from app.services.load_dispatch_write import mutable
    mutable(db, load)
    run_id = str(uuid.uuid4())
    tx = LoadVerificationTransaction(verification_run_id=run_id, load_id=load.id,
        transaction_type="START", result="STARTED", client_operation_id=payload.client_operation_id,
        performed_by=user_id)
    db.add(tx); db.commit(); db.refresh(tx); return _verify_read(tx)


def _open_run(db, load_id: int, run_id: str | None):
    if not run_id: raise HTTPException(422, "verification_run_id is required")
    start = db.scalar(select(LoadVerificationTransaction).where(
        LoadVerificationTransaction.load_id == load_id,
        LoadVerificationTransaction.verification_run_id == run_id,
        LoadVerificationTransaction.transaction_type == "START"))
    complete = db.scalar(select(LoadVerificationTransaction.id).where(
        LoadVerificationTransaction.load_id == load_id,
        LoadVerificationTransaction.verification_run_id == run_id,
        LoadVerificationTransaction.transaction_type == "COMPLETE"))
    if start is None: raise HTTPException(404, "Verification run not found")
    if complete is not None: raise HTTPException(409, "Verification run is complete")
    return run_id


def verification_scan(db, load: Load, payload, user_id: int):
    load = _lock(db, load)
    prior = _verify_prior(db, load, payload, user_id, "SCAN")
    if prior: return _verify_read(prior)
    from app.services.load_dispatch_write import mutable
    mutable(db, load)
    run_id = _open_run(db, load.id, payload.verification_run_id or payload.verification_id)
    item = _member_item(db, load, payload.outbound_id, payload.picking_item_id)
    unit = payload.quantity_unit.upper(); staged = _staged(db, load.id, item.id, unit)
    already = db.scalar(select(func.coalesce(func.sum(LoadVerificationTransaction.quantity), 0)).where(
        LoadVerificationTransaction.verification_run_id == run_id,
        LoadVerificationTransaction.transaction_type == "SCAN",
        LoadVerificationTransaction.picking_item_id == item.id,
        LoadVerificationTransaction.quantity_unit == unit)) or ZERO
    if already + payload.quantity > staged:
        raise HTTPException(409, "Verified quantity exceeds staged quantity")
    tx = LoadVerificationTransaction(verification_run_id=run_id, load_id=load.id,
        transaction_type="SCAN", outbound_id=payload.outbound_id, picking_item_id=item.id,
        quantity=payload.quantity, quantity_unit=unit, result="ACCEPTED",
        client_operation_id=payload.client_operation_id, performed_by=user_id)
    db.add(tx); db.commit(); db.refresh(tx); return _verify_read(tx)


def verification_complete(db, load: Load, payload, user_id: int):
    load = _lock(db, load)
    prior = _verify_prior(db, load, payload, user_id, "COMPLETE")
    if prior: return _verify_read(prior)
    from app.services.load_dispatch_write import mutable
    mutable(db, load)
    run_id = _open_run(db, load.id, payload.verification_run_id or payload.verification_id)
    expected = {}
    for tx in db.scalars(select(StageTransaction).where(StageTransaction.load_id == load.id)):
        key=(tx.outbound_id,tx.picking_item_id,tx.quantity_unit); expected[key]=expected.get(key,ZERO)+(tx.quantity if tx.action=="STAGE" else -tx.quantity)
    observed = {}
    for tx in db.scalars(select(LoadVerificationTransaction).where(LoadVerificationTransaction.verification_run_id==run_id,LoadVerificationTransaction.transaction_type=="SCAN")):
        key=(tx.outbound_id,tx.picking_item_id,tx.quantity_unit); observed[key]=observed.get(key,ZERO)+(tx.quantity or ZERO)
    expected={k:v for k,v in expected.items() if v != ZERO}
    if not expected or expected != observed: raise HTTPException(409, "Load verification is incomplete")
    tx=LoadVerificationTransaction(verification_run_id=run_id,load_id=load.id,
        transaction_type="COMPLETE",result="COMPLETE",manifest_fingerprint=manifest_fingerprint(db,load.id),
        client_operation_id=payload.client_operation_id,performed_by=user_id)
    db.add(tx);db.commit();db.refresh(tx);return _verify_read(tx)


def _verify_read(tx):
    return {"id":tx.id,"verification_run_id":tx.verification_run_id,"verification_id":tx.verification_run_id,
        "load_id":tx.load_id,"transaction_type":tx.transaction_type,"outbound_id":tx.outbound_id,
        "picking_item_id":tx.picking_item_id,"quantity":tx.quantity,"quantity_unit":tx.quantity_unit,
        "result":tx.result,"manifest_fingerprint":tx.manifest_fingerprint,"performed_by":tx.performed_by,
        "created_at":tx.created_at}


def execution_summary(db, load: Load):
    current=manifest_fingerprint(db,load.id)
    complete=db.scalar(select(LoadVerificationTransaction).where(
        LoadVerificationTransaction.load_id==load.id,
        LoadVerificationTransaction.transaction_type=="COMPLETE").order_by(LoadVerificationTransaction.id.desc()))
    latest_start = db.scalar(select(LoadVerificationTransaction).where(
        LoadVerificationTransaction.load_id == load.id,
        LoadVerificationTransaction.transaction_type == "START"
    ).order_by(LoadVerificationTransaction.id.desc()))
    current_run = None
    if latest_start:
        run_complete = db.scalar(select(LoadVerificationTransaction.id).where(
            LoadVerificationTransaction.load_id == load.id,
            LoadVerificationTransaction.verification_run_id == latest_start.verification_run_id,
            LoadVerificationTransaction.transaction_type == "COMPLETE"
        ))
        current_run = {"id": latest_start.verification_run_id,
                       "status": "COMPLETE" if run_complete is not None else "STARTED"}
    staged_rows=db.scalars(select(StageTransaction).where(StageTransaction.load_id==load.id)).all()
    net=sum((x.quantity if x.action=="STAGE" else -x.quantity for x in staged_rows),ZERO)
    saved=complete.manifest_fingerprint if complete else None
    return {"load_id":load.id,"current_verification_run":current_run,"staged_quantity":net,"verification_complete":complete is not None,
        "saved_manifest_fingerprint":saved,"current_manifest_fingerprint":current,
        "manifest_matches":saved is not None and saved==current}
