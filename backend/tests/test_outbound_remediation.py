from decimal import Decimal
from datetime import date

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.endpoints import outbound as outbound_endpoint
from app.models import (
    AuditLog,
    InventoryLot,
    InventoryTransaction,
    OutboundInventoryAllocation,
    OutboundInventoryIdempotency,
)
from app.schemas.outbound import ReleaseRequest
from app.services.outbound import release


def inventory(client, seed, container="OB-REMEDIATION", pallet=10):
    inbound = client.post(
        "/api/v1/inbound",
        json={
            "container_number": container,
            "customer_id": seed["customer"].id,
            "warehouse_id": seed["warehouse"].id,
            "received_date": str(date.today()),
            "fc_code": "ONT8",
            "pallet_qty": pallet,
            "carton_qty": 20,
            "weight_lbs": 1000,
            "cbm": 5,
            "location_id": seed["location"].id,
            "status": 3,
        },
    ).json()
    return client.post(f"/api/v1/inbound/{inbound['id']}/receive-to-inventory").json()


def ob(seed):
    return {
        "customer_id": seed["customer"].id,
        "warehouse_id": seed["warehouse"].id,
        "carrier_id": seed["carrier"].id,
        "ob_type": "STANDARD",
        "delivery_type": "FTL",
    }


def batch_allocate_payload(lot_id):
    return {
        "action": "allocate",
        "items": [{"id": 101, "data": {"inventory_lot_id": lot_id, "pallet_qty": 3}}],
    }


