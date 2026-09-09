from datetime import date
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import func, select

from app.core.security import create_access_token, hash_password
from app.models import (
    AuditLog,
    BOL,
    InventoryLot,
    InventoryTransaction,
    OutboundOrder,
    PickingList,
    User,
)
from app.models.bol import BOLStatus
from app.models.outbound import OBStatus
from app.models.picking import PickingStatus
from app.models.user import ScopeMode, UserRole
from app.services.picking_bol import ensure_outbound_documents, generate_picking
from conftest import TestingSession


def make_ob(client, seed, suffix=""):
    inbound = client.post("/api/v1/inbound", json={
        "container_number": f"PK-CNTR{suffix}",
        "customer_id": seed["customer"].id,
        "warehouse_id": seed["warehouse"].id,
        "received_date": str(date.today()),
        "fc_code": "ONT8",
        "pallet_qty": 10,
        "carton_qty": 20,
        "weight_lbs": 100,
        "cbm": 2,
        "location_id": seed["location"].id,
        "status": 3,
    }).json()
    lot = client.post(f"/api/v1/inbound/{inbound['id']}/receive-to-inventory").json()
    outbound = client.post("/api/v1/outbounds", json={
        "warehouse_id": seed["warehouse"].id,
        "customer_id": seed["customer"].id,
        "carrier_id": seed["carrier"].id,
    }).json()
    allocated = client.post(f"/api/v1/outbounds/{outbound['id']}/allocate", json={
        "inventory_lot_id": lot["id"],
        "pallet_qty": 10,
        "carton_qty": 20,
    })
    assert allocated.status_code == 200, allocated.text
    return outbound, lot


def active_documents(db, outbound_id):
    pickings = db.scalar(select(func.count()).select_from(PickingList).where(
        PickingList.outbound_order_id == outbound_id,
        PickingList.status != PickingStatus.CANCELED,
    ))
    bols = db.scalar(select(func.count()).select_from(BOL).where(
        BOL.outbound_order_id == outbound_id,
        BOL.status != BOLStatus.CANCELED,
    ))
    return pickings, bols


def audit_count(db, outbound_id, action):
    model = PickingList if action == "CREATE_PICKING_LIST" else BOL
    return db.scalar(select(func.count()).select_from(AuditLog).join(
        model, model.id == AuditLog.entity_id,
    ).where(AuditLog.action == action, model.outbound_order_id == outbound_id))


def inventory_snapshot(db, lot_id):
    lot = db.get(InventoryLot, lot_id)
    transaction_count = db.scalar(select(func.count()).select_from(InventoryTransaction).where(
        InventoryTransaction.inventory_lot_id == lot_id,
    ))
    return (
        lot.available_pallet_qty,
        lot.allocated_pallet_qty,
        lot.available_carton_qty,
        lot.allocated_carton_qty,
        transaction_count,
    )


def test_picking_and_bol_snapshot(client: TestClient, seed):
    outbound, _ = make_ob(client, seed)
    picking = client.post(f"/api/v1/outbounds/{outbound['id']}/picking-lists")
    assert picking.status_code == 200, picking.text
    body = picking.json()
    assert body["picking_no"].startswith("PK")
    assert body["planned_pallet_qty"] == "10.00"
    assert body["ob_no"] == outbound["ob_no"]
    assert body["outbound_order_id"] == outbound["id"]
    detail = client.get(f"/api/v1/picking-lists/{body['id']}").json()
    assert detail["ob_no"] == outbound["ob_no"]
    assert detail["outbound_order_id"] == outbound["id"]
    listed = client.get("/api/v1/picking-lists").json()
    assert next(row for row in listed if row["id"] == body["id"])["ob_no"] == outbound["ob_no"]
    export = client.get(f"/api/v1/picking-lists/{body['id']}/xlsx")
    assert export.status_code == 200
    sheet = load_workbook(BytesIO(export.content), data_only=True).active
    assert sheet["B1"].value == "OB No"
    assert sheet["B2"].value == outbound["ob_no"]
    assert sheet["B2"].value != outbound["id"]
    second = client.post(f"/api/v1/outbounds/{outbound['id']}/picking-lists")
    assert second.status_code == 200, second.text
    assert second.json()["id"] == picking.json()["id"]
    assert client.post(f"/api/v1/picking-lists/{picking.json()['id']}/complete", json={}).status_code == 200
    bol = client.post(f"/api/v1/outbounds/{outbound['id']}/bol")
    assert bol.status_code == 200, bol.text
    assert bol.json()["total_pallet_qty"] == "10.00"
    assert bol.json()["amazon_bol_ready"] is True
    assert client.get(f"/api/v1/bols/{bol.json()['id']}/pdf").headers["content-type"] == "application/pdf"
    assert client.get(f"/api/v1/bols/{bol.json()['id']}/xlsx").status_code == 200
    documents = client.get("/api/v1/documents", params={"bol_id": bol.json()["id"]})
    assert documents.status_code == 200, documents.text
    assert documents.json()["data"][0]["document_type"] == "BOL"


