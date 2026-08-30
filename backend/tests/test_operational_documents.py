from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.api.deps import get_db
from app.models import Load, OperationalException, OutboundOrder, User, Warehouse, WorkOrder
from app.models.load import LoadStatus
from app.models.operational_exception import ExceptionSeverity, ExceptionStatus, ExceptionType
from app.models.user import ScopeMode
from app.models.user_scope import UserWarehouseScope
from app.models.work_order import WorkOrderPriority, WorkOrderStatus, WorkOrderType
from app.models.operational_document import DocumentStatus, DocumentType, OperationalDocument

PDF = b"%PDF-1.4 test document"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def auth_client(db, user):
    app.dependency_overrides.clear()
    def override():
        yield db
    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {create_access_token(str(user.id))}"
    return client


def make_warehouse(db, code):
    row = Warehouse(warehouse_code=code, warehouse_name=code, address="1 Way", city="Los Angeles", state="CA", zip_code="90001")
    db.add(row); db.commit(); db.refresh(row); return row


def restrict(db, user, warehouse):
    user.warehouse_scope_mode = ScopeMode.SELECTED
    db.add(UserWarehouseScope(user_id=user.id, warehouse_id=warehouse.id))
    db.commit(); db.refresh(user); return user


def seed_load(db, seed, warehouse=None):
    warehouse = warehouse or seed["warehouse"]
    load = Load(load_no=f"LD-DOC-{warehouse.id}", warehouse_id=warehouse.id, status=LoadStatus.READY, created_by=seed["admin"].id)
    db.add(load); db.commit(); db.refresh(load); return load


def seed_wo(db, seed, warehouse=None):
    warehouse = warehouse or seed["warehouse"]
    wo = WorkOrder(work_order_no=f"WO-DOC-{warehouse.id}", work_order_type=WorkOrderType.GENERAL, status=WorkOrderStatus.OPEN, warehouse_id=warehouse.id, priority=WorkOrderPriority.NORMAL, created_by=seed["admin"].id)
    db.add(wo); db.commit(); db.refresh(wo); return wo


def seed_ex(db, seed, load):
    exc = OperationalException(exception_no=f"EX-DOC-{load.id}", exception_type=ExceptionType.OUTBOUND, severity=ExceptionSeverity.HIGH, status=ExceptionStatus.OPEN, title="doc", description="doc", warehouse_id=load.warehouse_id, load_id=load.id, reported_at=datetime.now(timezone.utc), reported_by=seed["admin"].id)
    db.add(exc); db.commit(); db.refresh(exc); return exc


def upload(client, **fields):
    files = fields.pop("files", {"file": ("pod.pdf", PDF, "application/pdf")})
    return client.post("/api/v1/documents/upload", files=files, data=fields)


def test_upload_pdf_and_image(client, db, seed):
    load = seed_load(db, seed)
    pdf = upload(client, document_type="POD", load_id=str(load.id))
    assert pdf.status_code == 201
    assert pdf.json()["document_type"] == "POD"
    assert pdf.json()["pod_status"] == "RECEIVED"
    assert pdf.json()["version"] == 1
    png = upload(client, document_type="GENERAL", load_id=str(load.id), files={"file": ("photo.png", PNG, "image/png")})
    assert png.status_code == 201
    assert png.json()["document_type"] == "GENERAL"


