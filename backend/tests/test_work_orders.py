import re

from fastapi.testclient import TestClient

from app.main import app
from app.models import OutboundOrder, PickingList


def refs(db, seed):
    ob = OutboundOrder(ob_no="WO-OB-1", warehouse_id=seed["warehouse"].id, customer_id=seed["customer"].id, created_by=seed["admin"].id, status=0, po_number=None)
    db.add(ob)
    db.flush()
    pick = PickingList(picking_no="WO-PICK-1", outbound_order_id=ob.id, status=0, created_by=seed["admin"].id)
    db.add(pick)
    db.commit()
    return ob, pick


def test_create_types_priority_numbering_and_picking_link(client, db, seed):
    ob, pick = refs(db, seed)
    first = client.post("/api/v1/work-orders", json={"work_order_type":"PICK", "warehouse_id":seed["warehouse"].id, "outbound_id":ob.id, "picking_list_id":pick.id, "priority":"URGENT"})
    second = client.post("/api/v1/work-orders", json={"work_order_type":"GENERAL", "warehouse_id":seed["warehouse"].id})
    assert first.status_code == second.status_code == 201
    assert re.fullmatch(r"WO-\d{8}-\d{4}", first.json()["work_order_no"])
    assert first.json()["work_order_no"] != second.json()["work_order_no"]
    assert first.json()["priority"] == "URGENT"
    assert first.json()["picking_list_id"] == pick.id


def test_assignment_patch_filters_detail_and_terminal_status(client, db, seed):
    created = client.post("/api/v1/work-orders", json={"work_order_type":"GENERAL", "warehouse_id":seed["warehouse"].id}).json()
    work_order_id = created["id"]
    assigned = client.post(f"/api/v1/work-orders/{work_order_id}/assign", json={"assigned_to":seed["admin"].id, "assigned_team":"Dock A"})
    assert assigned.status_code == 200
    assert assigned.json()["assigned_team"] == "Dock A"
    assert client.patch(f"/api/v1/work-orders/{work_order_id}", json={"priority":"HIGH", "notes":"Handle first"}).status_code == 200
    filtered = client.get("/api/v1/work-orders", params={"assigned_to":seed["admin"].id, "priority":"HIGH", "q":created["work_order_no"]})
    assert filtered.status_code == 200 and filtered.json()["meta"]["total"] == 1
    assert client.get(f"/api/v1/work-orders/{work_order_id}").json()["notes"] == "Handle first"
    assert client.post(f"/api/v1/work-orders/{work_order_id}/status", json={"status":"ASSIGNED"}).status_code == 200
    assert client.post(f"/api/v1/work-orders/{work_order_id}/status", json={"status":"COMPLETED"}).status_code == 409
    assert client.post(f"/api/v1/work-orders/{work_order_id}/status", json={"status":"IN_PROGRESS"}).status_code == 200
    completed = client.post(f"/api/v1/work-orders/{work_order_id}/status", json={"status":"COMPLETED"})
    assert completed.status_code == 200 and completed.json()["started_at"] and completed.json()["completed_at"]
    assert client.post(f"/api/v1/work-orders/{work_order_id}/status", json={"status":"CANCELED"}).status_code == 409
    assert client.patch(f"/api/v1/work-orders/{work_order_id}", json={"notes":"too late"}).status_code == 409


def test_load_level_work_order_is_exposed_by_load_detail(client, seed):
    load = client.post("/api/v1/loads", json={"warehouse_id":seed["warehouse"].id, "outbound_ids":[]})
    assert load.status_code == 201
    work_order = client.post("/api/v1/work-orders", json={"work_order_type":"LOAD", "warehouse_id":seed["warehouse"].id, "load_id":load.json()["id"]})
    assert work_order.status_code == 201
    detail = client.get(f"/api/v1/loads/{load.json()['id']}")
    assert detail.status_code == 200
    assert [item["id"] for item in detail.json()["work_orders"]] == [work_order.json()["id"]]


def test_invalid_related_objects_values_and_auth(client, db, seed):
    ob, pick = refs(db, seed)
    assert client.post("/api/v1/work-orders", json={"work_order_type":"NOPE", "warehouse_id":seed["warehouse"].id}).status_code == 422
    assert client.post("/api/v1/work-orders", json={"work_order_type":"CHECK", "warehouse_id":seed["warehouse"].id, "priority":"NOPE"}).status_code == 422
    assert client.post("/api/v1/work-orders", json={"work_order_type":"PICK", "warehouse_id":seed["warehouse"].id, "outbound_id":ob.id + 9999}).status_code == 404
    assert client.post("/api/v1/work-orders", json={"work_order_type":"PICK", "warehouse_id":seed["warehouse"].id, "outbound_id":ob.id, "picking_list_id":pick.id + 9999}).status_code == 404
    assert client.post("/api/v1/work-orders", json={"work_order_type":"GENERAL", "warehouse_id":seed["warehouse"].id, "assigned_to":seed["admin"].id + 9999}).status_code == 422
    assert TestClient(app).get("/api/v1/work-orders").status_code == 401
