"""Observational SELECT-only preflight; existing writers do not maintain its facts."""
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.models import Load, OutboundOrder
from app.models.load_dispatch import LoadAllocation, LoadDispatchPlan, LoadDispatchPlanLine
from app.models.outbound import OutboundInventoryAllocation
from app.models.user import ScopeMode, UserRole
from app.schemas.load_dispatch import DispatchReadiness, ReadinessCheck, ReadinessStatus
from app.services.access_policy import scoped_statement


def overall_ready(checks):
    """No vacuous success; applicability also needs affirmative evidence."""
    return bool(checks) and all(
        c.status in (ReadinessStatus.PASS, ReadinessStatus.NOT_APPLICABLE)
        and c.evidence and c.reason_code and not c.missing_information
        for c in checks
    )


def evaluate(load, plan, lines, allocations):
    checks = []

    def add(key, status, code, reason, evidence=None, missing=None):
        checks.append(ReadinessCheck(key=key, status=status, reason_code=code,
                                     reason=reason, evidence=evidence or [],
                                     missing_information=missing or []))

    state = getattr(load.status, "value", load.status)
    add("load_state", "PASS" if state == "READY" else "BLOCKED",
        "LOAD_READY" if state == "READY" else "LOAD_NOT_READY",
        "Load must be READY.", [f"load:{load.id}:status:{state}"])
    if plan is None:
        add("final_plan", "UNKNOWN", "FINAL_PLAN_MISSING", "No plan evidence exists.",
            missing=["Final dispatch plan"])
    elif plan.status != "FINAL":
        add("final_plan", "BLOCKED", "LATEST_PLAN_NOT_FINAL", "Latest plan is not final.",
            [f"plan:{plan.id}:version:{plan.version}"])
    elif not lines:
        add("final_plan", "BLOCKED", "FINAL_PLAN_EMPTY", "Final plan has no lines.", [f"plan:{plan.id}"])
    else:
        add("final_plan", "PASS", "FINAL_PLAN_PRESENT", "Final plan is present; approval is checked separately.",
            [f"plan:{plan.id}:version:{plan.version}:revision:{plan.content_revision}"])
    by_id = {a.id: a for a in allocations}
    for line in lines:
        allocation = by_id.get(line.allocation_id)
        for unit in ("carton_qty", "pallet_qty"):
            key = f"quantity:{line.id}:{unit}"
            if allocation is None:
                add(key, "UNKNOWN", "ALLOCATION_MISSING", "Allocation evidence is missing.",
                    missing=["Referenced allocation"])
                continue
            planned = Decimal(str(getattr(line, unit)))
            assigned = Decimal(str(getattr(allocation, unit)))
            valid = (planned.is_finite() and assigned.is_finite()
                     and 0 <= planned <= assigned)
            add(key, "PASS" if valid else "BLOCKED",
                "QUANTITY_WITHIN_ALLOCATION" if valid else "QUANTITY_OUTSIDE_ALLOCATION",
                "Each unit is compared only with its own allocation line; no conversion or offset.",
                [f"plan_line:{line.id}", f"allocation:{allocation.id}:{unit}"])
    for key, code, gap in (
        ("allocation_trust", "ALLOCATION_FACTS_UNVERIFIED", "Verified provenance and completeness of allocation facts"),
        ("writer_integration", "LEGACY_WRITERS_NOT_INTEGRATED", "Existing write paths maintaining the new models"),
        ("documents", "DOCUMENT_RULES_NOT_CONFIGURED", "Approved applicable document rules and versioned review evidence"),
        ("dispatch_approval", "DISPATCH_APPROVAL_MISSING", "Independent approval bound to the final plan"),
        ("exceptions", "EXCEPTION_EVIDENCE_INCOMPLETE", "Complete scoped exception decisions and reviews"),
        ("execution", "EXECUTION_EVIDENCE_NOT_INTEGRATED", "Staging, return and loading verification for the final plan"),
        ("identity", "IDENTITY_EVIDENCE_INCOMPLETE", "Full record ownership and warehouse relationship evidence"),
    ):
        add(key, "UNKNOWN", code, "Cannot establish this requirement from integrated evidence.", missing=[gap])
    return DispatchReadiness(load_id=load.id, checked_at=datetime.now(timezone.utc),
                             plan_id=plan.id if plan else None,
                             plan_version=plan.version if plan else None,
                             content_revision=plan.content_revision if plan else None,
                             checks=checks, ready=overall_ready(checks))


def dispatch_readiness(db, user, load_id):
    """Reject incomplete visibility before producing any evidence. No implicit flush."""
    try:
        with db.no_autoflush:
            load = db.scalar(scoped_statement(select(Load).where(Load.id == load_id), user,
                                              warehouse_column=Load.warehouse_id))
            if load is None:
                raise HTTPException(404, "Load not found")
            legacy_ids = set(db.scalars(select(OutboundOrder.id).where(OutboundOrder.load_id == load_id)).all())
            allocations = db.scalars(select(LoadAllocation).where(LoadAllocation.load_id == load_id)).all()
            plan = db.scalar(select(LoadDispatchPlan).where(LoadDispatchPlan.load_id == load_id)
                             .order_by(LoadDispatchPlan.version.desc()).limit(1))
            lines = (db.scalars(select(LoadDispatchPlanLine).where(LoadDispatchPlanLine.plan_id == plan.id)).all()
                     if plan else [])
            allocation_ids = {a.id for a in allocations}
            if any(line.allocation_id not in allocation_ids for line in lines):
                raise HTTPException(404, "Load not found")
            inventory_ids = {a.inventory_allocation_id for a in allocations}
            inventory = (db.scalars(select(OutboundInventoryAllocation).where(
                OutboundInventoryAllocation.id.in_(inventory_ids))).all() if inventory_ids else [])
            if {a.id for a in inventory} != inventory_ids:
                raise HTTPException(404, "Load not found")
            inventory_by_id = {a.id: a for a in inventory}
            if any(inventory_by_id[a.inventory_allocation_id].outbound_order_id != a.outbound_id
                   for a in allocations):
                raise HTTPException(404, "Load not found")
            order_ids = legacy_ids | {a.outbound_id for a in allocations} | {a.outbound_order_id for a in inventory}
            if not order_ids and user.role != UserRole.ADMIN and user.customer_scope_mode == ScopeMode.SELECTED:
                raise HTTPException(404, "Load not found")
            if order_ids:
                visible = set(db.scalars(scoped_statement(
                    select(OutboundOrder.id).where(OutboundOrder.id.in_(order_ids),
                                                   OutboundOrder.warehouse_id == load.warehouse_id), user,
                    warehouse_column=OutboundOrder.warehouse_id,
                    customer_column=OutboundOrder.customer_id)).all())
                if visible != order_ids:
                    raise HTTPException(404, "Load not found")
            return evaluate(load, plan, lines, allocations)
    except SQLAlchemyError:
        raise HTTPException(503, "Dispatch readiness is temporarily unavailable") from None
