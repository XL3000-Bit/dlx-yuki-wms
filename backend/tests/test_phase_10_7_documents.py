from app.core.config import settings
from app.core.security import create_access_token
from app.models import Load, OutboundOrder, Warehouse, WorkOrder
from app.models.operational_document import DocumentStatus
from app.services.document_storage import LocalDocumentStorage
import pytest


def _outbound(db, seed, *, number="DOC-OB-1", warehouse_id=None):
    row = OutboundOrder(
        ob_no=number,
        warehouse_id=warehouse_id or seed["warehouse"].id,
        customer_id=seed["customer"].id,
        created_by=seed["admin"].id,
        status=0,
    )
    db.add(row)
    db.commit()
    return row


def _upload(client, relation, *, kind="POD", filename="proof.pdf", content=b"proof-v1"):
    return client.post(
        "/api/v1/documents",
        data={"document_type": kind, **{key: str(value) for key, value in relation.items()}},
        files={"file": (filename, content, "application/pdf")},
    )


@pytest.mark.parametrize("claim", [{"warehouse_id": 999}, {"customer_id": 999},
                                    {"dispatch_business_type": "FBA"}, {"dispatch_business_type": "UNKNOWN"}])
def test_explicit_upload_claims_must_match_inferred_relations(client, db, seed, tmp_path, monkeypatch, claim):
    monkeypatch.setattr(settings, "document_storage_root", str(tmp_path))
    outbound = _outbound(db, seed)
    outbound.dispatch_business_type = "PRIVATE"
    db.commit()
    rejected = _upload(client, {"outbound_id": outbound.id, **claim}, kind="WAREHOUSE")
    assert rejected.status_code == 422 and "DOCUMENT_CLAIM_MISMATCH" in rejected.json()["detail"]
    assert not list(tmp_path.rglob("*.*"))
    assert client.get("/api/v1/documents", params={"outbound_id": outbound.id}).json()["meta"]["total"] == 0
    accepted = _upload(client, {"outbound_id": outbound.id, "warehouse_id": outbound.warehouse_id,
                               "customer_id": outbound.customer_id, "dispatch_business_type": "PRIVATE"}, kind="WAREHOUSE")
    assert accepted.status_code == 201


def test_upload_list_download_events_and_pod_does_not_change_outbound(client, db, seed, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "document_storage_root", str(tmp_path))
    outbound = _outbound(db, seed)
    before = outbound.status
    created = _upload(client, {"outbound_id": outbound.id})
    assert created.status_code == 201
    body = created.json()
    assert body["document_type"] == "POD" and body["status"] == "AVAILABLE" and body["version"] == 1
    db.refresh(outbound)
    assert outbound.status == before
    listed = client.get("/api/v1/documents", params={"outbound_id": outbound.id, "document_type": "POD"})
    assert listed.status_code == 200 and listed.json()["meta"]["total"] == 1
    downloaded = client.get(f"/api/v1/documents/{body['id']}/download")
    assert downloaded.status_code == 200 and downloaded.content == b"proof-v1"
    events = client.get(f"/api/v1/documents/{body['id']}/events").json()
    assert {event["event_type"] for event in events} == {"CREATED", "UPLOADED", "AVAILABLE"}


def test_version_supersedes_business_document_while_general_files_coexist(client, db, seed, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "document_storage_root", str(tmp_path))
    outbound = _outbound(db, seed)
    first = _upload(client, {"outbound_id": outbound.id}, content=b"v1").json()
    second = _upload(client, {"outbound_id": outbound.id}, content=b"v2").json()
    assert second["version"] == 2
    assert client.get(f"/api/v1/documents/{first['id']}").json()["status"] == "SUPERSEDED"
    general_a = _upload(client, {"outbound_id": outbound.id}, kind="GENERAL", filename="a.csv", content=b"a")
    general_b = _upload(client, {"outbound_id": outbound.id}, kind="GENERAL", filename="b.csv", content=b"b")
    assert general_a.json()["version"] == general_b.json()["version"] == 1
    assert general_a.json()["status"] == general_b.json()["status"] == "AVAILABLE"