def test_ensure_first_replay_and_inventory_stability(client: TestClient, seed, db):
    outbound, lot = make_ob(client, seed)
    before = inventory_snapshot(db, lot["id"])
    first = client.post(f"/api/v1/outbounds/{outbound['id']}/documents/ensure")
    second = client.post(f"/api/v1/outbounds/{outbound['id']}/documents/ensure")

    assert first.status_code == second.status_code == 200
    assert first.json()["picking_list_created"] is True
    assert first.json()["bol_created"] is True
    assert first.json()["documents_reused"] is False
    assert second.json()["picking_list_created"] is False
    assert second.json()["bol_created"] is False
    assert second.json()["documents_reused"] is True
    assert first.json()["picking_list_id"] == second.json()["picking_list_id"]
    assert first.json()["bol_id"] == second.json()["bol_id"]
    assert active_documents(db, outbound["id"]) == (1, 1)
    assert audit_count(db, outbound["id"], "CREATE_PICKING_LIST") == 1
    assert audit_count(db, outbound["id"], "CREATE_BOL") == 1
    assert inventory_snapshot(db, lot["id"]) == before


def test_ensure_replays_in_a_new_session(client: TestClient, seed, db):
    outbound, _ = make_ob(client, seed)
    first = client.post(f"/api/v1/outbounds/{outbound['id']}/documents/ensure").json()
    db.close()
    with TestingSession() as other:
        replay = ensure_outbound_documents(other, outbound["id"], seed["admin"].id)
        other.commit()
        assert replay.picking.id == first["picking_list_id"]
        assert replay.bol.id == first["bol_id"]
        assert replay.picking_list_created is False
        assert replay.bol_created is False
        assert active_documents(other, outbound["id"]) == (1, 1)


@pytest.mark.parametrize("existing", ["picking", "bol"])
def test_ensure_fills_only_the_missing_document(client: TestClient, seed, db, existing):
    outbound, _ = make_ob(client, seed)
    response = client.post(
        f"/api/v1/outbounds/{outbound['id']}/picking-lists"
        if existing == "picking" else f"/api/v1/outbounds/{outbound['id']}/bol"
    )
    assert response.status_code == 200, response.text

    ensured = client.post(f"/api/v1/outbounds/{outbound['id']}/documents/ensure")
    assert ensured.status_code == 200, ensured.text
    body = ensured.json()
    assert body["picking_list_created"] is (existing == "bol")
    assert body["bol_created"] is (existing == "picking")
    assert body["documents_reused"] is True
    assert active_documents(db, outbound["id"]) == (1, 1)


def test_canceled_documents_are_replaced_once(client: TestClient, seed, db):
    outbound, _ = make_ob(client, seed)
    first = client.post(f"/api/v1/outbounds/{outbound['id']}/documents/ensure").json()
    db.get(PickingList, first["picking_list_id"]).status = PickingStatus.CANCELED
    db.get(BOL, first["bol_id"]).status = BOLStatus.CANCELED
    db.commit()

    replacement = client.post(f"/api/v1/outbounds/{outbound['id']}/documents/ensure").json()
    replay = client.post(f"/api/v1/outbounds/{outbound['id']}/documents/ensure").json()
    assert replacement["picking_list_created"] is replacement["bol_created"] is True
    assert replacement["picking_list_id"] != first["picking_list_id"]
    assert replacement["bol_id"] != first["bol_id"]
    assert replay["picking_list_id"] == replacement["picking_list_id"]
    assert replay["bol_id"] == replacement["bol_id"]
    assert active_documents(db, outbound["id"]) == (1, 1)