@pytest.mark.parametrize("quantity", [0, -1, Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_release_request_rejects_non_positive_and_non_finite_quantities(quantity):
    for field in ("pallet_qty", "carton_qty", "weight_lbs", "cbm"):
        with pytest.raises(ValidationError):
            ReleaseRequest.model_validate({field: quantity})


def test_release_request_preserves_release_all_and_partial_semantics():
    assert ReleaseRequest.model_validate({}).model_dump(exclude_none=True) == {}
    assert ReleaseRequest.model_validate({"pallet_qty": None}).pallet_qty is None
    request = ReleaseRequest.model_validate({"pallet_qty": 2, "carton_qty": None})
    assert request.pallet_qty == Decimal("2")
    assert request.carton_qty is None


@pytest.mark.parametrize("quantity", [0, -1, Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_release_service_rejects_invalid_quantities_before_database_access(quantity):
    request = ReleaseRequest.model_construct(pallet_qty=quantity)

    with pytest.raises(HTTPException) as exc_info:
        release(object(), 1, 1, request, 1)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Release quantities must be finite and greater than zero"


def test_invalid_release_batch_writes_nothing_and_same_key_can_retry(
    client: TestClient, db: Session, seed
):
    lot = inventory(client, seed, container="RELEASE-VALIDATION", pallet=10)
    outbound = client.post("/api/v1/outbounds", json=ob(seed)).json()
    allocation = client.post(
        f"/api/v1/outbounds/{outbound['id']}/allocate",
        json={"inventory_lot_id": lot["id"], "pallet_qty": 6},
    ).json()
    url = f"/api/v1/outbounds/{outbound['id']}/inventory/batch"
    key = "invalid-release-retry"
    invalid = {
        "action": "release",
        "items": [
            {
                "id": allocation["id"],
                "data": {"allocation_id": allocation["id"], "pallet_qty": 0},
            }
        ],
    }

    before_transactions = len(db.scalars(select(InventoryTransaction)).all())
    before_audits = len(db.scalars(select(AuditLog)).all())
    failed = client.post(url, json=invalid, headers={"Idempotency-Key": key})

    assert failed.status_code == 409
    assert failed.json()["detail"] == {
        "code": "OUTBOUND_BATCH_OPERATION_FAILED",
        "item_id": allocation["id"],
        "message": "OUTBOUND_BATCH_OPERATION_FAILED",
    }
    db.expire_all()
    stored_lot = db.get(InventoryLot, lot["id"])
    stored_allocation = db.get(OutboundInventoryAllocation, allocation["id"])
    assert stored_lot.available_pallet_qty == 4
    assert stored_lot.allocated_pallet_qty == 6
    assert stored_allocation.allocated_pallet_qty == 6
    assert len(db.scalars(select(InventoryTransaction)).all()) == before_transactions
    assert len(db.scalars(select(AuditLog)).all()) == before_audits
    assert db.scalar(
        select(OutboundInventoryIdempotency).where(
            OutboundInventoryIdempotency.idempotency_key == key
        )
    ) is None

    valid = {
        "action": "release",
        "items": [
            {
                "id": allocation["id"],
                "data": {"allocation_id": allocation["id"], "pallet_qty": 2},
            }
        ],
    }
    retried = client.post(url, json=valid, headers={"Idempotency-Key": key})
    assert retried.status_code == 200, retried.text
    db.expire_all()
    assert db.get(InventoryLot, lot["id"]).available_pallet_qty == 6
    assert db.get(OutboundInventoryAllocation, allocation["id"]).allocated_pallet_qty == 4


def test_second_invalid_release_item_is_rejected_before_lock_receipt_or_mutation(
    client: TestClient, seed, monkeypatch
):
    outbound = client.post("/api/v1/outbounds", json=ob(seed)).json()
    calls = []

    def unexpected_call(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("batch execution started before all items were validated")

    for name in ("acquire_command_lock", "find_receipt", "get_lot", "allocate", "release"):
        monkeypatch.setattr(outbound_endpoint, name, unexpected_call)

    failed = client.post(
        f"/api/v1/outbounds/{outbound['id']}/inventory/batch",
        json={
            "action": "release",
            "items": [
                {"id": 101, "data": {"allocation_id": 101, "pallet_qty": 1}},
                {"id": 102, "data": {"allocation_id": 102, "pallet_qty": 0}},
            ],
        },
        headers={"Idempotency-Key": "second-invalid-release"},
    )

    assert failed.status_code == 409
    assert failed.json()["detail"] == {
        "code": "OUTBOUND_BATCH_OPERATION_FAILED",
        "item_id": 102,
        "message": "OUTBOUND_BATCH_OPERATION_FAILED",
    }
    assert calls == []


def test_inventory_batch_hides_unexpected_exception_and_leaves_key_reusable(
    client: TestClient, db: Session, seed, monkeypatch
):
    lot = inventory(client, seed, container="BATCH-ERROR-SANITIZE", pallet=10)
    outbound = client.post("/api/v1/outbounds", json=ob(seed)).json()
    url = f"/api/v1/outbounds/{outbound['id']}/inventory/batch"
    payload = batch_allocate_payload(lot["id"])
    key = "unexpected-error-retry"
    original = outbound_endpoint.acquire_command_lock

    def fail_with_secret(*_args, **_kwargs):
        raise RuntimeError("private database hostname and credentials")

    monkeypatch.setattr(outbound_endpoint, "acquire_command_lock", fail_with_secret)
    failed = client.post(url, json=payload, headers={"Idempotency-Key": key})
    assert failed.status_code == 409
    assert failed.json()["detail"]["code"] == "OUTBOUND_BATCH_OPERATION_FAILED"
    assert "private" not in failed.text
    assert "credentials" not in failed.text
    assert db.scalar(
        select(OutboundInventoryIdempotency).where(
            OutboundInventoryIdempotency.idempotency_key == key
        )
    ) is None

    monkeypatch.setattr(outbound_endpoint, "acquire_command_lock", original)
    retried = client.post(url, json=payload, headers={"Idempotency-Key": key})
    assert retried.status_code == 200, retried.text


def test_workbench_batch_hides_unexpected_exception_and_continues(
    client: TestClient, db: Session, seed
):
    outbound = client.post(
        "/api/v1/outbounds", json={**ob(seed), "reference_no": "DELETE-AFTER-ERROR"}
    ).json()

    response = client.post(
        "/api/v1/outbounds/workbench/batch",
        json={"action": "delete", "ids": ["private-error-value", outbound["id"]]},
    )

    assert response.status_code == 200
    assert response.json()["results"] == [
        {
            "id": "private-error-value",
            "status": "failed",
            "reason": "OUTBOUND_BATCH_OPERATION_FAILED",
        },
        {"id": outbound["id"], "status": "success"},
    ]
