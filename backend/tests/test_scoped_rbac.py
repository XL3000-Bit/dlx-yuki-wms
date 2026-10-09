from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.models import Customer, InboundRecord, OutboundOrder, User, Warehouse
from app.models.user import ScopeMode, UserRole


def _auth(client: TestClient, user: User) -> None:
    client.headers["Authorization"] = f"Bearer {create_access_token(str(user.id))}"


def _matrix(db, seed):
    warehouse_b = Warehouse(
        warehouse_code="DLX-SEA",
        warehouse_name="DLX Seattle",
        address="2 Warehouse Way",
        city="Seattle",
        state="WA",
        zip_code="98101",
    )
    customer_b = Customer(customer_code="BETA", customer_name="Beta Imports")
    warehouse_a_user = User(username="warehouse-a", display_name="Warehouse A", email="warehouse-a@example.com",
        password_hash=hash_password("WarehousePassword!"), role=UserRole.MANAGER,
        warehouse_scope_mode=ScopeMode.SELECTED, customer_scope_mode=ScopeMode.SELECTED)
    warehouse_b_user = User(username="warehouse-b", display_name="Warehouse B", email="warehouse-b@example.com",
        password_hash=hash_password("WarehousePassword!"), role=UserRole.MANAGER,
        warehouse_scope_mode=ScopeMode.SELECTED, customer_scope_mode=ScopeMode.SELECTED)
    scoped_viewer = User(username="scoped-viewer", display_name="Scoped Viewer", email="scoped-viewer@example.com",
        password_hash=hash_password("WarehousePassword!"), role=UserRole.VIEWER,
        warehouse_scope_mode=ScopeMode.SELECTED, customer_scope_mode=ScopeMode.SELECTED)
    db.add_all([warehouse_b, customer_b, warehouse_a_user, warehouse_b_user, scoped_viewer]); db.flush()
    warehouse_a_user.warehouses = [seed["warehouse"]]; warehouse_a_user.customers = [seed["customer"]]
    warehouse_b_user.warehouses = [warehouse_b]; warehouse_b_user.customers = [customer_b]
    scoped_viewer.warehouses = [seed["warehouse"]]; scoped_viewer.customers = [seed["customer"]]
    inbound_a = InboundRecord(inbound_no="IB-SCOPE-A", container_number="SCOPE-CONTAINER-A", customer_id=seed["customer"].id,
        warehouse_id=seed["warehouse"].id, created_by=seed["admin"].id, status=0)
    inbound_b = InboundRecord(inbound_no="IB-SCOPE-B", container_number="SECRET-OUTSIDE-ALPHA", customer_id=customer_b.id,
        warehouse_id=warehouse_b.id, created_by=seed["admin"].id, status=0)
    outbound_a = OutboundOrder(ob_no="SCOPE-ORDER-ALLOWED", reference_no="MIXED-SCOPE-KEY", customer_id=seed["customer"].id,
        warehouse_id=seed["warehouse"].id, created_by=seed["admin"].id, status=0)
    outbound_b = OutboundOrder(ob_no="SECRET-OUTSIDE-ALPHA", reference_no="MIXED-SCOPE-KEY", customer_id=customer_b.id,
        warehouse_id=warehouse_b.id, created_by=seed["admin"].id, status=0)
    db.add_all([inbound_a, inbound_b, outbound_a, outbound_b]); db.commit()
    return {"warehouse_b": warehouse_b, "customer_b": customer_b, "user_a": warehouse_a_user, "user_b": warehouse_b_user,
        "viewer": scoped_viewer, "inbound_a": inbound_a, "inbound_b": inbound_b, "outbound_a": outbound_a, "outbound_b": outbound_b}


def _references(search_response):
    return [item["primary_reference"] for group in search_response.json()["groups"] for item in group["items"]]


def test_admin_and_selected_scope_list_detail_and_selectors(client, db, seed):
    rows = _matrix(db, seed)
    assert client.get("/api/v1/inbound").json()["meta"]["total"] == 2
    _auth(client, rows["user_a"])
    listed = client.get("/api/v1/inbound").json()
    assert listed["meta"]["total"] == 1 and listed["data"][0]["id"] == rows["inbound_a"].id
    assert client.get(f"/api/v1/inbound/{rows['inbound_b'].id}").status_code == 404
    assert [row["id"] for row in client.get("/api/v1/master-data/warehouses").json()] == [seed["warehouse"].id]
    assert [row["id"] for row in client.get("/api/v1/master-data/customers").json()] == [seed["customer"].id]
    _auth(client, rows["user_b"])
    assert client.get("/api/v1/inbound").json()["data"][0]["id"] == rows["inbound_b"].id


