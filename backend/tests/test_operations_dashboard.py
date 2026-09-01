from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.models import Load, User, Warehouse
from app.models.user import ScopeMode, UserRole
from app.utils.business_time import get_business_today, to_business_datetime


def _auth(client: TestClient, user: User) -> None:
    client.headers["Authorization"] = f"Bearer {create_access_token(str(user.id))}"


def test_operations_dashboard_empty_contract(client):
    body = client.get("/api/v1/dashboard/operations").json()

    assert body["summary"] == {
        "active_loads": 0,
        "outbound_ready": 0,
        "outbound_active": 0,
        "open_work_orders": 0,
        "open_exceptions": 0,
        "critical_open_exceptions": 0,
        "completed_work_orders_period": 0,
    }
    assert body["work_orders"]["aging_snapshot"] == {
        "lt_4h": 0,
        "4_12h": 0,
        "12_24h": 0,
        "gt_24h": 0,
    }
    assert body["recent_activity"] == []


def test_operations_dashboard_metrics_activity_and_snapshot_date_semantics(client, db, seed):
    load = client.post("/api/v1/loads", json={"warehouse_id": seed["warehouse"].id}).json()
    work = client.post(
        "/api/v1/work-orders",
        json={
            "work_order_type": "LOAD",
            "warehouse_id": seed["warehouse"].id,
            "load_id": load["id"],
            "priority": "URGENT",
        },
    ).json()
    exception = client.post(
        "/api/v1/operational-exceptions",
        json={
            "exception_type": "WAREHOUSE",
            "severity": "CRITICAL",
            "title": "Dock blocked",
            "description": "Needs immediate action",
            "warehouse_id": seed["warehouse"].id,
            "load_id": load["id"],
        },
    ).json()
    db.commit()

    # SQLite drops timezone information for DateTime columns and its
    # CURRENT_TIMESTAMP default is UTC. Store this fixture in business-local
    # wall time explicitly so the test exercises the same Los Angeles business
    # date represented by PostgreSQL timestamptz in production.
    utc_created_at = datetime(2026, 8, 30, 0, 30, tzinfo=UTC)
    business_created_at = to_business_datetime(utc_created_at)
    assert utc_created_at.date() != business_created_at.date()
    load_row = db.get(Load, load["id"])
    assert load_row is not None
    load_row.created_at = business_created_at
    db.commit()

    business_date = business_created_at.date().isoformat()
    body = client.get(
        "/api/v1/dashboard/operations",
        params={"date_from": business_date, "date_to": business_date},
    ).json()
    assert body["summary"]["active_loads"] == 1
    assert body["summary"]["open_work_orders"] == 1
    assert body["summary"]["open_exceptions"] == 1
    assert body["summary"]["critical_open_exceptions"] == 1
    assert body["loads"]["created_period"] == 1
    assert body["work_orders"]["open_priority_snapshot"]["URGENT"] == 1
    assert body["exceptions"]["open_type_snapshot"]["WAREHOUSE"] == 1
    assert body["warehouses"][0]["open_work_orders"] == 1
    assert body["warehouses"][0]["open_exceptions"] == 1
    assert {item["entity_id"] for item in body["recent_activity"]} == {work["id"], exception["id"]}
    assert {item["kind"] for item in body["attention"]} == {"WORK_ORDER", "EXCEPTION"}

    utc_date = utc_created_at.date().isoformat()
    utc_day = client.get(
        "/api/v1/dashboard/operations",
        params={"date_from": utc_date, "date_to": utc_date},
    ).json()
    assert utc_day["loads"]["created_period"] == 0

    historic = client.get(
        "/api/v1/dashboard/operations",
        params={"date_from": "2000-01-01", "date_to": "2000-01-01"},
    ).json()
    assert historic["loads"]["created_period"] == 0
    assert historic["summary"]["open_work_orders"] == 1
    assert historic["summary"]["open_exceptions"] == 1


def test_operations_dashboard_aging_and_completed_period(client, db, seed):
    work = client.post(
        "/api/v1/work-orders",
        json={"work_order_type": "GENERAL", "warehouse_id": seed["warehouse"].id},
    ).json()
    client.post(f"/api/v1/work-orders/{work['id']}/status", json={"status": "IN_PROGRESS"})
    client.post(f"/api/v1/work-orders/{work['id']}/status", json={"status": "COMPLETED"})

    from app.models import WorkOrder

    row = db.get(WorkOrder, work["id"])
    row.completed_at = datetime.now() - timedelta(minutes=5)
    db.commit()
    today = get_business_today().isoformat()
    body = client.get("/api/v1/dashboard/operations", params={"date_from": today, "date_to": today}).json()
    assert body["summary"]["completed_work_orders_period"] == 1
    assert body["execution_funnel"][-1] == {"stage": "COMPLETED", "count": 1}


def test_operations_dashboard_enforces_warehouse_scope_and_validation(client, db, seed):
    other = Warehouse(
        warehouse_code="DLX-SEA",
        warehouse_name="Seattle",
        address="2 Warehouse Way",
        city="Seattle",
        state="WA",
        zip_code="98101",
    )
    scoped = User(
        username="dashboard-viewer",
        display_name="Dashboard Viewer",
        email="dashboard-viewer@example.com",
        password_hash=hash_password("WarehousePassword!"),
        role=UserRole.VIEWER,
        warehouse_scope_mode=ScopeMode.SELECTED,
        customer_scope_mode=ScopeMode.ALL,
    )
    db.add_all([other, scoped]); db.flush()
    scoped.warehouses = [seed["warehouse"]]
    db.commit()
    client.post("/api/v1/work-orders", json={"work_order_type": "GENERAL", "warehouse_id": seed["warehouse"].id})
    client.post("/api/v1/work-orders", json={"work_order_type": "GENERAL", "warehouse_id": other.id})

    _auth(client, scoped)
    body = client.get("/api/v1/dashboard/operations").json()
    assert body["summary"]["open_work_orders"] == 1
    assert [row["warehouse_id"] for row in body["warehouses"]] == [seed["warehouse"].id]
    assert client.get("/api/v1/dashboard/operations", params={"warehouse_id": other.id}).status_code == 403
    assert client.get(
        "/api/v1/dashboard/operations",
        params={"date_from": "2026-08-02", "date_to": "2026-08-01"},
    ).status_code == 422
