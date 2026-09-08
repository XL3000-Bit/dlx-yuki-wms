"""Existing API contracts exercised with synthetic data in conftest's memory SQLite."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.base import Base
from app.models import InventoryLot, OutboundInventoryAllocation
from test_outbound import inventory, ob


@pytest.fixture(autouse=True)
def memory_database_only(db):
    engine = db.get_bind()
    assert engine.dialect.name == "sqlite"
    assert engine.url.database in (None, "", ":memory:")


def post_ok(client, url, payload, expected_status=200):
    response = client.post(url, json=payload)
    assert response.status_code == expected_status, response.text
    return response.json()


def fba_source(client, seed, lot):
    shipment = post_ok(client, "/api/v1/fba", {
        "warehouse_id": seed["warehouse"].id,
        "customer_id": seed["customer"].id,
        "amazon_fc_code": "ONT8",
    }, expected_status=201)
    allocation = post_ok(client, f"/api/v1/fba/{shipment['id']}/allocate", {
        "inventory_lot_id": lot["id"], "pallet_qty": "10.00",
        "carton_qty": "20.00", "weight_lbs": "1000.00", "cbm": "5.0000",
    })
    assert not any(key.startswith("completed_") for key in allocation)
    assert allocation["inventory_lot_id"] == lot["id"]
    return shipment, allocation


def fba_outbound(client, seed, shipment):
    return post_ok(client, "/api/v1/outbounds", {
        **ob(seed), "ob_type": "FBA", "fba_shipment_id": shipment["id"],
        "fc_code": "ONT8",
    }, expected_status=201)


def payload(lot, allocation, **quantities):
    return {"inventory_lot_id": lot["id"], "fba_allocation_id": allocation["id"], **quantities}


def remaining(client, outbound):
    response = client.get(f"/api/v1/outbounds/{outbound['id']}/workbench-detail")
    assert response.status_code == 200, response.text
    return response.json()


def database_snapshot(db):
    """Include every table, including allocation, inventory transactions and audit logs."""
    db.expire_all()
    return {
        table.name: tuple(tuple(row) for row in db.execute(
            select(table).order_by(*table.primary_key.columns)
        ))
        for table in Base.metadata.sorted_tables
    }


def lot_snapshot(db, lot_id):
    db.expire_all()
    table = InventoryLot.__table__
    return tuple(db.execute(select(table).where(table.c.id == lot_id)).one())


def test_fba_remaining_accounts_for_a_different_outbound(client, db, seed):
    lot = inventory(client, seed, container="CONTRACT-CROSS-OB")
    shipment, allocation = fba_source(client, seed, lot)
    other = fba_outbound(client, seed, shipment)
    target = fba_outbound(client, seed, shipment)
    post_ok(client, f"/api/v1/outbounds/{other['id']}/allocate", payload(
        lot, allocation, pallet_qty="6.00", carton_qty="12.00",
        weight_lbs="600.00", cbm="3.0000",
    ))

    detail = remaining(client, target)
    assert detail["basic"]["id"] == target["id"]
    assert detail["basic"]["fba_id"] == shipment["id"]
    assert detail["allowed_actions"]["allocate"] is True
    assert len(detail["remaining_sources"]) == 1
    source = detail["remaining_sources"][0]
    assert (source["id"], source["fba_allocation_id"], source["inventory_lot_id"]) == (
        allocation["id"], allocation["id"], lot["id"],
    )
    assert source["source_type"] == "FBA"
    assert [source[f"remaining_{field}"] for field in (
        "pallet_qty", "carton_qty", "weight_lbs", "cbm",
    )] == ["4.00", "8.00", "400.00", "2.0000"]
    assert db.scalar(select(OutboundInventoryAllocation).where(
        OutboundInventoryAllocation.outbound_order_id == target["id"]
    )) is None
    db.expire_all()
    assert db.get(InventoryLot, lot["id"]).available_pallet_qty == 0


def test_colliding_fba_id_cannot_select_the_wrong_inventory_lot(client, db, seed):
    non_target = inventory(client, seed, container="CONTRACT-COLLIDING-LOT")
    target = inventory(client, seed, container="CONTRACT-CORRECT-LOT")
    shipment, allocation = fba_source(client, seed, target)
    assert allocation["id"] == non_target["id"]
    assert allocation["id"] != target["id"]
    outbound = fba_outbound(client, seed, shipment)
    url = f"/api/v1/outbounds/{outbound['id']}/allocate"

    before = database_snapshot(db)
    rejected = client.post(url, json=payload(non_target, allocation, pallet_qty="1.00"))
    assert rejected.status_code == 409, rejected.text
    assert database_snapshot(db) == before

    untouched = lot_snapshot(db, non_target["id"])
    accepted = post_ok(client, url, payload(target, allocation, pallet_qty="1.00"))
    db.expire_all()
    stored = db.get(OutboundInventoryAllocation, accepted["id"])
    assert stored.inventory_lot_id == target["id"]
    assert stored.fba_allocation_id == allocation["id"]
    assert stored.allocated_pallet_qty == Decimal("1.00")
    assert lot_snapshot(db, non_target["id"]) == untouched


def test_refreshed_remaining_zero_and_exhausted_source_contract(client, db, seed):
    lot = inventory(client, seed, container="CONTRACT-REFRESH-ZERO")
    shipment, allocation = fba_source(client, seed, lot)
    other = fba_outbound(client, seed, shipment)
    target = fba_outbound(client, seed, shipment)
    post_ok(client, f"/api/v1/outbounds/{other['id']}/allocate", payload(
        lot, allocation, pallet_qty="6.00", carton_qty="12.00",
        weight_lbs="600.00", cbm="3.0000",
    ))
    url = f"/api/v1/outbounds/{target['id']}/allocate"
    assert remaining(client, target)["remaining_sources"][0]["remaining_pallet_qty"] == "4.00"

    before = database_snapshot(db)
    rejected = client.post(url, json=payload(lot, allocation, pallet_qty="4.01"))
    assert rejected.status_code == 409, rejected.text
    assert database_snapshot(db) == before

    post_ok(client, url, payload(lot, allocation, pallet_qty="4.00"))
    source = remaining(client, target)["remaining_sources"][0]
    assert source["remaining_pallet_qty"] == "0.00"
    assert source["remaining_carton_qty"] == "8.00"
    post_ok(client, url, payload(
        lot, allocation, pallet_qty="0.00", carton_qty="8.00",
        weight_lbs="400.00", cbm="2.0000",
    ))
    assert remaining(client, target)["remaining_sources"] == []


def test_inventory_request_uses_own_lot_without_fba_association(client, db, seed):
    non_target = inventory(client, seed, container="CONTRACT-NORMAL-UNTOUCHED")
    target = inventory(client, seed, container="CONTRACT-NORMAL-TARGET")
    outbound = post_ok(client, "/api/v1/outbounds", ob(seed), expected_status=201)
    untouched = lot_snapshot(db, non_target["id"])
    accepted = post_ok(client, f"/api/v1/outbounds/{outbound['id']}/allocate", {
        "inventory_lot_id": target["id"], "pallet_qty": "1.25",
    })
    db.expire_all()
    stored = db.get(OutboundInventoryAllocation, accepted["id"])
    assert stored.inventory_lot_id == target["id"]
    assert stored.fba_allocation_id is None
    assert db.get(InventoryLot, target["id"]).available_pallet_qty == Decimal("8.75")
    assert lot_snapshot(db, non_target["id"]) == untouched
