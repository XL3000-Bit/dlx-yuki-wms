from datetime import datetime, timezone
from pathlib import Path
import re
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.models import BOL, ContainerTracking, Load, OperationalException, OperationalExceptionEvent, OutboundOrder, User, WorkOrder
from app.models.operational_document import DocumentEvent, DocumentStatus, DocumentType, OperationalDocument
from app.models.user import UserRole
from app.services.access import apply_warehouse_scope, ensure_warehouse_visible, ensure_warehouse_writable, get_access_scope
from app.services.file_storage import get_storage
from app.utils.business_time import get_business_today

ALLOWED_EXT = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}
BLOCKED_EXT = {".exe", ".bat", ".cmd", ".ps1", ".js", ".html", ".htm", ".msi", ".sh", ".com"}
VERSIONED_TYPES = {DocumentType.BOL, DocumentType.POD, DocumentType.DELIVERY_RECEIPT, DocumentType.WAREHOUSE}
OUTBOUND_DOC_TYPES = {DocumentType.BOL, DocumentType.POD, DocumentType.DELIVERY_RECEIPT}


def sanitize_filename(name: str) -> str:
    raw = Path(str(name or "file")).name
    raw = raw.replace("\\", "_").replace("/", "_")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip(".") or "file"
    return cleaned[:180]


def _ext(name: str) -> str:
    return Path(name).suffix.lower()


def validate_upload(filename: str, content: bytes, content_type: str | None = None) -> tuple[str, str]:
    safe = sanitize_filename(filename)
    ext = _ext(safe)
    if ext in BLOCKED_EXT or ext not in ALLOWED_EXT:
        raise HTTPException(422, "File type is not allowed")
    if len(content) > settings.document_max_bytes:
        raise HTTPException(422, "File exceeds maximum size")
    if not content:
        raise HTTPException(422, "Empty file is not allowed")
    mime = ALLOWED_EXT[ext]
    if content_type and content_type.split(";")[0].strip().lower() not in {mime, "application/octet-stream", "image/jpg"}:
        if ext not in {".jpg", ".jpeg", ".csv", ".xls"}:
            raise HTTPException(422, "MIME type does not match the file extension")
    return safe, mime


def generate_document_no(db) -> str:
    prefix = f"DOC-{get_business_today():%Y%m%d}-"
    last = db.scalar(select(func.max(OperationalDocument.document_no)).where(OperationalDocument.document_no.like(prefix + "%")))
    return f"{prefix}{(int(last[-4:]) + 1 if last else 1):04d}"


def _event(db, document, event_type, actor_id, message=None):
    db.add(DocumentEvent(document_id=document.id, event_type=event_type, actor_user_id=actor_id, message=message, created_at=datetime.now(timezone.utc)))


def document_query():
    return select(OperationalDocument).options(
        joinedload(OperationalDocument.warehouse),
        joinedload(OperationalDocument.uploader),
        joinedload(OperationalDocument.load),
        joinedload(OperationalDocument.outbound),
        joinedload(OperationalDocument.bol),
        joinedload(OperationalDocument.work_order),
        joinedload(OperationalDocument.exception),
        joinedload(OperationalDocument.container_tracking),
    )


def read_document(row: OperationalDocument) -> dict:
    refs = []
    if row.load: refs.append({"kind": "LOAD", "id": row.load.id, "label": row.load.load_no})
    if row.outbound: refs.append({"kind": "OUTBOUND", "id": row.outbound.id, "label": row.outbound.ob_no})
    if row.bol: refs.append({"kind": "BOL", "id": row.bol.id, "label": row.bol.bol_no})
    if row.work_order: refs.append({"kind": "WORK_ORDER", "id": row.work_order.id, "label": row.work_order.work_order_no})
    if row.exception: refs.append({"kind": "EXCEPTION", "id": row.exception.id, "label": row.exception.exception_no})
    if row.container_tracking: refs.append({"kind": "CONTAINER", "id": row.container_tracking.id, "label": row.container_tracking.container_number})
    pod = None
    if row.document_type == DocumentType.POD:
        pod = "RECEIVED" if row.status in (DocumentStatus.AVAILABLE, DocumentStatus.RECEIVED) else row.status.value
    return {
        "id": row.id, "document_no": row.document_no, "document_type": row.document_type.value, "status": row.status.value,
        "file_name": row.file_name, "original_file_name": row.original_file_name, "mime_type": row.mime_type,
        "file_size": row.file_size, "warehouse_id": row.warehouse_id,
        "warehouse_code": row.warehouse.warehouse_code if row.warehouse else None,
        "load_id": row.load_id, "outbound_id": row.outbound_id, "bol_id": row.bol_id,
        "work_order_id": row.work_order_id, "exception_id": row.exception_id, "container_tracking_id": row.container_tracking_id,
        "description": row.description, "version": row.version, "uploaded_by": row.uploaded_by,
        "uploader_name": row.uploader.display_name if row.uploader else None,
        "uploaded_at": row.uploaded_at, "created_at": row.created_at, "references": refs, "pod_status": pod,
    }


