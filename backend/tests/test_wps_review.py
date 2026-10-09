import json
from types import SimpleNamespace
import pytest
from sqlalchemy import select, func
from app.api.v1.endpoints import wps_review
from app.core.security import create_access_token
from app.models.customer import Customer
from app.models.inbound import InboundRecord
from app.services.wps_review import review, reconcile


def row(id="1", cartons="10", customer="ACME", location=None):
    return {"sourceIdentity": {"documentId": "doc", "sheetId": "sheet", "recordId": id},
            "values": {"container_number": "TEST123", "carton_qty": cartons, "customer": customer,
                       "location_candidates": location or ["A01"]}, "issues": [], "rawFields": {}}


def snapshot(name, rows, complete=True):
    return {"mode": "normalized_preview_only", "customerScope": "all", "sheet": name,
            "complete": complete, "rows": rows, "missingFields": []}


@pytest.mark.parametrize("ol,inbound,complete,status,difference", [
    ([row(cartons="4"), row("2", "6")], [row()], True, "matched", "0"),
    ([row(cartons="4")], [row()], True, "difference", "-6"),
    ([row()], [row()], False, "partial_snapshot", "0"),
    ([row(cartons=None)], [row()], True, "missing_quantity", None),
    ([row(cartons="NaN")], [row()], True, "missing_quantity", None),
    ([row()], [row(), row("2")], True, "ambiguous_inbound", None),
    ([row()], [], False, "missing_counterpart", None),
    ([row(cartons="0")], [row(cartons="0")], True, "matched", "0"),
])
def test_quantity_reconciliation(ol, inbound, complete, status, difference):
    result = reconcile([snapshot("OL", ol, complete), snapshot("提柜", inbound, complete)])[0]
    assert result["status"] == status
    assert result["difference"] == difference


def test_mapping_all_customers_and_warehouse_scoped_locations():
    customers = [SimpleNamespace(id=1, customer_code="ACME", customer_name="One", is_active=True),
                 SimpleNamespace(id=2, customer_code="OTHER", customer_name="ACME", is_active=True)]
    locations = [SimpleNamespace(warehouse_id=2, location_code="A01", is_active=True)]
    sheets = [snapshot("OL", [row(), row("2", customer="NEW")])]
    result = review(sheets, customers, locations, 1)
    assert len(result["sheets"][0]["rows"]) == 2
    assert result["sheets"][0]["rows"][0]["customerMatchStatus"] == "ambiguous"
    assert result["sheets"][0]["rows"][0]["unknownLocations"] == ["A01"]
    assert "key" not in sheets[0]["rows"][0]  # never mutate source
    result = review(sheets, customers, locations, 2, {"doc:sheet:1": 1})
    assert result["sheets"][0]["rows"][0]["customerMatchStatus"] == "manual"
    assert result["sheets"][0]["rows"][0]["locationStatus"] == "matched"
    with pytest.raises(ValueError):
        review(sheets, customers, locations, 2, {"doc:sheet:1": 999})


def write_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(wps_review, "SNAPSHOT_DIR", tmp_path)
    for sheet, filename in [("OL", "ol-normalized.json"), ("提柜", "inbound-normalized.json")]:
        (tmp_path / filename).write_text(json.dumps(snapshot(sheet, [row()], False)), encoding="utf-8")


def test_api_preview_no_write(client, db, seed, tmp_path, monkeypatch):
    write_snapshots(tmp_path, monkeypatch)
    record = InboundRecord(inbound_no="IB-TEST", container_number="TEST123",
                           warehouse_id=seed["warehouse"].id, created_by=seed["admin"].id,
                           carton_qty=12, raw_location_text="A01")
    db.add(record)
    db.commit()
    count = db.scalar(select(func.count()).select_from(Customer))
    result = client.post("/api/v1/wps/review", json={"warehouse_id": seed["warehouse"].id})
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["databaseWritten"] is False
    assert data["duplicateSummary"]["importAllowed"] is False
    assert data["sheets"][0]["rows"][0]["duplicateCheck"]["candidateCount"] == 1
    assert db.scalar(select(func.count()).select_from(InboundRecord)) == 1
    db.refresh(record)
    assert record.carton_qty == 12
    assert record.raw_location_text == "A01"
    assert data["sheets"][0]["rows"][0]["customerId"] == seed["customer"].id
    assert data["sheets"][0]["rows"][0]["locationStatus"] == "matched"
    assert data["reconciliation"][0]["status"] == "partial_snapshot"
    assert db.scalar(select(func.count()).select_from(Customer)) == count
    assert client.post("/api/v1/wps/review", json={"warehouse_id": 99999}).status_code == 422


def test_api_access_and_missing_snapshot(client, seed, tmp_path, monkeypatch):
    monkeypatch.setattr(wps_review, "SNAPSHOT_DIR", tmp_path)
    assert client.post("/api/v1/wps/review", json={}).status_code == 409
    client.headers["Authorization"] = f"Bearer {create_access_token(str(seed['viewer'].id))}"
    assert client.post("/api/v1/wps/review", json={}).status_code == 403
    client.headers.pop("Authorization")
    assert client.post("/api/v1/wps/review", json={}).status_code == 401
