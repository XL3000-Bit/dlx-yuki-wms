from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import InboundRecord, BOL, ContainerTracking, Load, OperationalDocument, OperationalException, OutboundOrder, WorkOrder
from app.models.operational_document import DocumentEvent, DocumentStatus, DocumentType
from app.models.user import User, UserRole
from app.services.access_policy import assert_customer_access, assert_warehouse_access, customer_clause, warehouse_clause
from app.services.document_storage import LocalDocumentStorage

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv", ".jpg", ".jpeg", ".png"}
COEXISTING_TYPES = {DocumentType.GENERAL, DocumentType.EXCEPTION_ATTACHMENT}


def scoped_documents(stmt, user: User):
    for clause in (warehouse_clause(user, OperationalDocument.warehouse_id), customer_clause(user, OperationalDocument.customer_id)):
        if clause is not None: stmt = stmt.where(clause)
    return stmt


def get_document(db: Session, user: User, document_id: int) -> OperationalDocument:
    row = db.scalar(scoped_documents(select(OperationalDocument).where(OperationalDocument.id == document_id), user))
    if row is None: raise HTTPException(404, "Document not found")
    return row


def assert_write(user: User, *, outbound_related: bool) -> None:
    allowed = {UserRole.ADMIN, UserRole.MANAGER, UserRole.WAREHOUSE, UserRole.OUTBOUND if outbound_related else UserRole.INBOUND}
    if user.role not in allowed: raise HTTPException(403, "Document write permission required")


def resolve_links(db: Session, user: User, links: dict) -> tuple[int, int | None, bool]:
    models = {"inbound_id": InboundRecord, "load_id": Load, "outbound_id": OutboundOrder, "bol_id": BOL, "work_order_id": WorkOrder,
              "operational_exception_id": OperationalException, "container_tracking_id": ContainerTracking}
    if not any(links.values()): raise HTTPException(422, "At least one business relation is required")
    warehouses = set(); customers = set(); outbound_related = False
    for field, model in models.items():
        value = links.get(field)
        if value is None: continue
        record = db.get(model, value)
        if record is None: raise HTTPException(422, f"Invalid {field}")
        warehouses.add(record.warehouse_id)
        customer_id = getattr(record, "customer_id", None)
        if customer_id: customers.add(customer_id)
        outbound_related |= field in {"outbound_id", "bol_id", "load_id"}
        if field == "work_order_id" and record.outbound_id: outbound_related = True
    if len(warehouses) != 1: raise HTTPException(409, "All document relations must belong to the same warehouse")
    if len(customers) > 1: raise HTTPException(409, "All document relations must belong to the same customer")
    warehouse_id = warehouses.pop(); customer_id = next(iter(customers), None)
    assert_warehouse_access(user, warehouse_id); assert_customer_access(user, customer_id); assert_write(user, outbound_related=outbound_related)
    return warehouse_id, customer_id, outbound_related


def dispatch_domain(db, user, links):
    from app.services.load_dispatch_write import scoped_load
    load = scoped_load(db, user, links["load_id"]) if links.get("load_id") else None
    orders = []
    if links.get("outbound_id"): orders.append(db.get(OutboundOrder, links["outbound_id"]))
    if links.get("bol_id"):
        bol = db.get(BOL, links["bol_id"])
        if not bol: raise HTTPException(422, "Invalid bol_id")
        if links.get("outbound_id") and bol.outbound_order_id != links["outbound_id"]: raise HTTPException(409, "DOCUMENT_ORDER_MISMATCH")
        orders.append(db.get(OutboundOrder, bol.outbound_order_id))
    domains = {load.dispatch_business_type} if load else set()
    for order in orders:
        if not order: raise HTTPException(422, "Invalid outbound relation")
        assert_warehouse_access(user, order.warehouse_id); assert_customer_access(user, order.customer_id)
        if load and order.load_id != load.id: raise HTTPException(409, "DOCUMENT_LOAD_MEMBERSHIP_MISMATCH")
        if order.dispatch_business_type: domains.add(order.dispatch_business_type)
    if len(domains) > 1: raise HTTPException(409, "DOCUMENT_BUSINESS_MISMATCH")
    return next(iter(domains), None)


def _event(document: OperationalDocument, kind: str, user_id: int | None, message: str | None = None):
    document.events.append(DocumentEvent(event_type=kind, actor_user_id=user_id, message=message, created_at=datetime.now(UTC)))


