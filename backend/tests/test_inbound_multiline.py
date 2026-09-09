from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models import (
    Customer,
    InboundRecord,
    InventoryLot,
    InventoryTransaction,
    User,
    Warehouse,
    WarehouseArea,
    WarehouseLocation,
)
from app.models.user import ScopeMode, UserRole
from app.services.inventory import receive_inbound_lines


def multi_payload(seed):
    return {
        "container_number": "MULTI123",
        "customer_id": seed["customer"].id,
        "warehouse_id": seed["warehouse"].id,
        "lines": [
            {
                "line_no": 1,
                "fc_code": "LAX9",
                "pallet_qty": 2,
                "carton_qty": 20,
                "weight_lbs": 120.5,
                "cbm": 2.25,
                "location_id": seed["location"].id,
                "remark": "first",
            },
            {
                "line_no": 2,
                "fc_code": "ONT8",
                "pallet_qty": 3,
                "carton_qty": 30,
                "weight_lbs": 180.5,
                "cbm": 3.75,
            },
        ],
    }


def test_create_patch_and_receive_multiple_lines(client: TestClient, db: Session, seed):
    created = client.post("/api/v1/inbound", json=multi_payload(seed))
    assert created.status_code == 201, created.text
    body = created.json()
    assert len(body["lines"]) == 2
    assert Decimal(body["pallet_qty"]) == Decimal("5")
    assert Decimal(body["carton_qty"]) == Decimal("50")
    assert Decimal(body["weight_lbs"]) == Decimal("301")
    assert Decimal(body["cbm"]) == Decimal("6")
    assert body["lines"][0]["location_id"] == seed["location"].id

    filtered = client.get("/api/v1/inbound", params={"fc_code": "ONT8"})
    assert filtered.status_code == 200
    assert filtered.json()["meta"]["total"] == 1

    patched = client.patch(
        f"/api/v1/inbound/{body['id']}",
        json={
            "lines": [
                {"line_no": 1, "fc_code": "SBD1", "pallet_qty": 4, "carton_qty": 40},
                {"line_no": 2, "fc_code": "ONT8", "pallet_qty": 1, "carton_qty": 10},
            ]
        },
    )
    assert patched.status_code == 200, patched.text
    assert Decimal(patched.json()["pallet_qty"]) == Decimal("5")

    received = client.post(f"/api/v1/inbound/{body['id']}/receive")
    assert received.status_code == 200, received.text
    result = received.json()
    assert result["inbound"]["status"] == 2
    assert len(result["inventory_lots"]) == 2
    assert len(set(result["inbound"]["inventory_lot_ids"])) == 2
    assert {item["fc_code"] for item in result["inventory_lots"]} == {"SBD1", "ONT8"}
    assert db.scalar(select(func.count(InventoryTransaction.id))) == 2

    assert client.post(f"/api/v1/inbound/{body['id']}/receive").status_code == 409
    assert client.patch(f"/api/v1/inbound/{body['id']}", json={"remark": "late"}).status_code == 409


def test_cancel_requires_draft_without_inventory(client: TestClient, db: Session, seed):
    draft = client.post("/api/v1/inbound", json=multi_payload(seed)).json()
    canceled = client.post(f"/api/v1/inbound/{draft['id']}/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["status"] == 6
    assert client.post(f"/api/v1/inbound/{draft['id']}/receive").status_code == 409

    another = client.post(
        "/api/v1/inbound", json={**multi_payload(seed), "container_number": "MULTI456"}
    ).json()
    assert client.post(f"/api/v1/inbound/{another['id']}/receive").status_code == 200
    row = db.get(InboundRecord, another["id"])
    row.status = 0
    db.commit()
    assert client.post(f"/api/v1/inbound/{another['id']}/cancel").status_code == 409


def test_receive_failure_rolls_back_all_lines(client: TestClient, db: Session, seed, monkeypatch):
    record_id = client.post("/api/v1/inbound", json=multi_payload(seed)).json()["id"]
    from app.services import inventory as service

    original = service._receive_lot
    calls = 0

    def fail_second(session, inbound, line, user_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated second-line failure")
        return original(session, inbound, line, user_id)

    monkeypatch.setattr(service, "_receive_lot", fail_second)
    with pytest.raises(RuntimeError, match="second-line"):
        receive_inbound_lines(db, record_id, seed["admin"].id)
    assert db.scalar(select(func.count(InventoryLot.id))) == 0
    assert db.scalar(select(func.count(InventoryTransaction.id))) == 0
    assert db.get(InboundRecord, record_id).status == 0


def test_scope_applies_to_create_list_detail_receive_and_cancel(
    client: TestClient, db: Session, seed
):
    other_customer = Customer(customer_code="OTHER", customer_name="Other")
    other_warehouse = Warehouse(
        warehouse_code="OTHER",
        warehouse_name="Other",
        address="1 Other Way",
        city="Ontario",
        state="CA",
        zip_code="91761",
    )
    db.add_all([other_customer, other_warehouse])
    db.flush()
    area = WarehouseArea(
        warehouse_id=other_warehouse.id, area_code="RECV", area_name="Receiving"
    )
    db.add(area)
    db.flush()
    other_location = WarehouseLocation(
        warehouse_id=other_warehouse.id,
        area_id=area.id,
        location_code="B01",
        location_name="B01",
    )
    scoped = User(
        username="scoped-inbound",
        display_name="Scoped Inbound",
        email="scoped@test.local",
        password_hash=hash_password("WarehousePassword!"),
        role=UserRole.INBOUND,
        warehouse_scope_mode=ScopeMode.SELECTED,
        customer_scope_mode=ScopeMode.SELECTED,
    )
    scoped.warehouses.append(seed["warehouse"])
    scoped.customers.append(seed["customer"])
    db.add_all([other_location, scoped])
    db.commit()

    outside = client.post(
        "/api/v1/inbound",
        json={
            "container_number": "OUTSIDE",
            "customer_id": other_customer.id,
            "warehouse_id": other_warehouse.id,
        },
    ).json()
    client.headers["Authorization"] = f"Bearer {create_access_token(str(scoped.id))}"
    assert client.get("/api/v1/inbound").json()["meta"]["total"] == 0
    assert client.get(f"/api/v1/inbound/{outside['id']}").status_code == 404
    assert client.post(f"/api/v1/inbound/{outside['id']}/receive").status_code == 404
    assert client.post(f"/api/v1/inbound/{outside['id']}/cancel").status_code == 404
    forbidden = client.post(
        "/api/v1/inbound",
        json={
            "container_number": "DENIED",
            "customer_id": other_customer.id,
            "warehouse_id": other_warehouse.id,
        },
    )
    assert forbidden.status_code == 403