def test_invalid_extension_and_path_traversal(client, db, seed):
    load = seed_load(db, seed)
    bad = upload(client, document_type="GENERAL", load_id=str(load.id), files={"file": ("virus.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 422
    traversal = upload(client, document_type="GENERAL", load_id=str(load.id), files={"file": ("../../etc/passwd.pdf", PDF, "application/pdf")})
    assert traversal.status_code == 201
    assert ".." not in traversal.json()["file_name"]
    assert traversal.json()["file_name"].endswith(".pdf")


def test_oversize_file(client, db, seed, monkeypatch):
    monkeypatch.setattr(settings, "document_max_bytes", 10)
    load = seed_load(db, seed)
    res = upload(client, document_type="GENERAL", load_id=str(load.id))
    assert res.status_code == 422


def test_download_and_unauthenticated(client, db, seed):
    load = seed_load(db, seed)
    created = upload(client, document_type="WAREHOUSE", load_id=str(load.id)).json()
    down = client.get(f"/api/v1/documents/{created['id']}/download")
    assert down.status_code == 200
    assert down.content.startswith(b"%PDF")
    assert TestClient(app).get(f"/api/v1/documents/{created['id']}/download").status_code == 401


def test_out_of_scope_download(client, db, seed):
    other = make_warehouse(db, "DLX-SFO")
    load = seed_load(db, seed, other)
    created = upload(client, document_type="GENERAL", load_id=str(load.id)).json()
    viewer = restrict(db, seed["viewer"], seed["warehouse"])
    scoped = auth_client(db, viewer)
    assert scoped.get(f"/api/v1/documents/{created['id']}").status_code == 404
    assert scoped.get(f"/api/v1/documents/{created['id']}/download").status_code == 404


def test_viewer_cannot_upload_or_archive(client, db, seed):
    load = seed_load(db, seed)
    created = upload(client, document_type="GENERAL", load_id=str(load.id)).json()
    viewer = auth_client(db, seed["viewer"])
    assert viewer.post("/api/v1/documents/upload", files={"file": ("a.pdf", PDF, "application/pdf")}, data={"document_type": "GENERAL", "load_id": str(load.id)}).status_code == 403
    assert viewer.post(f"/api/v1/documents/{created['id']}/archive").status_code == 403
    assert viewer.get("/api/v1/documents").status_code == 200
    assert viewer.get(f"/api/v1/documents/{created['id']}/download").status_code == 200


def test_version_increment_and_supersede(client, db, seed):
    load = seed_load(db, seed)
    first = upload(client, document_type="POD", load_id=str(load.id)).json()
    second = upload(client, document_type="POD", load_id=str(load.id), files={"file": ("pod2.pdf", PDF, "application/pdf")}).json()
    assert second["version"] == 2
    old = client.get(f"/api/v1/documents/{first['id']}").json()
    assert old["status"] == "SUPERSEDED"
    assert second["status"] in {"AVAILABLE", "RECEIVED"}


def test_multiple_exception_attachments(client, db, seed):
    load = seed_load(db, seed)
    exc = seed_ex(db, seed, load)
    a = upload(client, document_type="EXCEPTION_ATTACHMENT", exception_id=str(exc.id), files={"file": ("a.png", PNG, "image/png")})
    b = upload(client, document_type="EXCEPTION_ATTACHMENT", exception_id=str(exc.id), files={"file": ("b.png", PNG, "image/png")})
    assert a.status_code == 201 and b.status_code == 201
    listed = client.get("/api/v1/documents", params={"exception_id": exc.id}).json()
    assert listed["meta"]["total"] == 2
    events = client.get(f"/api/v1/operational-exceptions/{exc.id}/events").json()
    types = {row["event_type"] for row in events.get("data", events if isinstance(events, list) else [])}
    assert "DOCUMENT_ATTACHED" in types or any("DOCUMENT" in str(row) for row in (events.get("data") or []))


def test_archive_and_list_filters(client, db, seed):
    load = seed_load(db, seed)
    created = upload(client, document_type="WAREHOUSE", load_id=str(load.id)).json()
    archived = client.post(f"/api/v1/documents/{created['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"
    listed = client.get("/api/v1/documents", params={"q": created["document_no"][:8], "load_id": load.id}).json()
    assert listed["meta"]["total"] >= 1


def test_work_order_and_load_documents(client, db, seed):
    load = seed_load(db, seed)
    wo = seed_wo(db, seed)
    upload(client, document_type="WAREHOUSE", work_order_id=str(wo.id))
    upload(client, document_type="POD", load_id=str(load.id))
    assert client.get("/api/v1/documents", params={"work_order_id": wo.id}).json()["meta"]["total"] >= 1
    assert client.get("/api/v1/documents", params={"load_id": load.id}).json()["data"][0]["pod_status"] == "RECEIVED"


def test_global_search_document(client, db, seed):
    load = seed_load(db, seed)
    created = upload(client, document_type="GENERAL", load_id=str(load.id)).json()
    data = client.get("/api/v1/search", params={"q": created["document_no"][:8]}).json()
    types = {g["type"] for g in data["groups"]}
    assert "DOCUMENT" in types or data["total"] >= 0
    found = [item for g in data["groups"] for item in g["items"] if item["type"] == "DOCUMENT"]
    assert found


def test_requires_related_object(client, db, seed):
    res = upload(client, document_type="GENERAL")
    assert res.status_code == 422
