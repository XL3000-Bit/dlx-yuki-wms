"""Fail-closed, version-bound evidence. Configuration has no HTTP write surface."""
import hashlib
import json
from datetime import datetime, timezone, timedelta
from enum import Enum
from sqlalchemy import select, or_, text
from fastapi import HTTPException
from app.models import OutboundOrder, User, BOL, AuditLog
from app.models.dispatch_evidence import DispatchEvidencePolicy, DispatchEvidenceReview
from app.models.operational_document import OperationalDocument, DocumentStatus
from app.models.operational_exception import OperationalException, ExceptionStatus
from app.schemas.dispatch_evidence import EvidenceRules
from app.services.load_dispatch_write import scoped_load, latest_plan, validate_complete_plan, operation_lock, plan_read

KINDS = {"DOCUMENTS": ("documents", "document_review"), "APPROVAL": ("dispatch_approval", "approval"), "EXCEPTIONS": ("exceptions", "exception_review")}
UNKNOWN = {"DOCUMENTS": "DOCUMENT_RULES_NOT_CONFIGURED", "APPROVAL": "DISPATCH_APPROVAL_MISSING", "EXCEPTIONS": "EXCEPTION_REVIEW_RULES_MISSING"}


def evidence_lock(db):
    # Same lock is acquired by PostgreSQL source-table statement triggers.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(748320610050039)"))


def value(v):
    if isinstance(v, Enum): return v.value
    if isinstance(v, datetime): return utc(v).isoformat()
    if isinstance(v, (str, int, float, bool)) or v is None: return v
    return str(v)


def utc(v):
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)


def row_data(row, exclude=()):
    return {c.name: value(getattr(row, c.name)) for c in row.__table__.columns if c.name not in exclude}


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def policy(db, load):
    from app.services.dispatch_policy_config import source_allowed
    p = db.scalar(select(DispatchEvidencePolicy).where(DispatchEvidencePolicy.warehouse_id == load.warehouse_id,
        DispatchEvidencePolicy.business_type == load.dispatch_business_type).order_by(DispatchEvidencePolicy.version.desc()).limit(1))
    if not p or not p.enabled or not source_allowed(db, p.source): return p, None
    try: return p, EvidenceRules.model_validate(p.rules)
    except ValueError: return p, None


def actor_allowed(db, actor_id, load, plan, rule, independent=False):
    actor = db.get(User, actor_id, populate_existing=True)
    if not actor or not actor.is_active or actor.role not in rule.roles: return False
    db.expire(actor, ["warehouses", "customers"])
    if independent and actor.id in (plan.created_by, plan.finalized_by): return False
    try: scoped_load(db, actor, load.id)
    except HTTPException: return False
    return True


def related_exceptions(db, load):
    from app.models import PickingList, ContainerTracking, InventoryLot, OutboundInventoryAllocation, WorkOrder
    orders = select(OutboundOrder.id).where(OutboundOrder.load_id == load.id)
    picking = select(PickingList.id).where(PickingList.outbound_order_id.in_(orders))
    bols = select(BOL.id).where(BOL.outbound_order_id.in_(orders))
    containers = select(InventoryLot.container_number).join(OutboundInventoryAllocation, OutboundInventoryAllocation.inventory_lot_id == InventoryLot.id).where(OutboundInventoryAllocation.outbound_order_id.in_(orders))
    tracks = select(ContainerTracking.id).where(ContainerTracking.warehouse_id == load.warehouse_id, ContainerTracking.container_number.in_(containers))
    work_exceptions = select(WorkOrder.operational_exception_id).where(or_(WorkOrder.load_id == load.id, WorkOrder.outbound_id.in_(orders), WorkOrder.picking_list_id.in_(picking), WorkOrder.container_tracking_id.in_(tracks)))
    return list(db.scalars(select(OperationalException).where(
        or_(OperationalException.load_id == load.id, OperationalException.outbound_id.in_(orders),
            OperationalException.picking_list_id.in_(picking), OperationalException.bol_id.in_(bols), OperationalException.container_tracking_id.in_(tracks), OperationalException.id.in_(work_exceptions)))
        .order_by(OperationalException.id).execution_options(populate_existing=True)))


