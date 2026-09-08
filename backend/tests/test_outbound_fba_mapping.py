"""Independent API regressions for cumulative FBA allocation field mapping.

Real FastAPI handlers, services and ORM run against conftest's memory SQLite.
These tests do not claim PostgreSQL concurrency or browser coverage.
"""

from decimal import Decimal

import pytest
from sqlalchemy import event, select

from app.db.base import Base
from app.models import OutboundInventoryAllocation
from test_outbound import inventory
from test_outbound_source_contract import (
    database_snapshot,
    fba_outbound,
    fba_source,
    payload,
    post_ok,
    remaining,
)


QUANTITY_FIELDS = ("pallet_qty", "carton_qty", "weight_lbs", "cbm")
EXCESS_QUANTITIES = (
    ("pallet_qty", "4.01"),
    ("carton_qty", "8.01"),
    ("weight_lbs", "400.01"),
    ("cbm", "2.0001"),
)


@pytest.fixture
def allocated_fba(client, db, seed):
    """Every case gets its own database and first successful allocation."""
    engine = db.get_bind()
    assert engine.dialect.name == "sqlite"
    assert engine.url.database in (None, "", ":memory:")
    lot = inventory(client, seed, container="MAPPING-INDEPENDENT")
    shipment, source = fba_source(client, seed, lot)
    first_outbound = fba_outbound(client, seed, shipment)
    first = post_ok(client, f"/api/v1/outbounds/{first_outbound['id']}/allocate", payload(
        lot, source, pallet_qty="6.00", carton_qty="12.00",
        weight_lbs="600.00", cbm="3.0000",
    ))
    return lot, shipment, source, first_outbound, first


@pytest.mark.parametrize("same_outbound", [True, False], ids=["same-outbound", "different-outbound"])
def test_second_legal_fba_allocation_succeeds_with_correct_remaining(
    client, db, seed, allocated_fba, same_outbound,
):
    lot, shipment, source, first_outbound, first = allocated_fba
    target = first_outbound if same_outbound else fba_outbound(client, seed, shipment)
    accepted = post_ok(client, f"/api/v1/outbounds/{target['id']}/allocate", payload(
        lot, source, pallet_qty="1.25", carton_qty="2.50",
        weight_lbs="125.25", cbm="0.6250",
    ))

    db.expire_all()
    rows = db.scalars(select(OutboundInventoryAllocation).where(
        OutboundInventoryAllocation.fba_allocation_id == source["id"],
    ).order_by(OutboundInventoryAllocation.id)).all()
    assert len(rows) == (1 if same_outbound else 2)
    stored = db.get(OutboundInventoryAllocation, accepted["id"])
    assert (stored.outbound_order_id, stored.inventory_lot_id, stored.fba_allocation_id) == (
        target["id"], lot["id"], source["id"],
    )
    expected = ("7.25", "14.50", "725.25", "3.6250") if same_outbound else (
        "1.25", "2.50", "125.25", "0.6250",
    )
    assert tuple(getattr(stored, f"allocated_{field}") for field in QUANTITY_FIELDS) == tuple(
        Decimal(value) for value in expected
    )
    assert (accepted["id"] == first["id"]) is same_outbound
    if not same_outbound:
        original = db.get(OutboundInventoryAllocation, first["id"])
        assert tuple(getattr(original, f"allocated_{field}") for field in QUANTITY_FIELDS) == (
            Decimal("6.00"), Decimal("12.00"), Decimal("600.00"), Decimal("3.0000"),
        )
    sources = remaining(client, target)["remaining_sources"]
    assert len(sources) == 1
    assert sources[0]["fba_allocation_id"] == source["id"]
    assert sources[0]["inventory_lot_id"] == lot["id"]
    assert tuple(sources[0][f"remaining_{field}"] for field in QUANTITY_FIELDS) == (
        "2.75", "5.50", "274.75", "1.3750",
    )


@pytest.mark.parametrize("field,excess", EXCESS_QUANTITIES)
def test_excess_fba_allocation_is_rejected_independently(
    client, seed, allocated_fba, field, excess,
):
    lot, shipment, source, _, _ = allocated_fba
    target = fba_outbound(client, seed, shipment)
    response = client.post(f"/api/v1/outbounds/{target['id']}/allocate", json=payload(
        lot, source, **{field: excess},
    ))
    assert response.status_code == 409, response.text
    assert response.json() == {"detail": "Allocation exceeds remaining FBA allocation"}


@pytest.mark.parametrize("field,excess", EXCESS_QUANTITIES)
def test_rejected_fba_allocation_has_identical_database_and_zero_writes(
    client, db, seed, allocated_fba, field, excess,
):
    lot, shipment, source, _, _ = allocated_fba
    target = fba_outbound(client, seed, shipment)
    before = database_snapshot(db)
    assert set(before) == {table.name for table in Base.metadata.sorted_tables}
    assert before[OutboundInventoryAllocation.__tablename__]
    statements = []
    writes = []

    def capture_sql(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
        verb = statement.lstrip().split(None, 1)[0].upper()
        if context.isinsert or context.isupdate or context.isdelete or verb in {
            "INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP", "TRUNCATE",
        }:
            writes.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        response = client.post(f"/api/v1/outbounds/{target['id']}/allocate", json=payload(
            lot, source, **{field: excess},
        ))
    finally:
        event.remove(engine, "before_cursor_execute", capture_sql)
    after = database_snapshot(db)

    # Check all tables, including inventory, allocations, transactions and audit logs.
    assert after == before
    assert statements, "SQL recorder must observe the real request, not a mocked response"
    assert writes == [], f"Rejected request attempted database writes: {writes}"
    assert response.status_code == 409, response.text
    assert response.json() == {"detail": "Allocation exceeds remaining FBA allocation"}