def upload_document(db: Session, user: User, upload: UploadFile, document_type: DocumentType, links: dict,
                    title: str | None = None, notes: str | None = None, storage: LocalDocumentStorage | None = None, commit: bool = True,
                    *, claimed_warehouse_id: int | None = None, claimed_customer_id: int | None = None,
                    claimed_business_type: str | None = None):
    from app.services.dispatch_evidence import evidence_lock
    evidence_lock(db)
    filename = Path(upload.filename or "").name
    if not filename or filename != upload.filename or Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Unsupported or unsafe document filename")
    warehouse_id, customer_id, _ = resolve_links(db, user, links)
    domain = dispatch_domain(db, user, links)
    for field, claimed, actual in (("warehouse_id", claimed_warehouse_id, warehouse_id),
                                   ("customer_id", claimed_customer_id, customer_id),
                                   ("dispatch_business_type", claimed_business_type, domain)):
        if claimed is not None and claimed != actual:
            raise HTTPException(422, f"DOCUMENT_CLAIM_MISMATCH: {field} does not match business relations")
    storage = storage or LocalDocumentStorage(); key = f"{datetime.now(UTC):%Y/%m}/{uuid4().hex}{Path(filename).suffix.lower()}"
    size, checksum = storage.save(key, upload.file, settings.document_max_upload_bytes)
    try:
        group = [getattr(OperationalDocument, field) == links.get(field) for field in ("inbound_id", "load_id", "outbound_id", "bol_id", "work_order_id", "operational_exception_id", "container_tracking_id")]
        previous = None
        if document_type not in COEXISTING_TYPES:
            previous = db.scalar(select(OperationalDocument).where(OperationalDocument.document_type == document_type,
                OperationalDocument.status == DocumentStatus.AVAILABLE, and_(*group)).order_by(OperationalDocument.version.desc()))
        version = 1 if document_type in COEXISTING_TYPES else (db.scalar(select(func.max(OperationalDocument.version)).where(OperationalDocument.document_type == document_type, and_(*group))) or 0) + 1
        document = OperationalDocument(document_no=f"DOC-{datetime.now(UTC):%y%m%d}-{uuid4().hex[:8].upper()}", document_type=document_type,
            status=DocumentStatus.AVAILABLE, version=version, original_filename=filename, content_type=upload.content_type or "application/octet-stream",
            file_size=size, storage_key=key, checksum_sha256=checksum, title=title, notes=notes, warehouse_id=warehouse_id,
            customer_id=customer_id, dispatch_business_type=domain, created_by=user.id, **links)
        _event(document, "CREATED", user.id); _event(document, "UPLOADED", user.id, filename); _event(document, "AVAILABLE", user.id)
        if previous:
            previous.status = DocumentStatus.SUPERSEDED; _event(previous, "SUPERSEDED", user.id, f"Superseded by version {version}")
        db.add(document)
        if commit: db.commit()
        else: db.flush()
        db.refresh(document)
        return document
    except Exception:
        db.rollback(); storage.delete(key); raise


def archive_document(db: Session, user: User, document: OperationalDocument):
    from app.services.dispatch_evidence import evidence_lock
    evidence_lock(db)
    dispatch_domain(db, user, {"load_id": document.load_id, "outbound_id": document.outbound_id, "bol_id": document.bol_id})
    assert_write(user, outbound_related=bool(document.outbound_id or document.bol_id or document.load_id))
    if document.status == DocumentStatus.ARCHIVED: return document
    document.status = DocumentStatus.ARCHIVED; document.archived_at = datetime.now(UTC); document.archived_by = user.id
    _event(document, "ARCHIVED", user.id); db.commit(); db.refresh(document); return document


def register_generated_bol(db: Session, bol: BOL, user_id: int):
    from app.services.dispatch_evidence import evidence_lock
    evidence_lock(db)
    order = db.get(OutboundOrder, bol.outbound_order_id)
    current = db.scalar(select(OperationalDocument).where(OperationalDocument.bol_id == bol.id,
        OperationalDocument.document_type == DocumentType.BOL, OperationalDocument.status == DocumentStatus.AVAILABLE))
    if current: return current
    document = OperationalDocument(document_no=f"DOC-{datetime.now(UTC):%y%m%d}-{uuid4().hex[:8].upper()}", document_type=DocumentType.BOL,
        status=DocumentStatus.AVAILABLE, version=(db.scalar(select(func.max(OperationalDocument.version)).where(OperationalDocument.bol_id == bol.id, OperationalDocument.document_type == DocumentType.BOL)) or 0) + 1, original_filename=f"{bol.bol_no}.pdf", content_type="application/pdf", file_size=None,
        storage_key=None, checksum_sha256=None, is_generated=True, title=f"Bill of Lading {bol.bol_no}", warehouse_id=bol.warehouse_id,
        customer_id=bol.customer_id, dispatch_business_type=order.dispatch_business_type if order else None, outbound_id=bol.outbound_order_id, bol_id=bol.id, created_by=user_id)
    _event(document, "CREATED", user_id, "Registered generated BOL"); _event(document, "AVAILABLE", user_id)
    db.add(document)
    # Autoflush is disabled: expose this registration to repeated calls within
    # the same transaction, retaining one available version per generated BOL.
    db.flush()
    return document