def _can_write(user, document_type: DocumentType) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    if document_type in OUTBOUND_DOC_TYPES:
        return user.role in {UserRole.MANAGER, UserRole.OUTBOUND, UserRole.WAREHOUSE}
    return user.role in {UserRole.MANAGER, UserRole.INBOUND, UserRole.WAREHOUSE}


def _load_parent(db, model, object_id, label):
    row = db.get(model, object_id)
    if not row:
        raise HTTPException(404, f"{label} not found")
    return row


def _resolve_parents(db, payload: dict):
    parents = {}
    mapping = {
        "load_id": (Load, "Load"),
        "outbound_id": (OutboundOrder, "Outbound order"),
        "bol_id": (BOL, "BOL"),
        "work_order_id": (WorkOrder, "Work order"),
        "exception_id": (OperationalException, "Operational exception"),
        "container_tracking_id": (ContainerTracking, "Container tracking"),
    }
    for field, (model, label) in mapping.items():
        value = payload.get(field)
        if value:
            parents[field] = _load_parent(db, model, int(value), label)
    if not parents:
        raise HTTPException(422, "At least one related operational object is required")
    warehouses = []
    for obj in parents.values():
        warehouse_id = getattr(obj, "warehouse_id", None)
        if warehouse_id:
            warehouses.append(warehouse_id)
    if len(set(warehouses)) > 1:
        raise HTTPException(409, "Related objects must belong to the same warehouse")
    warehouse_id = warehouses[0] if warehouses else payload.get("warehouse_id")
    if not warehouse_id:
        raise HTTPException(422, "Warehouse is required")
    load = parents.get("load_id")
    outbound = parents.get("outbound_id")
    bol = parents.get("bol_id")
    if load and outbound and outbound.load_id and outbound.load_id != load.id:
        raise HTTPException(409, "Outbound order does not belong to the related load")
    if outbound and bol and bol.outbound_order_id != outbound.id:
        raise HTTPException(409, "BOL does not belong to the related outbound order")
    return int(warehouse_id), parents


def _supersede_previous(db, document_type: DocumentType, parents: dict, actor_id):
    if document_type not in VERSIONED_TYPES:
        return 1
    stmt = select(OperationalDocument).where(
        OperationalDocument.document_type == document_type,
        OperationalDocument.status.in_([DocumentStatus.AVAILABLE, DocumentStatus.RECEIVED, DocumentStatus.PENDING]),
    )
    if "load_id" in parents:
        stmt = stmt.where(OperationalDocument.load_id == parents["load_id"].id)
    elif "outbound_id" in parents:
        stmt = stmt.where(OperationalDocument.outbound_id == parents["outbound_id"].id)
    elif "bol_id" in parents:
        stmt = stmt.where(OperationalDocument.bol_id == parents["bol_id"].id)
    elif "work_order_id" in parents:
        stmt = stmt.where(OperationalDocument.work_order_id == parents["work_order_id"].id)
    else:
        return 1
    previous = list(db.scalars(stmt).all())
    version = max((row.version for row in previous), default=0) + 1
    for row in previous:
        row.status = DocumentStatus.SUPERSEDED
        _event(db, row, "DOCUMENT_SUPERSEDED", actor_id, f"Superseded by version {version}")
    return version


def _persist_file(content: bytes, safe_name: str) -> str:
    storage = get_storage()
    day = get_business_today().strftime("%Y/%m/%d")
    key = f"{day}/{uuid.uuid4().hex}_{safe_name}"
    storage.save(key, content)
    return key