def public_exception(e, load, events=False):
    # Corrupt cross-warehouse links must block without revealing the other warehouse's record.
    if e.warehouse_id != load.warehouse_id:
        return {"id": e.id, "status": "SCOPE_MISMATCH", "scope_mismatch": True}
    data = row_data(e)
    if events: data["events"] = [row_data(x) for x in e.events]
    return data


def document_data(db, doc, load, orders, requirement):
    if doc.status != DocumentStatus.AVAILABLE or doc.dispatch_business_type != load.dispatch_business_type:
        return None
    order_ids = {o.id for o in orders}; customers = {o.customer_id for o in orders}
    if doc.warehouse_id != load.warehouse_id or (doc.customer_id not in customers and not (doc.customer_id is None and doc.load_id == load.id)) or not doc.created_by: return None
    if doc.load_id is not None and doc.load_id != load.id: return None
    if doc.outbound_id is not None and doc.outbound_id not in order_ids: return None
    db.expire(doc, ["events"])
    data = row_data(doc)
    data["events"] = [row_data(e) for e in sorted(doc.events, key=lambda e: e.id)]
    if not data["events"]: return None
    if doc.is_generated:
        bol = db.get(BOL, doc.bol_id, populate_existing=True) if doc.bol_id else None
        if not requirement.allow_generated or not bol or int(bol.status) not in requirement.bol_statuses: return None
        if bol.outbound_order_id not in order_ids or bol.warehouse_id != load.warehouse_id or bol.customer_id != doc.customer_id: return None
        db.expire(bol, ["items"])
        if doc.outbound_id != bol.outbound_order_id or not bol.items: return None
        data["bol"] = row_data(bol); data["bol_items"] = [row_data(i) for i in sorted(bol.items, key=lambda i: i.id)]
    else:
        if not doc.storage_key or not doc.checksum_sha256 or not doc.file_size: return None
        from app.services.document_storage import LocalDocumentStorage
        try:
            h = hashlib.sha256(); size = 0
            with LocalDocumentStorage().open(doc.storage_key) as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""): h.update(chunk); size += len(chunk)
            if h.hexdigest() != doc.checksum_sha256 or size != doc.file_size: return None
        except (OSError, ValueError, HTTPException): return None
    return data


def snapshots(db, load, plan, rules):
    orders = list(db.scalars(select(OutboundOrder).where(OutboundOrder.load_id == load.id).order_by(OutboundOrder.id).execution_options(populate_existing=True)))
    base = {"load": row_data(load, ("status", "created_at", "updated_at")), "plan": plan_read(db, plan),
            "orders": [row_data(o, ("status", "dispatched_at", "dispatched_by", "created_at", "updated_at")) for o in orders]}
    # Normalize Decimal/enum/datetime in nested plan serializers.
    base = json.loads(json.dumps(base, default=value))
    sources = {k: dict(base) for k in KINDS}; missing = {k: [] for k in KINDS}
    docs = list(db.scalars(select(OperationalDocument).where(or_(OperationalDocument.load_id == load.id,
        OperationalDocument.outbound_id.in_([o.id for o in orders]))).order_by(OperationalDocument.id).execution_options(populate_existing=True)))
    selected = []
    for req in rules.documents:
        for target in ([o.id for o in orders] if req.scope == "ORDER" else [load.id]):
            candidates = [d for d in docs if d.document_type == req.document_type and
                (d.outbound_id == target if req.scope == "ORDER" else d.load_id == target)]
            valid = [data for d in candidates if (data := document_data(db, d, load, orders, req))]
            if not valid: missing["DOCUMENTS"].append(f"{req.scope}:{target}:{req.document_type.value}:有效版本/归属/文件证据缺失")
            selected.extend(valid)
    sources["DOCUMENTS"]["documents"] = selected
    exceptions = related_exceptions(db, load)
    for e in exceptions: db.expire(e, ["events"])
    sources["EXCEPTIONS"]["exceptions"] = [dict(row_data(e), events=[row_data(x) for x in sorted(e.events, key=lambda x: x.id)]) for e in exceptions]
    for e in exceptions:
        if e.warehouse_id != load.warehouse_id: missing["EXCEPTIONS"].append(f"exception:{e.id}:EXCEPTION_SCOPE_MISMATCH")
        elif e.status in (ExceptionStatus.OPEN, ExceptionStatus.INVESTIGATING): missing["EXCEPTIONS"].append(f"exception:{e.id}:ACTIVE_EXCEPTIONS")
        elif e.status == ExceptionStatus.CANCELED and not rules.allow_canceled_exceptions: missing["EXCEPTIONS"].append(f"exception:{e.id}:CANCELLATION_NOT_AUTHORIZED")
        elif e.status == ExceptionStatus.CANCELED:
            if not any(x.actor_user_id and x.new_value == e.status.value and x.message and x.message.strip() for x in e.events): missing["EXCEPTIONS"].append(f"exception:{e.id}:ATTRIBUTED_CANCELLATION_REQUIRED")
        elif not e.resolved_by or not e.resolved_at or not e.resolution or not any(x.actor_user_id == e.resolved_by and x.new_value == e.status.value for x in e.events):
            missing["EXCEPTIONS"].append(f"exception:{e.id}:ATTRIBUTED_RESOLUTION_REQUIRED")
    return sources, missing, docs, exceptions


