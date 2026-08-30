from fastapi.testclient import TestClient
from app.core.security import create_access_token
from app.main import app
from app.models import Load, User, Warehouse, WorkOrder
from app.models.user import ScopeMode, UserRole
from app.models.user_scope import UserWarehouseScope
from app.models.load import LoadStatus
from app.models.work_order import WorkOrderPriority, WorkOrderStatus, WorkOrderType
from app.models.operational_exception import ExceptionSeverity, ExceptionStatus, ExceptionType, OperationalException
from datetime import datetime, timezone


def auth_client(db, user):
    def override():
        yield db
    app.dependency_overrides.clear()
    from app.api.deps import get_db
    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {create_access_token(str(user.id))}"
    return client


def second_warehouse(db):
    other = Warehouse(warehouse_code="DLX-SFO", warehouse_name="DLX San Francisco", address="2 Warehouse Way", city="San Francisco", state="CA", zip_code="94105")
    db.add(other); db.commit(); db.refresh(other)
    return other


def restrict_viewer(db, seed, warehouse):
    viewer = seed["viewer"]
    viewer.warehouse_scope_mode = ScopeMode.SELECTED
    viewer.customer_scope_mode = ScopeMode.ALL
    db.add(UserWarehouseScope(user_id=viewer.id, warehouse_id=warehouse.id))
    db.commit(); db.refresh(viewer)
    return viewer


def seed_ops(db, seed, warehouse, suffix):
    load = Load(load_no=f"LD-SCOPE-{suffix}", warehouse_id=warehouse.id, status=LoadStatus.PLANNED, created_by=seed["admin"].id)
    db.add(load); db.flush()
    wo = WorkOrder(work_order_no=f"WO-SCOPE-{suffix}", work_order_type=WorkOrderType.GENERAL, status=WorkOrderStatus.OPEN, warehouse_id=warehouse.id, priority=WorkOrderPriority.NORMAL, created_by=seed["admin"].id)
    db.add(wo); db.flush()
    exc = OperationalException(exception_no=f"EX-SCOPE-{suffix}", exception_type=ExceptionType.WAREHOUSE, severity=ExceptionSeverity.MEDIUM, status=ExceptionStatus.OPEN, title=f"Scope {suffix}", description="scope fixture", warehouse_id=warehouse.id, load_id=load.id, reported_at=datetime.now(timezone.utc), reported_by=seed["admin"].id)
    db.add(exc); db.commit()
    return load, wo, exc


def test_admin_sees_all_warehouses(client, db, seed):
    other = second_warehouse(db)
    seed_ops(db, seed, seed["warehouse"], "A")
    seed_ops(db, seed, other, "B")
    loads = client.get("/api/v1/loads").json()["data"]
    assert {row["warehouse_id"] for row in loads} >= {seed["warehouse"].id, other.id}


def test_selected_user_list_and_detail_are_scoped(client, db, seed):
    other = second_warehouse(db)
    load_a, wo_a, exc_a = seed_ops(db, seed, seed["warehouse"], "A2")
    load_b, wo_b, exc_b = seed_ops(db, seed, other, "B2")
    viewer = restrict_viewer(db, seed, seed["warehouse"])
    scoped = auth_client(db, viewer)
    load_ids = {row["id"] for row in scoped.get("/api/v1/loads").json()["data"]}
    assert load_a.id in load_ids and load_b.id not in load_ids
    assert scoped.get(f"/api/v1/loads/{load_a.id}").status_code == 200
    assert scoped.get(f"/api/v1/loads/{load_b.id}").status_code == 404
    assert scoped.get(f"/api/v1/work-orders/{wo_b.id}").status_code == 404
    assert scoped.get(f"/api/v1/work-orders/{wo_b.id}/events").status_code == 404
    assert scoped.get(f"/api/v1/operational-exceptions/{exc_b.id}").status_code == 404
    assert scoped.get(f"/api/v1/operational-exceptions/{exc_b.id}/events").status_code == 404
    assert scoped.get(f"/api/v1/operational-exceptions/{exc_a.id}").status_code == 200
    warehouses = scoped.get("/api/v1/master-data/warehouses").json()
    assert {row["id"] for row in warehouses} == {seed["warehouse"].id}


def test_search_does_not_leak_outside_scope(client, db, seed):
    other = second_warehouse(db)
    seed_ops(db, seed, seed["warehouse"], "IN")
    seed_ops(db, seed, other, "OUT")
    viewer = restrict_viewer(db, seed, seed["warehouse"])
    scoped = auth_client(db, viewer)
    exact = scoped.get("/api/v1/search", params={"q": "LD-SCOPE-OUT"}).json()
    assert exact["total"] == 0 and exact["groups"] == []
    prefix = scoped.get("/api/v1/search", params={"q": "WO-SCOPE-OU"}).json()
    assert prefix["total"] == 0
    contains = scoped.get("/api/v1/search", params={"q": "SCOPE-OU"}).json()
    assert contains["total"] == 0
    mixed = scoped.get("/api/v1/search", params={"q": "SCOPE-"}).json()
    refs = [item["primary_reference"] for group in mixed["groups"] for item in group["items"]]
    assert any(ref.endswith("-IN") for ref in refs)
    assert not any(ref.endswith("-OUT") for ref in refs)


def test_viewer_cannot_write_even_inside_scope(client, db, seed):
    viewer = restrict_viewer(db, seed, seed["warehouse"])
    scoped = auth_client(db, viewer)
    assert scoped.post("/api/v1/loads", json={"warehouse_id": seed["warehouse"].id, "outbound_ids": []}).status_code == 403
    assert scoped.post("/api/v1/work-orders", json={"work_order_type": "GENERAL", "warehouse_id": seed["warehouse"].id}).status_code == 403


def test_me_returns_scope_payload(client, db, seed):
    viewer = restrict_viewer(db, seed, seed["warehouse"])
    scoped = auth_client(db, viewer)
    me = scoped.get("/api/v1/users/me").json()
    assert me["warehouse_scope_mode"] == "SELECTED"
    assert me["warehouse_ids"] == [seed["warehouse"].id]
