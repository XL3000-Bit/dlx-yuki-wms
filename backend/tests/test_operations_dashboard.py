from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.core.security import create_access_token
from app.main import app
from app.api.deps import get_db
from app.models import Load, OperationalException, OperationalExceptionEvent, User, Warehouse, WorkOrder, WorkOrderEvent
from app.models.load import LoadStatus
from app.models.operational_exception import ExceptionSeverity, ExceptionStatus, ExceptionType
from app.models.user import ScopeMode
from app.models.user_scope import UserWarehouseScope
from app.models.work_order import WorkOrderPriority, WorkOrderStatus, WorkOrderType


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


def seed_ops(db, seed, warehouse, *, load_status=LoadStatus.READY, wo_status=WorkOrderStatus.OPEN, priority=WorkOrderPriority.NORMAL, ex_status=ExceptionStatus.OPEN, severity=ExceptionSeverity.HIGH, resolved=False, age_hours=2, suffix="A"):
    now = datetime.now(timezone.utc)
    created = now - timedelta(hours=age_hours)
    load = Load(load_no=f"LD-D-{warehouse.id}-{suffix}", warehouse_id=warehouse.id, status=load_status, created_by=seed["admin"].id, created_at=created, updated_at=created)
    db.add(load); db.flush()
    wo = WorkOrder(work_order_no=f"WO-D-{warehouse.id}-{suffix}", work_order_type=WorkOrderType.GENERAL, status=wo_status, warehouse_id=warehouse.id, priority=priority, created_by=seed["admin"].id, created_at=created, updated_at=created, completed_at=now if wo_status == WorkOrderStatus.COMPLETED else None)
    db.add(wo); db.flush()
    exc = OperationalException(exception_no=f"EX-D-{warehouse.id}-{suffix}", exception_type=ExceptionType.OUTBOUND, severity=severity, status=ex_status, title=f"Dash {suffix}", description="dash", warehouse_id=warehouse.id, load_id=load.id, reported_at=created, reported_by=seed["admin"].id, resolved_at=now if resolved else None, resolution="fixed" if resolved else None)
    db.add(exc); db.flush()
    db.add(WorkOrderEvent(work_order_id=wo.id, event_type="CREATED", actor_user_id=seed["admin"].id, created_at=created, message=f"created {wo.work_order_no}"))
    db.add(OperationalExceptionEvent(operational_exception_id=exc.id, event_type="EXCEPTION_CREATED", actor_user_id=seed["admin"].id, created_at=created, message=f"created {exc.exception_no}"))
    db.commit()
    return load, wo, exc


def test_admin_summary_and_zero_resolution_is_null(client, db, seed):
    seed_ops(db, seed, seed["warehouse"], severity=ExceptionSeverity.CRITICAL)
    data = client.get("/api/v1/dashboard/operations").json()
    assert data["summary"]["active_loads"]["kind"] == "snapshot"
    assert data["summary"]["completed_today"]["kind"] == "period"
    assert data["summary"]["active_loads"]["value"] >= 1
    assert data["summary"]["open_exceptions"]["value"] >= 1
    assert data["summary"]["critical_exceptions"]["value"] >= 1
    assert data["exceptions"]["average_resolution_seconds"] is None
    assert data["work_orders"]["funnel"][0]["key"] == "OPEN"
    assert client.get("/api/v1/dashboard/operations").status_code == 200


def test_scoped_dashboard_hides_other_warehouse(client, db, seed):
    other = make_warehouse(db, "DLX-SFO")
    seed_ops(db, seed, seed["warehouse"], suffix="IN")
    seed_ops(db, seed, other, suffix="OUT", severity=ExceptionSeverity.CRITICAL, priority=WorkOrderPriority.URGENT)
    viewer = restrict(db, seed["viewer"], seed["warehouse"])
    scoped = auth_client(db, viewer)
    data = scoped.get("/api/v1/dashboard/operations").json()
    refs = [item["reference"] for item in data["attention"]] + [item["reference"] for item in data["recent_activity"]]
    assert any(ref.endswith("-IN") or "IN" in ref for ref in refs) or data["summary"]["open_work_orders"]["value"] >= 1
    assert all("OUT" not in ref for ref in refs)
    codes = {row["warehouse_code"] for row in data["warehouse_breakdown"]}
    assert "DLX-SFO" not in codes
    assert scoped.get("/api/v1/search", params={"q": "LD-D"}).status_code == 200


def test_period_completed_today_and_resolution_average(client, db, seed):
    seed_ops(db, seed, seed["warehouse"], wo_status=WorkOrderStatus.COMPLETED, ex_status=ExceptionStatus.RESOLVED, resolved=True, age_hours=5, suffix="DONE")
    data = client.get("/api/v1/dashboard/operations", params={"preset": "today"}).json()
    assert data["summary"]["completed_today"]["value"] >= 1
    assert data["exceptions"]["average_resolution_seconds"] is not None
    assert data["exceptions"]["average_resolution_seconds"] > 0


def test_aging_attention_and_viewer_read(client, db, seed):
    seed_ops(db, seed, seed["warehouse"], severity=ExceptionSeverity.CRITICAL, priority=WorkOrderPriority.URGENT, age_hours=30, suffix="OLD")
    data = client.get("/api/v1/dashboard/operations").json()
    assert data["exceptions"]["aging"]["gt_3d"] + data["exceptions"]["aging"]["d1_3"] + data["exceptions"]["aging"]["h12_24"] >= 1
    assert data["work_orders"]["aging"]["gt_24h"] >= 1
    assert data["attention"]
    assert data["recent_activity"]
    viewer = seed["viewer"]
    readable = auth_client(db, viewer)
    assert readable.get("/api/v1/dashboard/operations").status_code == 200