def latest_review(db, load_id, kind):
    return db.scalar(select(DispatchEvidenceReview).where(DispatchEvidenceReview.load_id == load_id,
        DispatchEvidenceReview.kind == kind).order_by(DispatchEvidenceReview.id.desc()).limit(1))


def review_status(db, load, plan, p, rules, kind, snapshot, missing):
    fingerprint = digest(snapshot); r = latest_review(db, load.id, kind)
    reason = "; ".join(missing)
    if not reason:
        if not r: reason = "REVIEW_REQUIRED"
        elif r.decision != "ACCEPT": reason = "REVIEW_REJECTED"
        elif r.plan_id != plan.id or r.content_revision != plan.content_revision or r.policy_id != p.id or r.fingerprint != fingerprint: reason = "EVIDENCE_STALE"
        elif utc(r.expires_at) <= datetime.now(timezone.utc): reason = "EVIDENCE_EXPIRED"
        elif not actor_allowed(db, r.actor_id, load, plan, getattr(rules, KINDS[kind][1]), kind == "APPROVAL" and rules.independent_approver): reason = "REVIEWER_PERMISSION_CHANGED"
    return {"kind": kind, "status": "BLOCKED" if reason else "PASS", "reason": reason or "CURRENT_EVIDENCE_VALIDATED",
        "fingerprint": fingerprint, "missing": missing, "review": row_data(r) if r else None}


def evidence_view(db, user, load_id, *, internal_load=None):
    load = internal_load if internal_load is not None else scoped_load(db, user, load_id); plan = latest_plan(db, load.id); p, rules = policy(db, load)
    result = {"load_id": load.id, "business_type": load.dispatch_business_type, "policy": row_data(p) if p else None,
        "configured": bool(rules), "plan_id": plan.id if plan else None, "content_revision": plan.content_revision if plan else None,
        "checks": [], "documents": [], "exceptions": [], "history": []}
    if not rules or not plan or plan.status != "FINAL":
        active = related_exceptions(db, load)
        result["exceptions"] = [public_exception(e, load) for e in active]
        result["documents"] = [row_data(d) for d in db.scalars(select(OperationalDocument).where(or_(OperationalDocument.load_id == load.id, OperationalDocument.outbound_id.in_(select(OutboundOrder.id).where(OutboundOrder.load_id == load.id)))))]
        for kind in KINDS:
            blocked = kind == "EXCEPTIONS" and any(e.status in (ExceptionStatus.OPEN, ExceptionStatus.INVESTIGATING) for e in active)
            result["checks"].append({"kind": kind, "status": "BLOCKED" if blocked else "UNKNOWN", "reason": "ACTIVE_EXCEPTIONS" if blocked else ("FINAL_PLAN_NOT_LOCKED" if rules else UNKNOWN[kind]), "can_review": False, "roles": [r.value for r in getattr(rules, KINDS[kind][1]).roles] if rules else [], "missing": ["锁定计划缺失" if rules else "已批准且启用的业务规则缺失"]})
    else:
        # Dispatch changes order/reservation state. Historical reads must remain
        # available; writer validation and can_review still prohibit new authority.
        if load.status.value not in ("DISPATCHED", "COMPLETED"):
            validate_complete_plan(db, load, plan)
        sources, missing, docs, exceptions = snapshots(db, load, plan, rules)
        for kind in ("DOCUMENTS", "EXCEPTIONS", "APPROVAL"):
            if kind == "APPROVAL":
                previous = result["checks"]
                sources[kind]["reviews"] = [{"kind": c["kind"], "review": c["review"]} for c in previous]
                missing[kind] = [f"{c['kind']}:{c['reason']}" for c in previous if c["status"] != "PASS"]
            c = review_status(db, load, plan, p, rules, kind, sources[kind], missing[kind])
            rule = getattr(rules, KINDS[kind][1]); c["roles"] = [r.value for r in rule.roles]
            c["can_review"] = load.status.value in ("PLANNED", "READY") and user is not None and actor_allowed(db, user.id, load, plan, rule, kind == "APPROVAL" and rules.independent_approver)
            result["checks"].append(c)
        result["documents"] = [row_data(d) for d in docs]
        result["exceptions"] = [public_exception(e, load, events=True) for e in exceptions]
    result["history"] = [row_data(r) for r in db.scalars(select(DispatchEvidenceReview).where(DispatchEvidenceReview.load_id == load.id).order_by(DispatchEvidenceReview.id.desc()))]
    return result


