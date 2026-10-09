from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import (
    BOL,
    BOLStatus,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    OperationalException,
    OutboundOrder,
    PickingList,
    PickingListItem,
    PickingStatus,
)


def _ready_fixture(
    client: TestClient,
    db: Session,
    seed,
    suffix: str,
    *,
    confirmed: bool = True,
    picked_pallet_qty: int = 6,
    with_bol: bool = True,
    with_carrier: bool = True,
    exception_status: ExceptionStatus | None = None,
) -> int:
    inbound = client.post(
        "/api/v1/inbound",
        json={
            "container_number": f"READY-{suffix}",
            "customer_id": seed["customer"].id,
            "warehouse_id": seed["warehouse"].id,
            "received_date": str(date.today()),
            "fc_code": "ONT8",
            "pallet_qty": 10,
            "carton_qty": 20,
            "weight_lbs": 1000,
            "cbm": 5,
            "location_id": seed["location"].id,
            "status": 3,
        },
    ).json()
    lot = client.post(f"/api/v1/inbound/{inbound['id']}/receive-to-inventory").json()
    outbound = client.post(
        "/api/v1/outbounds",
        json={
            "customer_id": seed["customer"].id,
            "warehouse_id": seed["warehouse"].id,
            "carrier_id": seed["carrier"].id if with_carrier else None,
            "ob_type": "STANDARD",
            "delivery_type": "FTL",
        },
    ).json()
    allocation = client.post(
        f"/api/v1/outbounds/{outbound['id']}/allocate",
        json={"inventory_lot_id": lot["id"], "pallet_qty": 6},
    ).json()
    if confirmed:
        response = client.post(f"/api/v1/outbounds/{outbound['id']}/confirm")
        assert response.status_code == 200, response.text

    if confirmed:
        picking = (
            db.query(PickingList)
            .filter(PickingList.outbound_order_id == outbound["id"])
            .order_by(PickingList.id.desc())
            .first()
        )
        assert picking is not None
        picking.status = PickingStatus.COMPLETED
        picking.items[0].picked_pallet_qty = picked_pallet_qty

        bol = (
            db.query(BOL)
            .filter(BOL.outbound_order_id == outbound["id"])
            .order_by(BOL.id.desc())
            .first()
        )
        assert bol is not None
        if not with_bol:
            bol.status = BOLStatus.CANCELED
    else:
        picking = PickingList(
            picking_no=f"PICK-{suffix}",
            outbound_order_id=outbound["id"],
            status=PickingStatus.COMPLETED,
            created_by=seed["admin"].id,
        )
        db.add(picking)
        db.flush()
        db.add(
            PickingListItem(
                picking_list_id=picking.id,
                outbound_allocation_id=allocation["id"],
                inventory_lot_id=lot["id"],
                location_id=seed["location"].id,
                lot_no=lot["lot_no"],
                container_number=lot["container_number"],
                planned_pallet_qty=6,
                picked_pallet_qty=picked_pallet_qty,
            )
        )
        if with_bol:
            db.add(BOL(
                bol_no=f"BOL-{suffix}",
                outbound_order_id=outbound["id"],
                customer_id=seed["customer"].id,
                warehouse_id=seed["warehouse"].id,
                carrier_id=seed["carrier"].id if with_carrier else None,
                ship_from_name="DLX Test Warehouse",
                ship_from_address="1 Warehouse Way",
                status=BOLStatus.GENERATED,
                created_by=seed["admin"].id,
            ))
    if exception_status is not None:
        db.add(
            OperationalException(
                exception_no=f"EX-{suffix}",
                exception_type=ExceptionType.OUTBOUND,
                severity=ExceptionSeverity.HIGH,
                status=exception_status,
                title="Dispatch blocker",
                description="Synthetic dispatch-readiness test exception",
                warehouse_id=seed["warehouse"].id,
                outbound_id=outbound["id"],
                reported_at=datetime.now(UTC),
                reported_by=seed["admin"].id,
            )
        )
    db.commit()
    return outbound["id"]


