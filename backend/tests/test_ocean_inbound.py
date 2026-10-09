from decimal import Decimal

from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token
from app.models import AuditLog, InboundRecord
from app.models.user import ScopeMode


def planned(seed, **overrides):
    return dict(container_number="TGBU6046663", warehouse_id=seed["warehouse"].id,
                customer_id=seed["customer"].id, unload_date="2026-09-28", carton_qty=42,
                pallet_qty=2, status=0, **overrides)


def create(client, seed, **overrides):
    response = client.post("/api/v1/inbound", json=planned(seed, **overrides))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def line(seed, row_id, **overrides):
    return {"id": row_id, "version": 0, "received_qty": "42", "inbound_pallets": "2",
            "location_id": seed["location"].id, **overrides}


def save(client, anchor, lines, action="draft"):
    method = client.post if action == "confirm" else client.put
    return method(f"/api/v1/ocean-inbound/{anchor}/{action}", json={"lines": lines})


def test_draft_confirm_preserves_plan_and_does_not_create_inventory(client, db, seed):
    row_id = create(client, seed)
    draft = line(seed, row_id, received_qty="40", memo="Two cartons short")
    result = save(client, row_id, [draft])
    assert result.status_code == 200, result.text
    row = db.get(InboundRecord, row_id)
    assert row.carton_qty == 42 and row.status == 0 and row.inventory_lot is None
    result = save(client, row_id, [{**draft, "version": 1}], "confirm")
    assert result.status_code == 200, result.text
    data = result.json()["data"][0]
    assert Decimal(data["receipt"]["expected_qty"]) == 42
    assert Decimal(data["inbound"]["carton_qty"]) == 40
    assert data["inbound"]["status"] == 2 and not data["inbound"]["inventory_created"]
    assert not data["editable"] and data["cargo_bol_no"]
    assert {r.action for r in db.scalars(select(AuditLog).where(AuditLog.entity_id == row_id))} >= {"OCEAN_DRAFT", "OCEAN_RECEIVE"}
    assert save(client, row_id, [{**draft, "version": 2}], "confirm").status_code == 409


def test_batch_validation_is_atomic_and_versions_reject_stale_edits(client, db, seed):
    first, second = create(client, seed), create(client, seed)
    result = save(client, first, [line(seed, first), line(seed, second, received_qty="41")], "confirm")
    assert result.status_code == 422
    assert db.get(InboundRecord, first).status == 0
    assert not db.get(InboundRecord, first).source_metadata
    assert save(client, first, [line(seed, first), line(seed, first)]).status_code == 422
    assert save(client, first, [line(seed, first)]).status_code == 200
    assert save(client, first, [line(seed, first)]).status_code == 409


def test_existing_received_cargo_shows_actuals_read_only(client, db, seed):
    row_id = create(client, seed)
    row = db.get(InboundRecord, row_id)
    row.status = 2
    db.commit()
    result = client.get(f"/api/v1/ocean-inbound/{row_id}").json()
    data = result["data"][0]
    assert Decimal(data["receipt"]["received_qty"]) == 42
    assert Decimal(data["receipt"]["inbound_pallets"]) == 2
    assert not data["editable"]
    assert result["can_upload"]


def test_group_date_scope_and_viewer_protection(client, db, seed):
    first = create(client, seed)
    other = client.post("/api/v1/inbound", json={**planned(seed), "unload_date": "2026-09-29"}).json()["id"]
    result = client.get(f"/api/v1/ocean-inbound/{first}")
    assert [r["inbound"]["id"] for r in result.json()["data"]] == [first]
    assert save(client, first, [line(seed, other)]).status_code == 404
    client.headers["Authorization"] = f"Bearer {create_access_token(str(seed['viewer'].id))}"
    assert not client.get(f"/api/v1/ocean-inbound/{first}").json()["data"][0]["editable"]
    assert save(client, first, [line(seed, first)]).status_code == 403
    seed["viewer"].warehouse_scope_mode = ScopeMode.SELECTED
    db.commit()
    assert client.get(f"/api/v1/ocean-inbound/{first}").status_code == 404


def test_generic_edit_invalidates_draft_and_cannot_rewrite_confirmation(client, seed):
    row_id = create(client, seed)
    assert client.put(f"/api/v1/inbound/{row_id}", json={**planned(seed), "remark": "edited"}).status_code == 200
    assert save(client, row_id, [line(seed, row_id)]).status_code == 409
    assert save(client, row_id, [line(seed, row_id, version=1)], "confirm").status_code == 200
    assert client.put(f"/api/v1/inbound/{row_id}", json=planned(seed)).status_code == 409


def test_inactive_location_cannot_receive(client, db, seed):
    row_id = create(client, seed)
    seed["location"].is_active = False
    db.commit()
    assert save(client, row_id, [line(seed, row_id)], "confirm").status_code == 422


def test_inbound_attachments_versions_download_and_scope(client, db, seed, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "document_storage_root", str(tmp_path))
    row_id, second = create(client, seed), create(client, seed)
    def upload(content):
        return client.post("/api/v1/documents", data={"inbound_id": row_id, "document_type": "WAREHOUSE"},
                           files={"file": ("receipt.pdf", content, "application/pdf")})
    first = upload(b"v1")
    assert first.status_code == 201, first.text
    latest = upload(b"v2").json()
    assert latest["version"] == 2 and latest["inbound_id"] == row_id
    assert client.get("/api/v1/documents", params={"inbound_id": second}).json()["meta"]["total"] == 0
    assert client.get(f"/api/v1/documents/{latest['id']}/download").content == b"v2"
    seed["viewer"].customer_scope_mode = ScopeMode.SELECTED
    db.commit()
    client.headers["Authorization"] = f"Bearer {create_access_token(str(seed['viewer'].id))}"
    assert client.get(f"/api/v1/documents/{latest['id']}/download").status_code == 404
    assert client.get("/api/v1/documents", params={"inbound_id": row_id}).json()["meta"]["total"] == 0