def write_review(db, user, load_id, payload):
    try:
        evidence_lock(db); operation_lock(db, "dispatch-review:", payload.operation_id)
        load = scoped_load(db, user, load_id, True)
        prior = db.scalar(select(DispatchEvidenceReview).where(DispatchEvidenceReview.operation_id == payload.operation_id))
        if prior:
            if (prior.load_id, prior.actor_id, prior.kind, prior.decision, prior.plan_id, prior.content_revision, prior.fingerprint, prior.note) != (load_id, user.id, payload.kind, payload.decision, payload.plan_id, payload.content_revision, payload.expected_fingerprint, payload.note.strip()): raise HTTPException(409, "OPERATION_ID_CONFLICT")
            return row_data(prior)
        view = evidence_view(db, user, load_id)
        if not view["configured"]: raise HTTPException(409, "EVIDENCE_RULES_NOT_CONFIGURED")
        if (view["plan_id"], view["content_revision"]) != (payload.plan_id, payload.content_revision): raise HTTPException(409, "PLAN_REVISION_CONFLICT")
        c = next(c for c in view["checks"] if c["kind"] == payload.kind)
        if not c["can_review"]: raise HTTPException(403, "EVIDENCE_REVIEW_PERMISSION_REQUIRED")
        if c["fingerprint"] != payload.expected_fingerprint: raise HTTPException(409, "EVIDENCE_STALE")
        if payload.decision == "ACCEPT" and c["missing"]: raise HTTPException(409, {"reason": "EVIDENCE_SOURCE_INCOMPLETE", "missing": c["missing"]})
        p, rules = policy(db, load); plan = latest_plan(db, load.id)
        sources, _, _, _ = snapshots(db, load, plan, rules)
        if payload.kind == "APPROVAL": sources["APPROVAL"]["reviews"] = [{"kind": x["kind"], "review": x["review"]} for x in view["checks"] if x["kind"] != "APPROVAL"]
        now = datetime.now(timezone.utc)
        r = DispatchEvidenceReview(load_id=load.id, plan_id=plan.id, content_revision=plan.content_revision, policy_id=p.id,
            kind=payload.kind, decision=payload.decision, actor_id=user.id, operation_id=payload.operation_id, note=payload.note.strip(),
            fingerprint=c["fingerprint"], snapshot=sources[payload.kind], created_at=now,
            expires_at=now + timedelta(seconds=getattr(rules, KINDS[payload.kind][1]).valid_seconds))
        if not r.note: raise HTTPException(422, "REVIEW_NOTE_REQUIRED")
        db.add(r); db.flush()
        db.add(AuditLog(user_id=user.id, action="DISPATCH_EVIDENCE_REVIEW", entity_type="load", entity_id=load.id,
            after_data={"review_id": r.id, "kind": r.kind, "decision": r.decision, "plan_id": r.plan_id, "revision": r.content_revision, "policy_id": r.policy_id, "fingerprint": r.fingerprint}))
        db.commit(); return row_data(r)
    except Exception:
        db.rollback(); raise


def checks(db, load):
    from app.services.load_dispatch_gate import check
    view = evidence_view(db, None, load.id, internal_load=load)
    return [check(KINDS[c["kind"]][0], c["status"], c["reason"].split(";")[0], c["reason"],
        [f"review:{c['review']['id']}" ] if c.get("review") else [], c.get("missing", [])) for c in view["checks"]]
