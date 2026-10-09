from pathlib import Path

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession
from app.models import OperationalDocument
from app.models.operational_document import DocumentEvent, DocumentStatus, DocumentType
from app.schemas.operational_document import DocumentEventRead, DocumentRead
from app.services.document_storage import LocalDocumentStorage
from app.services.operational_document import archive_document, get_document, scoped_documents, upload_document
from app.services.picking_bol import bol_pdf

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("")
def list_documents(db: DbSession, user: CurrentUser, q: str | None = None, document_type: DocumentType | None = None,
                   status: DocumentStatus | None = None, warehouse_id: int | None = None, customer_id: int | None = None,
                   inbound_id: int | None = None, load_id: int | None = None, outbound_id: int | None = None, bol_id: int | None = None,
                   work_order_id: int | None = None, operational_exception_id: int | None = None,
                   page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100)):
    filters = []
    if q:
        term = f"%{q.strip()}%"; filters.append(or_(OperationalDocument.document_no.ilike(term), OperationalDocument.original_filename.ilike(term), OperationalDocument.title.ilike(term)))
    for field, value in (("document_type", document_type), ("status", status), ("warehouse_id", warehouse_id), ("customer_id", customer_id),
                         ("inbound_id", inbound_id), ("load_id", load_id), ("outbound_id", outbound_id), ("bol_id", bol_id), ("work_order_id", work_order_id),
                         ("operational_exception_id", operational_exception_id)):
        if value is not None: filters.append(getattr(OperationalDocument, field) == value)
    base = scoped_documents(select(OperationalDocument).where(*filters), user)
    count = scoped_documents(select(func.count()).select_from(OperationalDocument).where(*filters), user)
    total = db.scalar(count) or 0
    rows = db.scalars(base.order_by(OperationalDocument.created_at.desc(), OperationalDocument.id.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    return {"data": [DocumentRead.model_validate(row) for row in rows], "meta": {"page": page, "per_page": per_page, "total": total, "total_pages": (total + per_page - 1) // per_page}}


@router.post("", response_model=DocumentRead, status_code=201)
def upload(db: DbSession, user: CurrentUser, file: UploadFile = File(...), document_type: DocumentType = Form(...),
           inbound_id: int | None = Form(None), title: str | None = Form(None), notes: str | None = Form(None), load_id: int | None = Form(None),
           outbound_id: int | None = Form(None), bol_id: int | None = Form(None), work_order_id: int | None = Form(None),
           operational_exception_id: int | None = Form(None), container_tracking_id: int | None = Form(None),
           warehouse_id: int | None = Form(None), customer_id: int | None = Form(None), dispatch_business_type: str | None = Form(None)):
    links = {"inbound_id": inbound_id, "load_id": load_id, "outbound_id": outbound_id, "bol_id": bol_id, "work_order_id": work_order_id,
             "operational_exception_id": operational_exception_id, "container_tracking_id": container_tracking_id}
    return upload_document(db, user, file, document_type, links, title, notes,
                           claimed_warehouse_id=warehouse_id, claimed_customer_id=customer_id,
                           claimed_business_type=dispatch_business_type)


@router.get("/{document_id}", response_model=DocumentRead)
def detail(document_id: int, db: DbSession, user: CurrentUser): return get_document(db, user, document_id)


@router.get("/{document_id}/events", response_model=list[DocumentEventRead])
def events(document_id: int, db: DbSession, user: CurrentUser):
    get_document(db, user, document_id)
    return list(db.scalars(select(DocumentEvent).where(DocumentEvent.document_id == document_id).order_by(DocumentEvent.created_at.desc(), DocumentEvent.id.desc())).all())


@router.get("/{document_id}/download")
def download(document_id: int, db: DbSession, user: CurrentUser):
    document = get_document(db, user, document_id)
    safe_name = Path(document.original_filename).name.replace('"', "")
    headers = {"Content-Disposition": f'attachment; filename="{safe_name}"'}
    if document.is_generated and document.bol:
        return Response(bol_pdf(document.bol), media_type="application/pdf", headers=headers)
    storage = LocalDocumentStorage()
    if not document.storage_key or not storage.exists(document.storage_key):
        from fastapi import HTTPException
        raise HTTPException(404, "Document content not found")
    return FileResponse(storage._path(document.storage_key), media_type=document.content_type, filename=safe_name)


@router.post("/{document_id}/archive", response_model=DocumentRead)
def archive(document_id: int, db: DbSession, user: CurrentUser): return archive_document(db, user, get_document(db, user, document_id))
