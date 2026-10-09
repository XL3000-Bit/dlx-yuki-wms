from decimal import Decimal

from app.core.security import create_access_token
from app.models import InboundRecord, InventoryLot, OutboundInventoryAllocation, Load, LoadVerificationTransaction, OutboundOrder, PickingList, PickingListItem


def _load_member(db, seed, suffix: str = "1"):
    load = Load(
        load_no=f"LOAD-112-{suffix}", dispatch_business_type="PRIVATE",
        warehouse_id=seed["warehouse"].id,
        created_by=seed["admin"].id,
    )
    db.add(load)
    db.flush()
    outbound = OutboundOrder(
        ob_no=f"OB-112-{suffix}", dispatch_business_type="PRIVATE", status=3,
        customer_id=seed["customer"].id,
        warehouse_id=seed["warehouse"].id,
        load_id=load.id,
        created_by=seed["admin"].id,
    )
    db.add(outbound)
    db.flush()
    picking = PickingList(
        picking_no=f"PICK-112-{suffix}",
        outbound_order_id=outbound.id,
        status=3, completed_by=seed["admin"].id,
        created_by=seed["admin"].id,
    )
    db.add(picking)
    db.flush()
    inbound = InboundRecord(inbound_no=f"IN-112-{suffix}", container_number=f"CONT-{suffix}", warehouse_id=seed["warehouse"].id, customer_id=seed["customer"].id, created_by=seed["admin"].id)
    db.add(inbound); db.flush()
    lot = InventoryLot(lot_no=f"LOT-{suffix}", source_inbound_id=inbound.id, container_number=inbound.container_number, warehouse_id=seed["warehouse"].id, customer_id=seed["customer"].id, created_by=seed["admin"].id,
        original_pallet_qty=10, available_pallet_qty=0, allocated_pallet_qty=10, original_carton_qty=0, available_carton_qty=0, original_weight_lbs=0, available_weight_lbs=0, original_cbm=0, available_cbm=0)
    db.add(lot); db.flush()
    inv = OutboundInventoryAllocation(outbound_order_id=outbound.id, inventory_lot_id=lot.id, allocated_pallet_qty=10, created_by=seed["admin"].id)
    db.add(inv); db.flush()
    item = PickingListItem(
        picking_list_id=picking.id,
        outbound_allocation_id=inv.id,
        inventory_lot_id=lot.id,
        location_id=seed["location"].id,
        lot_no=f"LOT-{suffix}",
        container_number=f"CONT-{suffix}",
        planned_pallet_qty=Decimal("10"),
        planned_carton_qty=Decimal("0"),
        planned_weight_lbs=Decimal("0"),
        planned_cbm=Decimal("0"),
        picked_pallet_qty=Decimal("10"),
        picked_carton_qty=Decimal("0"),
        picked_weight_lbs=Decimal("0"),
        picked_cbm=Decimal("0"),
        sequence_no=1,
    )
    db.add(item)
    db.commit()
    return load, outbound, item


def _stage_payload(seed, outbound, item, quantity="4", action="STAGE"):
    return {
        "outbound_id": outbound.id,
        "picking_item_id": item.id,
        "staging_location_id": seed["location"].id,
        "quantity": quantity,
        "quantity_unit": "PALLET",
        "action": action,
    }


def test_stage_success(client, db, seed):
    load, outbound, item = _load_member(db, seed)
    response = client.post(f"/api/v1/loads/{load.id}/stage", json=_stage_payload(seed, outbound, item))
    assert response.status_code == 200
    assert response.json()["action"] == "STAGE"
    assert response.json()["quantity"] == 4


def test_non_member_and_excessive_unstage_return_409(client, db, seed):
    load, outbound, item = _load_member(db, seed, "A")
    _, other_outbound, other_item = _load_member(db, seed, "B")
    non_member = client.post(
        f"/api/v1/loads/{load.id}/stage",
        json=_stage_payload(seed, other_outbound, other_item),
    )
    assert non_member.status_code == 409

    assert client.post(
        f"/api/v1/loads/{load.id}/stage",
        json=_stage_payload(seed, outbound, item, "2"),
    ).status_code == 200
    excessive = client.post(
        f"/api/v1/loads/{load.id}/stage",
        json=_stage_payload(seed, outbound, item, "3", "UNSTAGE"),
    )
    assert excessive.status_code == 409


def test_verify_complete_saves_fingerprint_and_later_stage_mismatches(client, db, seed):
    load, outbound, item = _load_member(db, seed)
    stage_url = f"/api/v1/loads/{load.id}/stage"
    assert client.post(stage_url, json=_stage_payload(seed, outbound, item, "4")).status_code == 200

    started = client.post(f"/api/v1/loads/{load.id}/verify/start", json={})
    assert started.status_code == 200
    run_id = started.json()["verification_run_id"]
    scanned = client.post(f"/api/v1/loads/{load.id}/verify/scan", json={
        "verification_run_id": run_id,
        "outbound_id": outbound.id,
        "picking_item_id": item.id,
        "quantity": "4",
        "quantity_unit": "PALLET",
    })
    assert scanned.status_code == 200
    completed = client.post(
        f"/api/v1/loads/{load.id}/verify/complete",
        json={"verification_run_id": run_id},
    )
    assert completed.status_code == 200
    assert completed.json()["manifest_fingerprint"]
    transaction = db.get(LoadVerificationTransaction, completed.json()["id"])
    assert transaction.manifest_fingerprint == completed.json()["manifest_fingerprint"]

    assert client.post(stage_url, json=_stage_payload(seed, outbound, item, "1")).status_code == 200
    summary = client.get(f"/api/v1/loads/{load.id}/execution-summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["current_manifest_fingerprint"] != body["saved_manifest_fingerprint"]
    assert body["manifest_matches"] is False


def test_viewer_post_is_forbidden(client, db, seed):
    load, outbound, item = _load_member(db, seed)
    client.headers["Authorization"] = f"Bearer {create_access_token(str(seed['viewer'].id))}"
    response = client.post(f"/api/v1/loads/{load.id}/stage", json=_stage_payload(seed, outbound, item))
    assert response.status_code == 403
