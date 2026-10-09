"""The only application dispatch writer. Evidence and status share one transaction.

Unconfirmed document/approval/review rules deliberately remain UNKNOWN. A read
snapshot cannot authorize a subsequent dispatch, even when all checks pass.
"""
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, or_
from app.models import LoadStatus, OutboundOrder, StageTransaction, LoadVerificationTransaction, PickingListItem
from app.models.outbound import OBStatus
from app.models.load_dispatch import LoadDispatchExecution
from app.schemas.load_dispatch import ReadinessCheck
from app.services.load_dispatch_readiness import dispatch_readiness, overall_ready
from app.services.load_dispatch_write import scoped_load, latest_plan, validate_complete_plan, operation_lock
from app.services.staging import manifest_fingerprint, _member_item, _unit_value


def check(key, status, code, reason, evidence=None, missing=None):
    return ReadinessCheck(key=key, status=status, reason_code=code, reason=reason,
                          evidence=evidence or [], missing_information=missing or [])


def policy_checks(db, load):
    from app.services.dispatch_evidence import checks
    return checks(db, load)


def validate_execution(db, load, facts, lines):
    complete = db.scalar(select(LoadVerificationTransaction).where(
        LoadVerificationTransaction.load_id == load.id, LoadVerificationTransaction.transaction_type == "COMPLETE")
        .order_by(LoadVerificationTransaction.id.desc()).limit(1))
    if complete is None: raise HTTPException(409, "LOADING_VERIFICATION_MISSING")
    if complete.result != "COMPLETE" or not complete.performed_by or complete.manifest_fingerprint != manifest_fingerprint(db, load.id):
        raise HTTPException(409, "LOADING_VERIFICATION_STALE_OR_UNATTRIBUTED")
    staged = {}
    for tx in db.scalars(select(StageTransaction).where(StageTransaction.load_id == load.id).order_by(StageTransaction.id)):
        from app.models import WarehouseLocation
        location = db.get(WarehouseLocation, tx.staging_location_id)
        if not tx.performed_by or not location or location.warehouse_id != load.warehouse_id:
            raise HTTPException(409, "STAGING_OWNERSHIP_OR_ACTOR_INVALID")
        if tx.action not in ("STAGE", "UNSTAGE"): raise HTTPException(409, "STAGING_ACTION_INVALID")
        item = _member_item(db, load, tx.outbound_id, tx.picking_item_id)
        key = (tx.outbound_id, item.id, tx.quantity_unit)
        staged[key] = staged.get(key, Decimal(0)) + (tx.quantity if tx.action == "STAGE" else -tx.quantity)
        if staged[key] < 0 or staged[key] > _unit_value(item, tx.quantity_unit):
            raise HTTPException(409, "STAGING_QUANTITY_INVALID")
    staged = {k: v for k, v in staged.items() if v}
    if not staged: raise HTTPException(409, "STAGING_EVIDENCE_EMPTY")
    observed = {}; started = False
    for tx in db.scalars(select(LoadVerificationTransaction).where(
        LoadVerificationTransaction.load_id == load.id, LoadVerificationTransaction.verification_run_id == complete.verification_run_id)):
        if not tx.performed_by: raise HTTPException(409, "VERIFICATION_ACTOR_MISSING")
        if tx.transaction_type == "START": started = True
        if tx.transaction_type == "SCAN":
            if tx.result != "ACCEPTED" or not tx.quantity or tx.quantity <= 0:
                raise HTTPException(409, "VERIFICATION_SCAN_INVALID")
            key = (tx.outbound_id, tx.picking_item_id, tx.quantity_unit)
            observed[key] = observed.get(key, Decimal(0)) + tx.quantity
    if not started or staged != observed: raise HTTPException(409, "VERIFICATION_DOES_NOT_COVER_STAGING")
    quantities = {}
    for (_, item_id, unit), qty in staged.items():
        item = db.get(PickingListItem, item_id)
        key = (item.outbound_allocation_id, unit)
        quantities[key] = quantities.get(key, Decimal(0)) + qty
    by_id = {a.id: a for a in facts}; expected = {}
    for line in lines:
        inv_id = by_id[line.allocation_id].inventory_allocation_id
        for unit, qty in (("CARTON", line.carton_qty), ("PALLET", line.pallet_qty)):
            if qty: expected[(inv_id, unit)] = expected.get((inv_id, unit), Decimal(0)) + qty
    if quantities != expected: raise HTTPException(409, "STAGING_DOES_NOT_COVER_FINAL_PLAN")
    return [f"verification:{complete.id}:run:{complete.verification_run_id}", f"manifest:{complete.manifest_fingerprint}"]


