from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models import (
    InventoryLot,
    OutboundInventoryAllocation,
    OutboundOrder,
    PickingList,
    PickingListItem,
    PickingStatus,
    ScanEvent,
    User,
    Warehouse,
    WarehouseArea,
    WarehouseLocation,
)
from app.models.user import ScopeMode, UserRole


def _inventory(client: TestClient, seed: dict, container: str = "SCAN-CNTR.1") -> dict:
    inbound = client.post(
        "/api/v1/inbound",
        json={
            "container_number": container,
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
    )
    assert inbound.status_code == 201, inbound.text
    received = client.post(
        f"/api/v1/inbound/{inbound.json()['id']}/receive-to-inventory"
    )
    assert received.status_code == 200, received.text
    return received.json()


def _outbound(client: TestClient, seed: dict, lot: dict | None = None) -> dict:
    response = client.post(
        "/api/v1/outbounds",
        json={
            "customer_id": seed["customer"].id,
            "warehouse_id": seed["warehouse"].id,
            "carrier_id": seed["carrier"].id,
            "ob_type": "STANDARD",
            "delivery_type": "FTL",
        },
    )
    assert response.status_code == 201, response.text
    outbound = response.json()
    if lot is not None:
        allocation = client.post(
            f"/api/v1/outbounds/{outbound['id']}/allocate",
            json={"inventory_lot_id": lot["id"], "pallet_qty": 4},
        )
        assert allocation.status_code == 200, allocation.text
    return outbound


def _picking(client: TestClient, outbound_id: int) -> dict:
    response = client.post(f"/api/v1/outbounds/{outbound_id}/picking-lists")
    assert response.status_code == 200, response.text
    return response.json()


def _session(
    client: TestClient,
    seed: dict,
    operation_type: str = "STAGE",
    **context: int | str | None,
) -> dict:
    response = client.post(
        "/api/v1/scan-sessions",
        json={
            "warehouse_id": seed["warehouse"].id,
            "operation_type": operation_type,
            **context,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["session"]


def _scan(client: TestClient, session_id: int, value: str):
    return client.post(f"/api/v1/scan-sessions/{session_id}/scan", json={"value": value})


def _pick_session(client: TestClient, seed: dict, picking: dict) -> dict:
    return _session(
        client,
        seed,
        operation_type="PICK",
        picking_ref=picking["picking_no"],
    )


def _confirm_pick(
    client: TestClient,
    session_id: int,
    quantity: int | str,
    operation_id: str,
):
    return client.post(
        f"/api/v1/scan-sessions/{session_id}/confirm-pick",
        json={"quantity": quantity, "client_operation_id": operation_id},
    )


def test_scan_session_accepts_supported_context_identifiers_and_duplicates(
    client: TestClient, seed: dict
) -> None:
    lot = _inventory(client, seed)
    fba_response = client.post(
        "/api/v1/fba",
        json={
            "warehouse_id": seed["warehouse"].id,
            "customer_id": seed["customer"].id,
            "amazon_fc_code": "ONT8",
        },
    )
    assert fba_response.status_code == 201, fba_response.text
    fba = fba_response.json()
    fba_allocation_response = client.post(
        f"/api/v1/fba/{fba['id']}/allocate",
        json={"inventory_lot_id": lot["id"], "pallet_qty": 4},
    )
    assert fba_allocation_response.status_code == 200, fba_allocation_response.text
    fba_allocation = fba_allocation_response.json()
    outbound_response = client.post(
        "/api/v1/outbounds",
        json={
            "customer_id": seed["customer"].id,
            "warehouse_id": seed["warehouse"].id,
            "carrier_id": seed["carrier"].id,
            "ob_type": "FBA",
            "delivery_type": "FTL",
            "fba_shipment_id": fba["id"],
            "fc_code": "ONT8",
        },
    )
    assert outbound_response.status_code == 201, outbound_response.text
    outbound = outbound_response.json()
    allocated = client.post(
        f"/api/v1/outbounds/{outbound['id']}/allocate",
        json={
            "inventory_lot_id": lot["id"],
            "fba_allocation_id": fba_allocation["id"],
            "pallet_qty": 4,
        },
    )
    assert allocated.status_code == 200, allocated.text
    picking = _picking(client, outbound["id"])
    session = _session(
        client,
        seed,
        outbound_id=outbound["id"],
        picking_id=picking["id"],
    )
    assert session["session_no"].startswith(f"SC-{date.today():%Y%m%d}-")

    values = [
        (f"\r\n {lot['lot_no'].lower()} \r\n", "INVENTORY_LOT"),
        ("SCAN-CNTR.1", "CONTAINER"),
        (seed["location"].location_code, "LOCATION"),
        (outbound["ob_no"], "OUTBOUND"),
        (picking["picking_no"], "PICKING"),
        (fba["fba_no"], "FBA"),
    ]
    for value, scan_type in values:
        response = _scan(client, session["id"], value)
        assert response.status_code == 200, response.text
        assert response.json()["event"]["result"] == "ACCEPTED"
        assert response.json()["event"]["scan_type"] == scan_type

    duplicate = _scan(client, session["id"], lot["lot_no"].upper())
    assert duplicate.status_code == 200, duplicate.text
    duplicate_body = duplicate.json()
    assert duplicate_body["event"]["result"] == "DUPLICATE"
    assert duplicate_body["counters"] == {
        "total": 7,
        "accepted": 6,
        "duplicate": 1,
        "rejected": 0,
        "result_counts": {"ACCEPTED": 6, "DUPLICATE": 1},
    }
    assert duplicate_body["event"]["normalized_value"] == lot["lot_no"].upper()


def test_scan_failures_are_structured_and_history_is_paginated(
    client: TestClient, seed: dict
) -> None:
    session = _session(client, seed)
    empty = _scan(client, session["id"], "\r\n  ")
    assert empty.status_code == 200
    assert empty.json()["event"]["result"] == "REJECTED"
    assert empty.json()["event"]["normalized_value"] == ""

    for number in range(22):
        response = _scan(client, session["id"], f"UNKNOWN-{number}")
        assert response.status_code == 200
        assert response.json()["event"]["result"] == "NOT_FOUND"
    assert len(response.json()["recent_events"]) == 20

    history = client.get(
        f"/api/v1/scan-sessions/{session['id']}/events",
        params={"limit": 5, "offset": 2},
    )
    assert history.status_code == 200, history.text
    assert history.json()["total"] == 23
    assert len(history.json()["data"]) == 5
    event_ids = [event["id"] for event in history.json()["data"]]
    assert event_ids == sorted(event_ids, reverse=True)
    assert history.json()["data"][0]["normalized_value"] == "UNKNOWN-19"

    extra_field = client.post(
        f"/api/v1/scan-sessions/{session['id']}/scan",
        json={"value": "anything", "quantity": 99},
    )
    assert extra_field.status_code == 422

    invalid_warehouse = client.post(
        "/api/v1/scan-sessions",
        json={"warehouse_id": 999_999, "operation_type": "STAGE"},
    )
    assert invalid_warehouse.status_code == 422


def test_scan_context_reports_wrong_outbound_location_and_warehouse(
    client: TestClient, db: Session, seed: dict
) -> None:
    first_lot = _inventory(client, seed, "SCAN-FIRST")
    second_lot = _inventory(client, seed, "SCAN-SECOND")
    first_ob = _outbound(client, seed, first_lot)
    second_ob = _outbound(client, seed, second_lot)
    picking = _picking(client, first_ob["id"])

    area = db.scalar(select(WarehouseArea).where(WarehouseArea.warehouse_id == seed["warehouse"].id))
    other_location = WarehouseLocation(
        warehouse_id=seed["warehouse"].id,
        area_id=area.id,
        location_code="A02",
        location_name="A02",
    )
    other_warehouse = Warehouse(
        warehouse_code="DLX-ONT",
        warehouse_name="DLX Ontario",
        address="2 Warehouse Way",
        city="Ontario",
        state="CA",
        zip_code="91761",
    )
    db.add_all([other_location, other_warehouse])
    db.flush()
    other_area = WarehouseArea(
        warehouse_id=other_warehouse.id,
        area_code="STORAGE",
        area_name="Storage",
    )
    db.add(other_area)
    db.flush()
    remote_location = WarehouseLocation(
        warehouse_id=other_warehouse.id,
        area_id=other_area.id,
        location_code="REMOTE-01",
        location_name="Remote 01",
    )
    db.add(remote_location)
    db.commit()

    session = _session(
        client,
        seed,
        outbound_id=first_ob["id"],
        picking_id=picking["id"],
    )
    wrong_outbound = _scan(client, session["id"], second_lot["lot_no"])
    assert wrong_outbound.json()["event"]["result"] == "WRONG_OUTBOUND"
    wrong_location = _scan(client, session["id"], "A02")
    assert wrong_location.json()["event"]["result"] == "WRONG_LOCATION"
    wrong_warehouse = _scan(client, session["id"], "REMOTE-01")
    assert wrong_warehouse.json()["event"]["result"] == "WRONG_WAREHOUSE"

    bad_context = client.post(
        "/api/v1/scan-sessions",
        json={
            "warehouse_id": other_warehouse.id,
            "operation_type": "STAGE",
            "outbound_id": first_ob["id"],
        },
    )
    assert bad_context.status_code == 422

    mismatched_picking = client.post(
        "/api/v1/scan-sessions",
        json={
            "warehouse_id": seed["warehouse"].id,
            "operation_type": "STAGE",
            "outbound_id": second_ob["id"],
            "picking_id": picking["id"],
        },
    )
    assert mismatched_picking.status_code == 422


def test_scans_do_not_mutate_inventory_allocation_or_outbound(
    client: TestClient, db: Session, seed: dict
) -> None:
    lot = _inventory(client, seed)
    outbound = _outbound(client, seed, lot)
    session = _session(client, seed, outbound_id=outbound["id"])

    db.expire_all()
    stored_lot = db.get(InventoryLot, lot["id"])
    allocation = db.scalar(
        select(OutboundInventoryAllocation).where(
            OutboundInventoryAllocation.outbound_order_id == outbound["id"]
        )
    )
    stored_outbound = db.get(OutboundOrder, outbound["id"])
    before = (
        stored_lot.available_pallet_qty,
        stored_lot.allocated_pallet_qty,
        allocation.allocated_pallet_qty,
        allocation.completed_pallet_qty,
        stored_outbound.status,
    )

    for value in (lot["lot_no"], lot["lot_no"], "DOES-NOT-EXIST"):
        assert _scan(client, session["id"], value).status_code == 200

    db.expire_all()
    stored_lot = db.get(InventoryLot, lot["id"])
    allocation = db.get(OutboundInventoryAllocation, allocation.id)
    stored_outbound = db.get(OutboundOrder, outbound["id"])
    after = (
        stored_lot.available_pallet_qty,
        stored_lot.allocated_pallet_qty,
        allocation.allocated_pallet_qty,
        allocation.completed_pallet_qty,
        stored_outbound.status,
    )
    assert after == before


@pytest.mark.parametrize("transition", ["complete", "cancel"])
def test_terminal_session_records_invalid_state_and_rejects_second_transition(
    client: TestClient, seed: dict, transition: str
) -> None:
    session = _session(client, seed)
    transitioned = client.post(f"/api/v1/scan-sessions/{session['id']}/{transition}")
    assert transitioned.status_code == 200, transitioned.text
    expected = "COMPLETED" if transition == "complete" else "CANCELED"
    assert transitioned.json()["session"]["status"] == expected

    terminal_scan = _scan(client, session["id"], "ANYTHING")
    assert terminal_scan.status_code == 200
    assert terminal_scan.json()["event"]["result"] == "INVALID_STATE"
    assert client.post(f"/api/v1/scan-sessions/{session['id']}/{transition}").status_code == 409


def test_scan_events_are_append_only_in_orm(client: TestClient, db: Session, seed: dict) -> None:
    session = _session(client, seed)
    _scan(client, session["id"], "UNKNOWN")
    event = db.scalar(select(ScanEvent))
    event.message = "mutated"
    with pytest.raises(ValueError, match="append-only"):
        db.commit()
    db.rollback()

    event = db.get(ScanEvent, event.id)
    db.delete(event)
    with pytest.raises(ValueError, match="append-only"):
        db.commit()
    db.rollback()


def test_scan_permissions_and_owner_scope_do_not_leak_sessions(
    client: TestClient, db: Session, seed: dict
) -> None:
    session = _session(client, seed)
    anonymous = TestClient(client.app)
    assert anonymous.get(f"/api/v1/scan-sessions/{session['id']}").status_code == 401
    assert anonymous.post(
        "/api/v1/scan-sessions",
        json={"warehouse_id": seed["warehouse"].id, "operation_type": "STAGE"},
    ).status_code == 401

    viewer_token = create_access_token(str(seed["viewer"].id))
    viewer = TestClient(client.app, headers={"Authorization": f"Bearer {viewer_token}"})
    assert viewer.post(
        "/api/v1/scan-sessions",
        json={"warehouse_id": seed["warehouse"].id, "operation_type": "STAGE"},
    ).status_code == 403
    assert viewer.get(f"/api/v1/scan-sessions/{session['id']}").status_code == 404

    operator = User(
        username="scan-operator",
        display_name="Scan Operator",
        email="scan.operator@test.local",
        password_hash=hash_password("WarehousePassword!"),
        role=UserRole.OUTBOUND,
    )
    db.add(operator)
    db.commit()
    operator_token = create_access_token(str(operator.id))
    operator_client = TestClient(
        client.app, headers={"Authorization": f"Bearer {operator_token}"}
    )
    created = operator_client.post(
        "/api/v1/scan-sessions",
        json={"warehouse_id": seed["warehouse"].id, "operation_type": "STAGE"},
    )
    assert created.status_code == 201, created.text
    assert client.get(
        f"/api/v1/scan-sessions/{created.json()['session']['id']}"
    ).status_code == 200
    assert operator_client.get(f"/api/v1/scan-sessions/{session['id']}").status_code == 404

    restricted_operator = User(
        username="restricted-scan-operator",
        display_name="Restricted Scan Operator",
        email="restricted.scan.operator@test.local",
        password_hash=hash_password("WarehousePassword!"),
        role=UserRole.OUTBOUND,
        warehouse_scope_mode=ScopeMode.SELECTED,
    )
    db.add(restricted_operator)
    db.commit()
    restricted_client = TestClient(
        client.app,
        headers={"Authorization": f"Bearer {create_access_token(str(restricted_operator.id))}"},
    )
    assert restricted_client.post(
        "/api/v1/scan-sessions",
        json={"warehouse_id": seed["warehouse"].id, "operation_type": "STAGE"},
    ).status_code == 403


def test_pick_session_uses_stable_reference_infers_outbound_and_is_unique(
    client: TestClient, seed: dict
) -> None:
    lot = _inventory(client, seed, "PICK-SESSION")
    outbound = _outbound(client, seed, lot)
    picking = _picking(client, outbound["id"])

    session = _pick_session(client, seed, picking)
    assert session["operation_type"] == "PICK"
    assert session["picking_id"] == picking["id"]
    assert session["outbound_id"] == outbound["id"]

    duplicate = client.post(
        "/api/v1/scan-sessions",
        json={
            "warehouse_id": seed["warehouse"].id,
            "operation_type": "PICK",
            "picking_ref": picking["picking_no"],
        },
    )
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]

    missing_picking = client.post(
        "/api/v1/scan-sessions",
        json={"warehouse_id": seed["warehouse"].id, "operation_type": "PICK"},
    )
    assert missing_picking.status_code == 422


@pytest.mark.parametrize(
    "terminal_status",
    [PickingStatus.COMPLETED, PickingStatus.CANCELED, PickingStatus.EXCEPTION],
)
def test_pick_session_rejects_mismatched_outbound_and_terminal_picking(
    client: TestClient,
    db: Session,
    seed: dict,
    terminal_status: PickingStatus,
) -> None:
    lot = _inventory(client, seed, f"PICK-CONTEXT-{terminal_status}")
    outbound = _outbound(client, seed, lot)
    other_outbound = _outbound(client, seed)
    picking = _picking(client, outbound["id"])

    mismatched = client.post(
        "/api/v1/scan-sessions",
        json={
            "warehouse_id": seed["warehouse"].id,
            "operation_type": "PICK",
            "outbound_id": other_outbound["id"],
            "picking_ref": picking["picking_no"],
        },
    )
    assert mismatched.status_code == 422
    assert "does not belong" in mismatched.json()["detail"]

    stored_picking = db.get(PickingList, picking["id"])
    stored_picking.status = terminal_status
    db.commit()

    terminal = client.post(
        "/api/v1/scan-sessions",
        json={
            "warehouse_id": seed["warehouse"].id,
            "operation_type": "PICK",
            "picking_ref": picking["picking_no"],
        },
    )
    assert terminal.status_code == 409
    assert terminal.json()["detail"] == "Picking list is not open for scan execution"


def test_pick_scan_enforces_location_lot_quantity_sequence(
    client: TestClient, db: Session, seed: dict
) -> None:
    lot = _inventory(client, seed, "PICK-SEQUENCE")
    unrelated_lot = _inventory(client, seed, "PICK-UNRELATED")
    outbound = _outbound(client, seed, lot)
    picking = _picking(client, outbound["id"])

    area = db.scalar(
        select(WarehouseArea).where(WarehouseArea.warehouse_id == seed["warehouse"].id)
    )
    other_location = WarehouseLocation(
        warehouse_id=seed["warehouse"].id,
        area_id=area.id,
        location_code="PICK-A02",
        location_name="Pick A02",
    )
    db.add(other_location)
    db.commit()

    session = _pick_session(client, seed, picking)
    session_id = session["id"]

    wrong_type = _scan(client, session_id, lot["lot_no"])
    assert wrong_type.status_code == 200
    assert wrong_type.json()["event"]["result"] == "NOT_FOUND"
    assert wrong_type.json()["picking_summary"]["current_step"] == "EXPECT_LOCATION"

    wrong_location = _scan(client, session_id, other_location.location_code)
    assert wrong_location.json()["event"]["result"] == "WRONG_LOCATION"

    location = _scan(client, session_id, seed["location"].location_code)
    assert location.json()["event"]["result"] == "ACCEPTED"
    assert location.json()["picking_summary"]["current_step"] == "EXPECT_LOT"

    source_mismatch = _scan(client, session_id, unrelated_lot["lot_no"])
    assert source_mismatch.json()["event"]["result"] == "PICK_SOURCE_MISMATCH"
    assert source_mismatch.json()["picking_summary"]["current_step"] == "EXPECT_LOT"

    source = _scan(client, session_id, lot["lot_no"])
    assert source.json()["event"]["result"] == "ACCEPTED"
    assert source.json()["picking_summary"]["current_step"] == "EXPECT_QUANTITY_CONFIRMATION"
    assert Decimal(source.json()["picking_summary"]["current_item_available_qty"]) == 4

    extra_scan = _scan(client, session_id, seed["location"].location_code)
    assert extra_scan.json()["event"]["result"] == "INVALID_STATE"

    reset = client.post(f"/api/v1/scan-sessions/{session_id}/reset-step")
    assert reset.status_code == 200, reset.text
    assert reset.json()["picking_summary"]["current_step"] == "EXPECT_LOCATION"


def test_pick_confirmation_is_atomic_idempotent_and_does_not_complete_outbound(
    client: TestClient, db: Session, seed: dict
) -> None:
    lot = _inventory(client, seed, "PICK-ATOMIC")
    outbound = _outbound(client, seed, lot)
    picking = _picking(client, outbound["id"])
    session = _pick_session(client, seed, picking)
    session_id = session["id"]

    allocation = db.scalar(
        select(OutboundInventoryAllocation).where(
            OutboundInventoryAllocation.outbound_order_id == outbound["id"]
        )
    )
    db.expire_all()
    stored_lot = db.get(InventoryLot, lot["id"])
    stored_outbound = db.get(OutboundOrder, outbound["id"])
    before = (
        stored_lot.available_pallet_qty,
        stored_lot.allocated_pallet_qty,
        allocation.allocated_pallet_qty,
        allocation.completed_pallet_qty,
        stored_outbound.status,
    )

    assert _scan(client, session_id, seed["location"].location_code).json()["event"]["result"] == "ACCEPTED"
    assert _scan(client, session_id, lot["lot_no"]).json()["event"]["result"] == "ACCEPTED"
    overpick = _confirm_pick(client, session_id, 5, "pick-over")
    assert overpick.status_code == 409
    assert "remaining quantity" in overpick.json()["detail"]

    first = _confirm_pick(client, session_id, 2, "pick-operation-1")
    assert first.status_code == 200, first.text
    assert first.json()["event"]["event_type"] == "PICK_CONFIRMED"
    assert Decimal(first.json()["event"]["quantity"]) == 2
    assert first.json()["picking_summary"]["picking_status"] == "IN_PROGRESS"
    assert Decimal(first.json()["picking_summary"]["remaining_qty"]) == 2

    duplicate = _confirm_pick(client, session_id, 2, "pick-operation-1")
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["event"]["id"] == first.json()["event"]["id"]

    db.expire_all()
    item = db.scalar(
        select(PickingListItem).where(PickingListItem.picking_list_id == picking["id"])
    )
    assert item.picked_pallet_qty == 2
    assert db.scalar(
        select(ScanEvent).where(ScanEvent.client_operation_id == "pick-operation-1")
    ) is not None

    stored_lot = db.get(InventoryLot, lot["id"])
    allocation = db.get(OutboundInventoryAllocation, allocation.id)
    stored_outbound = db.get(OutboundOrder, outbound["id"])
    after = (
        stored_lot.available_pallet_qty,
        stored_lot.allocated_pallet_qty,
        allocation.allocated_pallet_qty,
        allocation.completed_pallet_qty,
        stored_outbound.status,
    )
    assert after == before


def test_pick_list_completes_only_after_every_allocation_item_is_picked(
    client: TestClient, db: Session, seed: dict
) -> None:
    first_lot = _inventory(client, seed, "PICK-MULTI-1")
    second_lot = _inventory(client, seed, "PICK-MULTI-2")
    outbound = _outbound(client, seed, first_lot)
    second_allocation = client.post(
        f"/api/v1/outbounds/{outbound['id']}/allocate",
        json={"inventory_lot_id": second_lot["id"], "pallet_qty": 4},
    )
    assert second_allocation.status_code == 200, second_allocation.text
    picking = _picking(client, outbound["id"])
    session = _pick_session(client, seed, picking)

    for lot, operation_id in (
        (first_lot, "multi-pick-1"),
        (second_lot, "multi-pick-2"),
    ):
        assert _scan(client, session["id"], seed["location"].location_code).json()["event"]["result"] == "ACCEPTED"
        assert _scan(client, session["id"], lot["lot_no"]).json()["event"]["result"] == "ACCEPTED"
        confirmed = _confirm_pick(client, session["id"], 4, operation_id)
        assert confirmed.status_code == 200, confirmed.text
        db.expire_all()
        status_value = db.get(PickingList, picking["id"]).status
        if operation_id == "multi-pick-1":
            assert status_value == PickingStatus.IN_PROGRESS
            assert confirmed.json()["picking_summary"]["picking_status"] == "IN_PROGRESS"
        else:
            assert status_value == PickingStatus.COMPLETED
            assert confirmed.json()["picking_summary"]["picking_status"] == "COMPLETED"


def test_cancel_or_complete_session_does_not_rollback_or_complete_partial_pick(
    client: TestClient, db: Session, seed: dict
) -> None:
    lot = _inventory(client, seed, "PICK-PARTIAL")
    outbound = _outbound(client, seed, lot)
    picking = _picking(client, outbound["id"])
    session = _pick_session(client, seed, picking)

    _scan(client, session["id"], seed["location"].location_code)
    _scan(client, session["id"], lot["lot_no"])
    assert _confirm_pick(client, session["id"], 1, "partial-pick").status_code == 200
    canceled = client.post(f"/api/v1/scan-sessions/{session['id']}/cancel")
    assert canceled.status_code == 200

    db.expire_all()
    item = db.scalar(
        select(PickingListItem).where(PickingListItem.picking_list_id == picking["id"])
    )
    assert item.picked_pallet_qty == 1
    assert db.get(PickingList, picking["id"]).status == PickingStatus.IN_PROGRESS

    resumed = _pick_session(client, seed, picking)
    completed_session = client.post(f"/api/v1/scan-sessions/{resumed['id']}/complete")
    assert completed_session.status_code == 200
    assert completed_session.json()["session"]["status"] == "COMPLETED"
    db.expire_all()
    assert db.get(PickingList, picking["id"]).status == PickingStatus.IN_PROGRESS