def test_global_search_never_leaks_exact_prefix_contains_or_mixed_results(client, db, seed):
    rows = _matrix(db, seed); _auth(client, rows["user_a"])
    for query in ("SECRET-OUTSIDE-ALPHA", "SECRET-OUT", "OUTSIDE-ALP"):
        assert "SECRET-OUTSIDE-ALPHA" not in _references(client.get("/api/v1/search", params={"q": query}))
    mixed = _references(client.get("/api/v1/search", params={"q": "MIXED-SCOPE-KEY"}))
    assert mixed == ["SCOPE-ORDER-ALLOWED"]


def test_work_order_scope_inherits_for_detail_events_and_writes(client, db, seed):
    rows = _matrix(db, seed)
    work_a = client.post("/api/v1/work-orders", json={"work_order_type":"GENERAL", "warehouse_id":seed["warehouse"].id}).json()
    work_b = client.post("/api/v1/work-orders", json={"work_order_type":"GENERAL", "warehouse_id":rows["warehouse_b"].id}).json()
    _auth(client, rows["user_a"])
    listed = client.get("/api/v1/work-orders").json()
    assert listed["meta"]["total"] == 1 and listed["data"][0]["id"] == work_a["id"]
    assert client.get(f"/api/v1/work-orders/{work_b['id']}").status_code == 404
    assert client.get(f"/api/v1/work-orders/{work_b['id']}/events").status_code == 404
    assert client.post("/api/v1/work-orders", json={"work_order_type":"GENERAL", "warehouse_id":rows["warehouse_b"].id}).status_code == 403


def test_exception_list_counts_detail_events_and_actions_are_scoped(client, db, seed):
    rows = _matrix(db, seed)
    base = {"exception_type":"OUTBOUND", "severity":"HIGH", "description":"Scope test"}
    ex_a = client.post("/api/v1/operational-exceptions", json={**base, "title":"Allowed issue", "warehouse_id":seed["warehouse"].id,
        "outbound_id":rows["outbound_a"].id}).json()
    ex_b = client.post("/api/v1/operational-exceptions", json={**base, "title":"Hidden issue", "warehouse_id":rows["warehouse_b"].id,
        "outbound_id":rows["outbound_b"].id}).json()
    _auth(client, rows["user_a"])
    listed = client.get("/api/v1/operational-exceptions").json()
    assert listed["meta"]["total"] == 1 and listed["counts"]["OPEN"] == 1 and listed["data"][0]["id"] == ex_a["id"]
    assert client.get(f"/api/v1/operational-exceptions/{ex_b['id']}").status_code == 404
    assert client.get(f"/api/v1/operational-exceptions/{ex_b['id']}/events").status_code == 404
    assert client.post(f"/api/v1/operational-exceptions/{ex_b['id']}/assign", json={"assigned_team":"Dock"}).status_code == 404
    assert client.post(f"/api/v1/operational-exceptions/{ex_b['id']}/resolve", json={"resolution":"No access"}).status_code == 404


def test_viewer_has_read_only_permissions_and_backend_rejects_mutations(client, db, seed):
    rows = _matrix(db, seed); _auth(client, rows["viewer"])
    me = client.get("/api/v1/users/me").json()
    assert me["permissions"] == ["read"]
    assert me["warehouse_ids"] == [seed["warehouse"].id]
    assert client.get("/api/v1/inbound").json()["meta"]["total"] == 1
    assert client.post("/api/v1/work-orders", json={"work_order_type":"GENERAL", "warehouse_id":seed["warehouse"].id}).status_code == 403
    assert client.post("/api/v1/operational-exceptions", json={"exception_type":"OUTBOUND", "severity":"LOW", "title":"No write",
        "description":"Viewer cannot create", "warehouse_id":seed["warehouse"].id, "outbound_id":rows["outbound_a"].id}).status_code == 403