def integrated_readiness(db, user, load_id, locked=False):
    result = dispatch_readiness(db, user, load_id)
    load = scoped_load(db, user, load_id, locked)
    plan = latest_plan(db, load_id)
    replacements = {}; facts = lines = None
    try:
        if plan is None or plan.status != "FINAL" or not plan.finalized_by:
            raise HTTPException(409, "ATTRIBUTED_FINAL_PLAN_REQUIRED")
        facts, lines = validate_complete_plan(db, load, plan, lock=locked)
        for key in ("allocation_trust", "writer_integration", "identity"):
            replacements[key] = check(key, "PASS", "CURRENT_RESERVATIONS_VALIDATED", "本版计划与订单、库存预留及执行人归属一致。", [f"plan:{plan.id}:revision:{plan.content_revision}"])
    except HTTPException as exc:
        for key in ("allocation_trust", "writer_integration", "identity"):
            replacements[key] = check(key, "BLOCKED", "PLAN_VALIDATION_FAILED", str(exc.detail), missing=[str(exc.detail)])
    try:
        if facts is None: raise HTTPException(409, "VALIDATED_FINAL_PLAN_REQUIRED")
        evidence = validate_execution(db, load, facts, lines)
        replacements["execution"] = check("execution", "PASS", "LOADING_EVIDENCE_VALIDATED", "暂存数量、装车扫描及本版计划逐单位一致。", evidence)
    except HTTPException as exc:
        replacements["execution"] = check("execution", "BLOCKED", "EXECUTION_VALIDATION_FAILED", str(exc.detail), missing=[str(exc.detail)])
    replacements.update({c.key: c for c in policy_checks(db, load)})
    result.checks = [replacements.get(c.key, c) for c in result.checks]
    result.ready = overall_ready(result.checks)
    result.notice = "已接入实际派发阻断。只读预检不是派发授权；提交时将在事务内重新核验。"
    if locked: result.consistency = "Load and reservation locks held in dispatch transaction."
    return result


def dispatch_load(db, user, load_id, payload):
    try:
        from app.services.dispatch_evidence import evidence_lock
        evidence_lock(db)
        operation_lock(db, "load-dispatch:", payload.operation_id)
        load = scoped_load(db, user, load_id, True)
        if not payload.operation_id or payload.plan_id is None or payload.expected_revision is None:
            raise HTTPException(422, "DISPATCH_OPERATION_PLAN_AND_REVISION_REQUIRED")
        prior = db.scalar(select(LoadDispatchExecution).where(LoadDispatchExecution.operation_id == payload.operation_id))
        if prior:
            if (prior.load_id, prior.performed_by, prior.plan_id, prior.content_revision) != (load.id, user.id, payload.plan_id, payload.expected_revision):
                raise HTTPException(409, "OPERATION_ID_CONFLICT")
            return load
        plan = latest_plan(db, load.id)
        if load.status != LoadStatus.READY: raise HTTPException(409, "LOAD_NOT_READY")
        if not plan or plan.id != payload.plan_id or plan.content_revision != payload.expected_revision:
            raise HTTPException(409, "PLAN_REVISION_CONFLICT")
        readiness = integrated_readiness(db, user, load.id, locked=True)
        if not readiness.ready: raise HTTPException(409, readiness.model_dump(mode="json"))
        from app.models import AuditLog
        orders = list(db.scalars(select(OutboundOrder).where(OutboundOrder.load_id == load.id).order_by(OutboundOrder.id).with_for_update().execution_options(populate_existing=True)))
        now = datetime.now(timezone.utc)
        for order in orders:
            order.status = OBStatus.DISPATCHED; order.dispatched_at = now; order.dispatched_by = user.id
        load.status = LoadStatus.DISPATCHED
        db.add(LoadDispatchExecution(load_id=load.id, operation_id=payload.operation_id, plan_id=plan.id,
                                    content_revision=plan.content_revision, performed_by=user.id))
        db.add(AuditLog(user_id=user.id, action="LOAD_DISPATCH", entity_type="load", entity_id=load.id,
                        before_data={"status": "READY"}, after_data={"status": "DISPATCHED", "plan_id": plan.id, "revision": plan.content_revision, "operation_id": payload.operation_id}))
        from app.services.load import sync_load_notification
        sync_load_notification(db, load)
        db.flush(); db.commit()
        from app.services.load import get_load
        return get_load(db, load.id)
    except Exception:
        db.rollback()
        raise