def _attach_to_load(client: TestClient, seed, outbound_id: int) -> int:
    assert client.patch(f"/api/v1/loads/orders/{outbound_id}/business", json={"business_type": "PRIVATE"}).status_code == 200
    response = client.post(
        "/api/v1/loads",
        json={"warehouse_id": seed["warehouse"].id, "dispatch_business_type": "PRIVATE", "outbound_ids": [outbound_id]},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_standalone_ready_evidence_still_requires_load_gate(client: TestClient, db: Session, seed):
    outbound_id = _ready_fixture(client, db, seed, "PASS")
    readiness = client.get(f"/api/v1/outbounds/{outbound_id}/dispatch-readiness")
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "NOT_READY"
    assert readiness.json()["blocking_codes"] == ["LOAD_DISPATCH_REQUIRED"]
    assert all(check["passed"] for check in readiness.json()["checks"] if check["key"] != "load_dispatch")
    response = client.post(f"/api/v1/outbounds/{outbound_id}/dispatch")
    assert response.status_code == 409, response.text


@pytest.mark.parametrize(
    ("suffix", "kwargs", "expected_codes"),
    [
        ("PICK", {"picked_pallet_qty": 5}, {"PICKING_INCOMPLETE"}),
        ("BOL", {"with_bol": False}, {"SYSTEM_BOL_REQUIRED", "BOL_MISSING"}),
        ("CARRIER", {"with_carrier": False}, {"CARRIER_REQUIRED", "CARRIER_MISSING"}),
        ("OPEN", {"exception_status": ExceptionStatus.OPEN}, {"ACTIVE_EXCEPTION", "BLOCKING_EXCEPTION"}),
        (
            "INVESTIGATING",
            {"exception_status": ExceptionStatus.INVESTIGATING},
            {"ACTIVE_EXCEPTION", "BLOCKING_EXCEPTION"},
        ),
        ("STATUS", {"confirmed": False}, {"OUTBOUND_NOT_CONFIRMED", "OUTBOUND_STATUS_INVALID"}),
    ],
)
def test_dispatch_blockers_do_not_change_status(
    client: TestClient,
    db: Session,
    seed,
    suffix: str,
    kwargs: dict,
    expected_codes: set[str],
):
    outbound_id = _ready_fixture(client, db, seed, suffix, **kwargs)
    before = db.get(OutboundOrder, outbound_id).status
    readiness = client.get(f"/api/v1/outbounds/{outbound_id}/dispatch-readiness")
    assert readiness.status_code == 200
    readiness_body = readiness.json()
    assert readiness_body["status"] == "NOT_READY" or readiness_body.get("ready") is False
    assert expected_codes.intersection(readiness_body["blocking_codes"])
    response = client.post(f"/api/v1/outbounds/{outbound_id}/dispatch")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["status"] == "NOT_READY" or detail.get("ready") is False
    assert expected_codes.intersection(detail["blocking_codes"])
    assert detail["blocking_reasons"]
    db.expire_all()
    assert db.get(OutboundOrder, outbound_id).status == before


def test_batch_dispatch_keeps_blocked_outbound_unchanged(client: TestClient, db: Session, seed):
    ready_id = _ready_fixture(client, db, seed, "BATCH-READY")
    blocked_id = _ready_fixture(client, db, seed, "BATCH-BLOCKED", with_bol=False)
    response = client.post(
        "/api/v1/outbounds/workbench/batch",
        json={"action": "dispatch", "ids": [ready_id, blocked_id]},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["successful"] == 0
    assert result["failed"] == 2
    failed_result = next(item for item in result["results"] if item["id"] == blocked_id)
    assert failed_result["id"] == blocked_id
    assert "generated BOL" in failed_result["reason"]
    db.expire_all()
    assert db.get(OutboundOrder, ready_id).status == 3
    assert db.get(OutboundOrder, blocked_id).status == 3


def test_load_bound_outbound_readiness_and_dispatch_are_blocked(client: TestClient, db: Session, seed):
    outbound_id = _ready_fixture(client, db, seed, "LOAD-BOUND")
    _attach_to_load(client, seed, outbound_id)

    readiness = client.get(f"/api/v1/outbounds/{outbound_id}/dispatch-readiness")
    assert readiness.status_code == 200, readiness.text
    readiness_body = readiness.json()
    assert readiness_body["status"] == "NOT_READY"
    assert "LOAD_DISPATCH_REQUIRED" in readiness_body["blocking_codes"]

    response = client.post(f"/api/v1/outbounds/{outbound_id}/dispatch")
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["error_code"] == "DISPATCH_THROUGH_LOAD_REQUIRED"

    db.expire_all()
    assert db.get(OutboundOrder, outbound_id).status == 3


def test_batch_dispatch_blocks_every_order_without_load_gate(client: TestClient, db: Session, seed):
    standalone_id = _ready_fixture(client, db, seed, "BATCH-STANDALONE")
    load_bound_id = _ready_fixture(client, db, seed, "BATCH-LOAD-BOUND")
    _attach_to_load(client, seed, load_bound_id)

    response = client.post(
        "/api/v1/outbounds/workbench/batch",
        json={"action": "dispatch", "ids": [standalone_id, load_bound_id]},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["successful"] == 0
    assert result["failed"] == 2
    results = {item["id"]: item for item in result["results"]}
    assert results[standalone_id]["status"] == "failed"
    assert results[load_bound_id]["status"] == "failed"

    db.expire_all()
    assert db.get(OutboundOrder, standalone_id).status == 3
    assert db.get(OutboundOrder, load_bound_id).status == 3


def test_viewer_cannot_dispatch_ready_outbound(client: TestClient, db: Session, seed):
    outbound_id = _ready_fixture(client, db, seed, "VIEWER")
    token = create_access_token(str(seed["viewer"].id))
    readiness = client.get(
        f"/api/v1/outbounds/{outbound_id}/dispatch-readiness",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert readiness.status_code == 200, readiness.text
    response = client.post(
        f"/api/v1/outbounds/{outbound_id}/dispatch",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    db.expire_all()
    assert db.get(OutboundOrder, outbound_id).status == 3
