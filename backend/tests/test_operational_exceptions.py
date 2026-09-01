import re

from fastapi.testclient import TestClient

from app.main import app
from app.models import OutboundOrder


def make_outbound(db, seed, number="EX-OB-1"):
    row = OutboundOrder(ob_no=number, warehouse_id=seed["warehouse"].id,
        customer_id=seed["customer"].id, created_by=seed["admin"].id,
        status=0, po_number=None)
    db.add(row); db.commit()
    return row


def payload(seed, outbound, **overrides):
    values = {"exception_type":"OUTBOUND", "severity":"HIGH", "title":"Dock mismatch",
        "description":"Pallet labels do not match", "warehouse_id":seed["warehouse"].id,
        "outbound_id":outbound.id}
    values.update(overrides)
    return values


def test_crud_filters_events_resolution_and_global_search(client, db, seed):
    outbound = make_outbound(db, seed)
    created = client.post("/api/v1/operational-exceptions", json=payload(seed, outbound))
    assert created.status_code == 201
    data = created.json()
    assert re.fullmatch(r"EX-\d{8}-\d{4}", data["exception_no"])
    assert data["status"] == "OPEN" and data["related"]["outbound"]["label"] == outbound.ob_no
    assert data["created_at"] is not None
    assert data["updated_at"] is not None
    assert data["reported_at"] is not None
    listed = client.get("/api/v1/operational-exceptions", params={"status":"OPEN", "severity":"HIGH", "q":"Dock mismatch"}).json()
    assert listed["meta"]["total"] == 1 and listed["counts"]["OPEN"] == 1
    exception_id = data["id"]
    assert client.patch(f"/api/v1/operational-exceptions/{exception_id}", json={"severity":"CRITICAL", "description":"Escalated"}).status_code == 200
    assert client.post(f"/api/v1/operational-exceptions/{exception_id}/assign", json={"assigned_to":seed["admin"].id, "assigned_team":"Dock"}).status_code == 200
    assert client.post(f"/api/v1/operational-exceptions/{exception_id}/status", json={"status":"INVESTIGATING"}).status_code == 200
    assert client.post(f"/api/v1/operational-exceptions/{exception_id}/resolve", json={"resolution":"Labels replaced"}).json()["status"] == "RESOLVED"
    assert client.patch(f"/api/v1/operational-exceptions/{exception_id}", json={"description":"too late"}).status_code == 409
    events = client.get(f"/api/v1/operational-exceptions/{exception_id}/events", params={"order":"asc"}).json()
    assert events["total"] >= 6
    assert events["data"][0]["event_type"] == "EXCEPTION_CREATED"
    assert all(event["created_at"] is not None for event in events["data"])
    found = client.get("/api/v1/search", params={"q":data["exception_no"]}).json()
    assert any(group["type"] == "EXCEPTION" for group in found["groups"])


def test_dedup_validation_transition_and_auth(client, db, seed):
    outbound = make_outbound(db, seed)
    first = client.post("/api/v1/operational-exceptions", json=payload(seed, outbound))
    assert first.status_code == 201
    assert client.post("/api/v1/operational-exceptions", json=payload(seed, outbound, title="Same active issue")).status_code == 409
    assert client.post(f"/api/v1/operational-exceptions/{first.json()['id']}/resolve", json={"resolution":""}).status_code == 422
    assert client.post(f"/api/v1/operational-exceptions/{first.json()['id']}/status", json={"status":"RESOLVED"}).status_code == 422
    assert client.post("/api/v1/operational-exceptions", json={"exception_type":"OTHER", "severity":"LOW", "title":"No ref", "description":"Missing relation", "warehouse_id":seed["warehouse"].id}).status_code == 422
    assert TestClient(app).get("/api/v1/operational-exceptions").status_code == 401


def test_linked_work_order_and_load_summary(client, db, seed):
    outbound = make_outbound(db, seed)
    load = client.post("/api/v1/loads", json={"warehouse_id":seed["warehouse"].id, "outbound_ids":[outbound.id]}).json()
    incident = client.post("/api/v1/operational-exceptions", json=payload(seed, outbound, load_id=load["id"])).json()
    work_order = client.post(f"/api/v1/operational-exceptions/{incident['id']}/work-orders", json={"assigned_team":"QA", "notes":"Verify labels"})
    assert work_order.status_code == 200
    detail = client.get(f"/api/v1/operational-exceptions/{incident['id']}").json()
    assert detail["work_orders"][0]["priority"] == "HIGH"
    work_order_detail = client.get(f"/api/v1/work-orders/{work_order.json()['id']}").json()
    assert work_order_detail["work_order_type"] == "CHECK" and work_order_detail["operational_exception_id"] == incident["id"]
    load_detail = client.get(f"/api/v1/loads/{load['id']}").json()
    assert load_detail["active_exception_count"] == 1
    assert load_detail["active_exceptions"][0]["exception_no"] == incident["exception_no"]
    assert client.get(f"/api/v1/operational-exceptions/{incident['id']}").json()["status"] == "OPEN"


def test_outbound_exception_creates_and_confirm_resolves_incident(client, db, seed):
    outbound = make_outbound(db, seed)
    marked = client.post(f"/api/v1/outbounds/{outbound.id}/exception", json={"reason":"Damaged pallet", "remark":"Rewrap required"})
    assert marked.status_code == 200
    incidents = client.get("/api/v1/operational-exceptions", params={"q":outbound.ob_no}).json()["data"]
    assert len(incidents) == 1 and incidents[0]["status"] == "OPEN"
    # Existing Outbound rules still govern recovery; without allocations, confirmation is rejected.
    assert client.post(f"/api/v1/outbounds/{outbound.id}/confirm").status_code == 409
    assert client.get(f"/api/v1/operational-exceptions/{incidents[0]['id']}").json()["status"] == "OPEN"