def create_document(db, user, *, filename: str, content: bytes, content_type: str | None, payload: dict):
    if not _can_write(user, DocumentType(payload["document_type"])):
        raise HTTPException(403, "Document write permission required")
    document_type = DocumentType(payload["document_type"])
    safe, mime = validate_upload(filename, content, content_type)
    warehouse_id, parents = _resolve_parents(db, payload)
    scope = get_access_scope(db, user)
    ensure_warehouse_writable(scope, warehouse_id, detail="Not found")
    status = DocumentStatus.RECEIVED if document_type == DocumentType.POD else DocumentStatus.AVAILABLE
    version = _supersede_previous(db, document_type, parents, user.id)
    key = _persist_file(content, safe)
    try:
        row = OperationalDocument(
            document_no=generate_document_no(db), document_type=document_type, status=status,
            file_name=safe, original_file_name=sanitize_filename(filename), mime_type=mime, file_size=len(content),
            storage_key=key, warehouse_id=warehouse_id,
            load_id=parents["load_id"].id if "load_id" in parents else None,
            outbound_id=parents["outbound_id"].id if "outbound_id" in parents else None,
            bol_id=parents["bol_id"].id if "bol_id" in parents else None,
            work_order_id=parents["work_order_id"].id if "work_order_id" in parents else None,
            exception_id=parents["exception_id"].id if "exception_id" in parents else None,
            container_tracking_id=parents["container_tracking_id"].id if "container_tracking_id" in parents else None,
            description=payload.get("description"), version=version, uploaded_by=user.id,
            uploaded_at=datetime.now(timezone.utc),
        )
        db.add(row); db.flush()
        _event(db, row, "DOCUMENT_CREATED", user.id, f"Created {row.document_no}")
        _event(db, row, "FILE_UPLOADED", user.id, safe)
        _event(db, row, "DOCUMENT_AVAILABLE" if status != DocumentStatus.RECEIVED else "DOCUMENT_AVAILABLE", user.id, status.value)
        if row.exception_id:
            db.add(OperationalExceptionEvent(
                operational_exception_id=row.exception_id, event_type="DOCUMENT_ATTACHED", actor_user_id=user.id,
                field_name="document", new_value=row.document_no, message=f"{row.document_type.value} {row.original_file_name}",
                created_at=datetime.now(timezone.utc),
            ))
        db.commit()
    except Exception:
        get_storage().delete(key)
        db.rollback()
        raise
    return get_document(db, row.id, user)


def get_document(db, document_id, user) -> OperationalDocument:
    row = db.scalar(document_query().where(OperationalDocument.id == document_id))
    if not row:
        raise HTTPException(404, "Document not found")
    ensure_warehouse_visible(get_access_scope(db, user), row.warehouse_id, detail="Document not found")
    return row


def list_documents(db, user, filters: dict, page=1, per_page=20):
    scope = get_access_scope(db, user)
    stmt = apply_warehouse_scope(document_query(), OperationalDocument.warehouse_id, scope)
    if filters.get("q"):
        needle = f"%{filters['q'].strip()}%"
        stmt = stmt.outerjoin(BOL, BOL.id == OperationalDocument.bol_id).where(or_(
            OperationalDocument.document_no.ilike(needle),
            OperationalDocument.file_name.ilike(needle),
            OperationalDocument.original_file_name.ilike(needle),
            BOL.bol_no.ilike(needle),
        ))
    if filters.get("document_type"):
        stmt = stmt.where(OperationalDocument.document_type == DocumentType(filters["document_type"]))
    if filters.get("status"):
        stmt = stmt.where(OperationalDocument.status == DocumentStatus(filters["status"]))
    if filters.get("warehouse_id"):
        ensure_warehouse_visible(scope, int(filters["warehouse_id"]), detail="Document not found")
        stmt = stmt.where(OperationalDocument.warehouse_id == int(filters["warehouse_id"]))
    for field in ("load_id", "outbound_id", "bol_id", "work_order_id", "exception_id", "container_tracking_id"):
        if filters.get(field):
            stmt = stmt.where(getattr(OperationalDocument, field) == int(filters[field]))
    rows = list(db.scalars(stmt.order_by(OperationalDocument.id.desc())).unique())
    total = len(rows)
    page_rows = rows[(page - 1) * per_page:page * per_page]
    return {"data": [read_document(row) for row in page_rows], "meta": {"page": page, "per_page": per_page, "total": total, "total_pages": (total + per_page - 1) // per_page or 1}}


def archive_document(db, document_id, user):
    row = get_document(db, document_id, user)
    if not _can_write(user, row.document_type):
        raise HTTPException(403, "Document write permission required")
    ensure_warehouse_writable(get_access_scope(db, user), row.warehouse_id, detail="Document not found")
    if row.status == DocumentStatus.ARCHIVED:
        return row
    row.status = DocumentStatus.ARCHIVED
    _event(db, row, "DOCUMENT_ARCHIVED", user.id, "Archived")
    db.commit()
    return get_document(db, row.id, user)


def download_path(db, document_id, user):
    row = get_document(db, document_id, user)
    storage = get_storage()
    if not storage.exists(row.storage_key):
        raise HTTPException(404, "File not found")
    return row, storage.open(row.storage_key)


def register_generated_bol(db, bol: BOL, user_id: int, content: bytes):
    existing = db.scalar(select(OperationalDocument).where(
        OperationalDocument.bol_id == bol.id,
        OperationalDocument.document_type == DocumentType.BOL,
        OperationalDocument.status.in_([DocumentStatus.AVAILABLE, DocumentStatus.RECEIVED]),
    ))
    if existing:
        return existing
    user = db.get(User, user_id)
    payload = {"document_type": DocumentType.BOL.value, "bol_id": bol.id, "outbound_id": bol.outbound_order_id, "warehouse_id": bol.warehouse_id}
    if user is None:
        return None
    return create_document(db, user, filename=f"{bol.bol_no}.pdf", content=content, content_type="application/pdf", payload=payload)