def test_confirm_creates_documents_and_repeated_confirm_is_stable(client: TestClient, seed, db):
    outbound, _ = make_ob(client, seed)
    confirmed = client.post(f"/api/v1/outbounds/{outbound['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == OBStatus.CONFIRMED
    assert active_documents(db, outbound["id"]) == (1, 1)
    ids = (
        db.scalar(select(PickingList.id).where(PickingList.outbound_order_id == outbound["id"])),
        db.scalar(select(BOL.id).where(BOL.outbound_order_id == outbound["id"])),
    )
    repeated = client.post(f"/api/v1/outbounds/{outbound['id']}/confirm")
    assert repeated.status_code == 409, repeated.text
    assert repeated.json()["detail"] == "Invalid status transition: Confirmed to Confirmed"
    assert active_documents(db, outbound["id"]) == (1, 1)
    assert ids == (
        db.scalar(select(PickingList.id).where(PickingList.outbound_order_id == outbound["id"])),
        db.scalar(select(BOL.id).where(BOL.outbound_order_id == outbound["id"])),
    )


def test_confirm_reuses_existing_pair(client: TestClient, seed, db):
    outbound, _ = make_ob(client, seed)
    ensured = client.post(f"/api/v1/outbounds/{outbound['id']}/documents/ensure").json()
    confirmed = client.post(f"/api/v1/outbounds/{outbound['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert active_documents(db, outbound["id"]) == (1, 1)
    assert db.get(PickingList, ensured["picking_list_id"]) is not None
    assert db.get(BOL, ensured["bol_id"]) is not None
    assert audit_count(db, outbound["id"], "CREATE_PICKING_LIST") == 1
    assert audit_count(db, outbound["id"], "CREATE_BOL") == 1


def test_confirm_rolls_back_when_picking_creation_fails(client: TestClient, seed, db, monkeypatch):
    outbound, _ = make_ob(client, seed)

    def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic picking failure")

    monkeypatch.setattr("app.services.picking_bol.ensure_outbound_documents", fail)
    with pytest.raises(RuntimeError, match="synthetic picking failure"):
        client.post(f"/api/v1/outbounds/{outbound['id']}/confirm")
    db.expire_all()
    assert db.get(OutboundOrder, outbound["id"]).status == OBStatus.NEW
    assert active_documents(db, outbound["id"]) == (0, 0)


def test_confirm_rolls_back_flushed_picking_when_bol_creation_fails(client: TestClient, seed, db, monkeypatch):
    outbound, _ = make_ob(client, seed)

    def fail_after_picking(session, outbound_id, user_id):
        generate_picking(session, outbound_id, user_id, commit=False)
        session.flush()
        raise RuntimeError("synthetic BOL failure")

    monkeypatch.setattr("app.services.picking_bol.ensure_outbound_documents", fail_after_picking)
    with pytest.raises(RuntimeError, match="synthetic BOL failure"):
        client.post(f"/api/v1/outbounds/{outbound['id']}/confirm")
    db.expire_all()
    assert db.get(OutboundOrder, outbound["id"]).status == OBStatus.NEW
    assert active_documents(db, outbound["id"]) == (0, 0)
    assert audit_count(db, outbound["id"], "CREATE_PICKING_LIST") == 0


def test_ensure_and_confirm_enforce_permission_and_scope(client: TestClient, seed, db):
    outbound, _ = make_ob(client, seed)
    client.headers["Authorization"] = f"Bearer {create_access_token(str(seed['viewer'].id))}"
    assert client.post(f"/api/v1/outbounds/{outbound['id']}/documents/ensure").status_code == 403
    assert client.post(f"/api/v1/outbounds/{outbound['id']}/confirm").status_code == 403

    scoped = User(
        username="scoped",
        display_name="Scoped",
        email="scoped@test.local",
        password_hash=hash_password("WarehousePassword!"),
        role=UserRole.MANAGER,
        warehouse_scope_mode=ScopeMode.SELECTED,
        customer_scope_mode=ScopeMode.SELECTED,
    )
    db.add(scoped)
    db.commit()
    client.headers["Authorization"] = f"Bearer {create_access_token(str(scoped.id))}"
    assert client.post(f"/api/v1/outbounds/{outbound['id']}/documents/ensure").status_code == 404
    assert client.post(f"/api/v1/outbounds/{outbound['id']}/confirm").status_code == 404
    assert active_documents(db, outbound["id"]) == (0, 0)
