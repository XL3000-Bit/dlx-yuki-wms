from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.main import app
from app.models import Customer, User, Warehouse
from app.models.bol import BOL, BOLStatus
from app.models.inbound import AuditLog
from app.models.inventory import InventoryTransaction
from app.models.outbound import OBStatus, OutboundOrder
from app.models.picking import PickingList, PickingStatus
from app.models.user import ScopeMode, UserRole
from app.services.access_policy import ROLE_PERMISSIONS
from app.utils.business_time import get_business_now


def _counts(db: Session) -> tuple[int, ...]:
    models = (OutboundOrder, PickingList, BOL, InventoryTransaction, AuditLog, User, Customer, Warehouse)
    return tuple(db.scalar(select(func.count()).select_from(model)) or 0 for model in models)


def _authorization(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


def test_dispatch_queue_requires_authentication_and_read_permission(client, seed, monkeypatch):
    anonymous = TestClient(app).get("/api/v1/3pl/dispatch-queue")
    assert anonymous.status_code == 401

    monkeypatch.setitem(ROLE_PERMISSIONS, UserRole.VIEWER, set())
    denied = client.get(
        "/api/v1/3pl/dispatch-queue",
        headers=_authorization(seed["viewer"]),
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "3PL dispatch queue read permission is required"


def test_dispatch_queue_scopes_filters_pages_and_never_writes(client, db: Session, seed):
    now = get_business_now()
    other_customer = Customer(customer_code="OTHER", customer_name="Other Client")
    other_warehouse = Warehouse(
        warehouse_code="OTHER-WH", warehouse_name="Other Warehouse",
        address="2 Warehouse Way", city="Oakland", state="CA", zip_code="94601",
    )
    db.add_all([other_customer, other_warehouse])
    db.flush()

    viewer = seed["viewer"]
    viewer.warehouse_scope_mode = ScopeMode.SELECTED
    viewer.customer_scope_mode = ScopeMode.SELECTED
    viewer.warehouses.append(seed["warehouse"])
    viewer.customers.append(seed["customer"])

    visible = []
    for index, status in enumerate((OBStatus.IN_PROGRESS, OBStatus.CONFIRMED, OBStatus.HOLD), start=1):
        order = OutboundOrder(
            ob_no=f"OB-SCOPE-{index}", reference_no=f"CLIENT-REF-{index}",
            customer_id=seed["customer"].id, warehouse_id=seed["warehouse"].id,
            carrier_id=seed["carrier"].id, status=status,
            loading_team="Dispatch Team", schedule_pickup_at=now + timedelta(days=index),
            created_by=seed["admin"].id,
        )
        visible.append(order)
    hidden = OutboundOrder(
        ob_no="OB-HIDDEN", customer_id=other_customer.id, warehouse_id=other_warehouse.id,
        status=OBStatus.IN_PROGRESS, created_by=seed["admin"].id,
    )
    canceled = OutboundOrder(
        ob_no="OB-CANCELED", customer_id=seed["customer"].id,
        warehouse_id=seed["warehouse"].id, status=OBStatus.CANCELED,
        created_by=seed["admin"].id,
    )
    db.add_all([*visible, hidden, canceled])
    db.flush()
    db.add_all([
        PickingList(
            picking_no="PK-CANCELED", outbound_order_id=visible[1].id,
            status=PickingStatus.CANCELED, created_by=seed["admin"].id,
        ),
        BOL(
            bol_no="BOL-CANCELED", outbound_order_id=visible[1].id,
            customer_id=seed["customer"].id, warehouse_id=seed["warehouse"].id,
            ship_from_name="DLX", ship_from_address="1 Warehouse Way",
            status=BOLStatus.CANCELED, created_by=seed["admin"].id,
        ),
    ])
    db.commit()

    before = _counts(db)
    headers = _authorization(viewer)
    first = client.get(
        "/api/v1/3pl/dispatch-queue",
        params={"search": "client-ref", "page": 1, "page_size": 2, "sort": "reference"},
        headers=headers,
    )
    second = client.get(
        "/api/v1/3pl/dispatch-queue",
        params={"search": "client-ref", "page": 2, "page_size": 2, "sort": "reference"},
        headers=headers,
    )
    repeated = client.get(
        "/api/v1/3pl/dispatch-queue",
        params={"search": "client-ref", "page": 1, "page_size": 2, "sort": "reference"},
        headers=headers,
    )

    assert first.status_code == second.status_code == repeated.status_code == 200
    payload = first.json()
    assert payload["summary_scope"] == "FILTERED_RESULT"
    assert payload["summary"]["total"] == payload["total"] == 3
    assert payload["pages"] == 2
    assert [task["reference"] for task in payload["tasks"]] == ["OB-SCOPE-1", "OB-SCOPE-2"]
    assert [task["reference"] for task in second.json()["tasks"]] == ["OB-SCOPE-3"]
    repeated_payload = repeated.json()
    assert {
        key: repeated_payload[key]
        for key in repeated_payload
        if key != "generated_at"
    } == {
        key: payload[key]
        for key in payload
        if key != "generated_at"
    }
    confirmed = next(task for task in payload["tasks"] if task["reference"] == "OB-SCOPE-2")
    assert confirmed["document_state"] == "MISSING"
    assert confirmed["picking_download_url"] is None
    assert confirmed["bol_download_url"] is None
    assert _counts(db) == before

    forbidden_customer = client.get(
        "/api/v1/3pl/dispatch-queue", params={"customer_id": other_customer.id}, headers=headers,
    )
    forbidden_warehouse = client.get(
        "/api/v1/3pl/dispatch-queue", params={"warehouse_id": other_warehouse.id}, headers=headers,
    )
    assert forbidden_customer.status_code == forbidden_warehouse.status_code == 403


def test_dispatch_queue_rejects_bad_inputs(client):
    cases = (
        {"page": 0}, {"page_size": 101}, {"status": 5}, {"readiness": "UNKNOWN"},
        {"date_from": "2026-09-02", "date_to": "2026-09-01"},
    )
    for params in cases:
        assert client.get("/api/v1/3pl/dispatch-queue", params=params).status_code == 422
