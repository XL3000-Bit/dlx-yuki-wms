"""Real API regressions for selecting the affected allocation response.

Each case gets conftest's independent memory SQLite database. This verifies
response identity and inventory effects, not PostgreSQL concurrency or a browser.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import InventoryLot, OutboundInventoryAllocation
from test_outbound import inventory, ob


QUANTITIES = ("pallet_qty", "carton_qty", "weight_lbs", "cbm")
CHANGE = dict(zip(QUANTITIES, ("1.00", "2.00", "100.00", "0.5000")))
RESPONSE_FIELDS = {
    "id", "inventory_lot_id", "fba_allocation_id", "lot_no",
    "container_number", "fc_code", "location", "source_type", "fba_no",
    "created_at", *(f"allocated_{field}" for field in QUANTITIES),
    *(f"completed_{field}" for field in QUANTITIES),
}


def post_ok(client, url, payload, status=200):
    response = client.post(url, json=payload)
    assert response.status_code == status, response.text
    return response.json()


def read_allocations(client, outbound):
    response = client.get(f"/api/v1/outbounds/{outbound['id']}/allocations")
    assert response.status_code == 200, response.text
    return {row["id"]: row for row in response.json()}


def lot_snapshot(db, lot):
    db.expire_all()
    table = InventoryLot.__table__
    return dict(db.execute(select(table).where(table.c.id == lot["id"])).mappings().one())


def assert_allocation_equal(actual, expected):
    """Decimal JSON strings can retain different trailing-zero scales."""
    assert set(actual) == set(expected) == RESPONSE_FIELDS
    quantity_fields = {f"{prefix}_{field}" for prefix in ("allocated", "completed") for field in QUANTITIES}
    for field in RESPONSE_FIELDS:
        if field in quantity_fields:
            assert isinstance(actual[field], str) and isinstance(expected[field], str)
            actual_value, expected_value = Decimal(actual[field]), Decimal(expected[field])
            assert actual_value.is_finite() and expected_value.is_finite()
            assert actual_value == expected_value, field
        else:
            assert actual[field] == expected[field], field


@pytest.fixture(params=["INVENTORY", "FBA"])
def two_allocations(request, client, db, seed):
    engine = db.get_bind()
    assert engine.dialect.name == "sqlite"
    assert engine.url.database in (None, "", ":memory:")
    source_type = request.param
    lots = [inventory(client, seed, container=f"RESPONSE-{source_type}-{name}") for name in ("A", "B")]
    shipment = None
    source_ids = [None, None]
    outbound_payload = ob(seed)
    if source_type == "FBA":
        shipment = post_ok(client, "/api/v1/fba", {
            "warehouse_id": seed["warehouse"].id,
            "customer_id": seed["customer"].id,
            "amazon_fc_code": "ONT8",
        }, status=201)
        source_ids = [post_ok(client, f"/api/v1/fba/{shipment['id']}/allocate", {
            "inventory_lot_id": lot["id"], "pallet_qty": "10.00",
            "carton_qty": "20.00", "weight_lbs": "1000.00", "cbm": "5.0000",
        })["id"] for lot in lots]
        outbound_payload.update(ob_type="FBA", fba_shipment_id=shipment["id"], fc_code="ONT8")
    outbound = post_ok(client, "/api/v1/outbounds", outbound_payload, status=201)
    allocation_payloads = []
    allocations = []
    for lot, source_id, quantities in zip(lots, source_ids, (
        ("2.00", "4.00", "200.00", "1.0000"),
        ("4.00", "8.00", "400.00", "2.0000"),
    )):
        payload = {"inventory_lot_id": lot["id"], **dict(zip(QUANTITIES, quantities))}
        if source_id is not None:
            payload["fba_allocation_id"] = source_id
        allocation_payloads.append(payload)
        allocations.append(post_ok(client, f"/api/v1/outbounds/{outbound['id']}/allocate", payload))
    assert allocations[0]["id"] < allocations[1]["id"]
    assert allocations[0]["inventory_lot_id"] == lots[0]["id"]
    assert allocations[1]["inventory_lot_id"] == lots[1]["id"]
    return {
        "outbound": outbound, "lots": lots, "source_ids": source_ids,
        "source_type": source_type, "shipment": shipment,
        "payloads": allocation_payloads, "allocations": allocations,
    }


def assert_effects_then_response(client, db, seed, context, target_index, before, lot_before, response, direction):
    """Check actual writes before identity, so RED means operation right / response wrong."""
    outbound = context["outbound"]
    target_id = context["allocations"][target_index]["id"]
    other_index = 1 - target_index
    other_id = context["allocations"][other_index]["id"]
    db.expire_all()
    stored = db.get(OutboundInventoryAllocation, target_id)
    assert stored.outbound_order_id == outbound["id"]
    assert stored.inventory_lot_id == context["lots"][target_index]["id"]
    assert stored.fba_allocation_id == context["source_ids"][target_index]
    assert tuple(getattr(stored, f"allocated_{field}") for field in QUANTITIES) == (
        Decimal("3.00"), Decimal("6.00"), Decimal("300.00"), Decimal("1.5000"),
    )
    assert all(getattr(stored, f"completed_{field}") == 0 for field in QUANTITIES)
    after = read_allocations(client, outbound)
    assert set(after) == set(before) == {target_id, other_id}
    assert_allocation_equal(after[other_id], before[other_id])
    assert lot_snapshot(db, context["lots"][other_index]) == lot_before[other_index]
    target_lot_after = lot_snapshot(db, context["lots"][target_index])
    if context["source_type"] == "FBA":
        assert target_lot_after == lot_before[target_index]
    else:
        for field in QUANTITIES:
            delta = direction * Decimal(CHANGE[field])
            assert target_lot_after[f"allocated_{field}"] == lot_before[target_index][f"allocated_{field}"] + delta
            assert target_lot_after[f"available_{field}"] == lot_before[target_index][f"available_{field}"] - delta

    assert response["id"] == target_id, "The operation changed the target, but returned another allocation"
    assert_allocation_equal(response, after[target_id])
    assert set(response) == RESPONSE_FIELDS
    assert response["inventory_lot_id"] == context["lots"][target_index]["id"]
    assert response["fba_allocation_id"] == context["source_ids"][target_index]
    assert response["lot_no"] == context["lots"][target_index]["lot_no"]
    assert response["container_number"] == context["lots"][target_index]["container_number"]
    assert response["fc_code"] == "ONT8"
    assert response["location"]["id"] == seed["location"].id
    assert response["location"]["code"] == seed["location"].location_code
    assert response["location"]["name"] == seed["location"].location_name
    assert response["source_type"] == context["source_type"]
    assert response["fba_no"] == (context["shipment"]["fba_no"] if context["shipment"] else None)
    assert response["created_at"] == before[target_id]["created_at"]


def test_allocating_again_to_a_returns_a_not_later_b(client, db, seed, two_allocations):
    context = two_allocations
    before = read_allocations(client, context["outbound"])
    lot_before = [lot_snapshot(db, lot) for lot in context["lots"]]
    response = post_ok(client, f"/api/v1/outbounds/{context['outbound']['id']}/allocate", {
        **context["payloads"][0], **CHANGE,
    })
    assert_effects_then_response(client, db, seed, context, 0, before, lot_before, response, direction=1)


def test_releasing_b_returns_b_not_first_a(client, db, seed, two_allocations):
    context = two_allocations
    before = read_allocations(client, context["outbound"])
    lot_before = [lot_snapshot(db, lot) for lot in context["lots"]]
    allocation_id = context["allocations"][1]["id"]
    response = post_ok(client, f"/api/v1/outbounds/{context['outbound']['id']}/allocations/{allocation_id}/release", CHANGE)
    assert_effects_then_response(client, db, seed, context, 1, before, lot_before, response, direction=-1)