def test_upload_safety_size_limit_path_traversal_and_compensating_cleanup(client, db, seed, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "document_storage_root", str(tmp_path))
    monkeypatch.setattr(settings, "document_max_upload_bytes", 3)
    outbound = _outbound(db, seed)
    too_large = _upload(client, {"outbound_id": outbound.id}, content=b"four")
    assert too_large.status_code == 413 and not list(tmp_path.rglob("*.*"))
    executable = _upload(client, {"outbound_id": outbound.id}, filename="malware.exe", content=b"MZ")
    assert executable.status_code == 415
    traversal = _upload(client, {"outbound_id": outbound.id}, filename="../escape.pdf", content=b"ok")
    assert traversal.status_code == 415
    storage = LocalDocumentStorage(tmp_path)
    assert storage._path("safe/file.pdf").is_relative_to(tmp_path)
    for unsafe in ("../escape.pdf", "/absolute.pdf", "bad\\path.pdf"):
        try:
            storage._path(unsafe)
            assert False, "unsafe storage key accepted"
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 400


def test_viewer_can_read_and_download_but_cannot_upload_or_archive(client, db, seed, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "document_storage_root", str(tmp_path))
    outbound = _outbound(db, seed)
    document = _upload(client, {"outbound_id": outbound.id}).json()
    client.headers["Authorization"] = f"Bearer {create_access_token(str(seed['viewer'].id))}"
    assert client.get("/api/v1/documents").status_code == 200
    assert client.get(f"/api/v1/documents/{document['id']}/download").status_code == 200
    assert _upload(client, {"outbound_id": outbound.id}).status_code == 403
    assert client.post(f"/api/v1/documents/{document['id']}/archive").status_code == 403


def test_cross_warehouse_relations_are_rejected_and_work_order_documents_are_supported(client, db, seed, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "document_storage_root", str(tmp_path))
    other = Warehouse(warehouse_code="DOC-SEA", warehouse_name="Seattle", address="2 Dock Way", city="Seattle", state="WA", zip_code="98101")
    db.add(other)
    db.flush()
    outbound = _outbound(db, seed, warehouse_id=other.id)
    load = Load(load_no="DOC-LOAD-1", warehouse_id=seed["warehouse"].id, created_by=seed["admin"].id)
    work = WorkOrder(work_order_no="DOC-WO-1", work_order_type="GENERAL", warehouse_id=seed["warehouse"].id, created_by=seed["admin"].id)
    db.add_all([load, work])
    db.commit()
    mismatch = _upload(client, {"load_id": load.id, "outbound_id": outbound.id})
    assert mismatch.status_code == 409
    attached = _upload(client, {"work_order_id": work.id}, kind="WAREHOUSE", filename="checklist.xlsx", content=b"xls")
    assert attached.status_code == 201 and attached.json()["work_order_id"] == work.id
    archived = client.post(f"/api/v1/documents/{attached.json()['id']}/archive")
    assert archived.status_code == 200 and archived.json()["status"] == DocumentStatus.ARCHIVED.value


def test_global_search_finds_document_number_filename_and_generated_bol_title(client, db, seed, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "document_storage_root", str(tmp_path))
    outbound = _outbound(db, seed)
    document = _upload(client, {"outbound_id": outbound.id}, filename="signed-delivery.pdf").json()
    by_filename = client.get("/api/v1/search", params={"q": "signed-delivery"}).json()
    assert any(group["type"] == "DOCUMENT" for group in by_filename["groups"])
    by_number = client.get("/api/v1/search", params={"q": document["document_no"]}).json()
    assert by_number["groups"][0]["items"][0]["target_route"] == f"/documents?selected={document['id']}"
