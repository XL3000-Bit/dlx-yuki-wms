from datetime import date
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from app.api.deps import CurrentUser, DbSession
from app.services.operational_document import archive_document, download_path, get_document, list_documents, create_document, read_document

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("")
def list_docs(
    db: DbSession,
    user: CurrentUser,
    q: str | None = None,
    document_type: str | None = None,
    status: str | None = None,
    warehouse_id: int | None = None,
    load_id: int | None = None,
    outbound_id: int | None = None,
    bol_id: int | None = None,
    work_order_id: int | None = None,
    exception_id: int | None = None,
    container_tracking_id: int | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    return list_documents(db, user, {
        "q": q, "document_type": document_type, "status": status, "warehouse_id": warehouse_id,
        "load_id": load_id, "outbound_id": outbound_id, "bol_id": bol_id, "work_order_id": work_order_id,
        "exception_id": exception_id, "container_tracking_id": container_tracking_id,
    }, page=page, per_page=per_page)


@router.get("/{document_id}")
def detail(document_id: int, db: DbSession, user: CurrentUser):
    return read_document(get_document(db, document_id, user))


@router.get("/{document_id}/events")
def events(document_id: int, db: DbSession, user: CurrentUser):
    row = get_document(db, document_id, user)
    return {"data": [{"id": e.id, "event_type": e.event_type, "actor_user_id": e.actor_user_id, "actor_name": e.actor.display_name if e.actor else "System", "message": e.message, "created_at": e.created_at} for e in row.events]}


@router.get("/{document_id}/download")
def download(document_id: int, db: DbSession, user: CurrentUser):
    row, path = download_path(db, document_id, user)
    return FileResponse(path, media_type=row.mime_type, filename=row.original_file_name)


@router.post("/upload", status_code=201)
async def upload(
    db: DbSession,
    user: CurrentUser,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    description: str | None = Form(None),
    warehouse_id: int | None = Form(None),
    load_id: int | None = Form(None),
    outbound_id: int | None = Form(None),
    bol_id: int | None = Form(None),
    work_order_id: int | None = Form(None),
    exception_id: int | None = Form(None),
    container_tracking_id: int | None = Form(None),
):
    content = await file.read()
    row = create_document(db, user, filename=file.filename or "file", content=content, content_type=file.content_type, payload={
        "document_type": document_type, "description": description, "warehouse_id": warehouse_id,
        "load_id": load_id, "outbound_id": outbound_id, "bol_id": bol_id, "work_order_id": work_order_id,
        "exception_id": exception_id, "container_tracking_id": container_tracking_id,
    })
    return read_document(row)


@router.post("/{document_id}/archive")
def archive(document_id: int, db: DbSession, user: CurrentUser):
    return read_document(archive_document(db, document_id, user))
