"""Cancel must preserve pending status and atomically release every allocation."""
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.models import AuditLog, FBAInventoryAllocation, InventoryLot, InventoryTransaction, OutboundInventoryAllocation, OutboundOrder
from app.models.outbound import OBStatus
from app.schemas.outbound import AllocateRequest, ReleaseRequest
from app.services import outbound as service
from test_outbound_allocation_concurrency_postgres import concurrent_sessions, fixture_state, FACTORS, DELTAS, quantities

pytestmark = pytest.mark.skipif(os.environ.get("RUN_POSTGRES_CONCURRENCY") != "1", reason="requires isolated PostgreSQL")


def snapshot(db, order_id):
    def values(row):
        return {a.key: getattr(row, a.key) for a in inspect(type(row)).column_attrs}
    allocations = list(db.scalars(select(OutboundInventoryAllocation).where(
        OutboundInventoryAllocation.outbound_order_id == order_id).order_by(OutboundInventoryAllocation.id)))
    return {
        "order": values(db.get(OutboundOrder, order_id)),
        "allocations": [values(a) for a in allocations],
        "lots": [values(db.get(InventoryLot, a.inventory_lot_id)) for a in allocations],
        "sources": [values(db.get(FBAInventoryAllocation, a.fba_allocation_id)) for a in allocations if a.fba_allocation_id],
        "audit": [values(a) for a in db.scalars(select(AuditLog).where(AuditLog.entity_type == "OUTBOUND", AuditLog.entity_id == order_id).order_by(AuditLog.id))],
        "tx": [values(t) for t in db.scalars(select(InventoryTransaction).where(InventoryTransaction.reference_type == "OUTBOUND", InventoryTransaction.reference_id == order_id).order_by(InventoryTransaction.id))],
    }


def confirmed(sessions, fba, second=False):
    state = fixture_state(sessions, fba=fba)
    order_id = state["orders"][0]
    if second:
        other = fixture_state(sessions, fba=fba, initial=0)
        with sessions.begin() as db:
            order = db.get(OutboundOrder, order_id)
            lot = db.get(InventoryLot, other["lot"])
            lot.warehouse_id, lot.customer_id = order.warehouse_id, order.customer_id
            if fba:
                db.get(FBAInventoryAllocation, other["source"]).fba_shipment_id = order.fba_shipment_id
        with sessions() as db:
            service.allocate(db, order_id, AllocateRequest(inventory_lot_id=other["lot"], fba_allocation_id=other["source"], **quantities(4)), state["user"])
    with sessions.begin() as db:
        db.get(OutboundOrder, order_id).status = OBStatus.CONFIRMED
    return state


@pytest.mark.parametrize("fba", [False, True])
def test_cancel_preserves_canceled_status_when_release_uses_fresh_locked_state(concurrent_sessions, fba):
    sessions = concurrent_sessions
    state = confirmed(sessions, fba)
    order_id = state["orders"][0]
    with sessions() as db:
        assert db.autoflush is False and db.expire_on_commit is False
        before = snapshot(db, order_id)
        service.change(db, order_id, OBStatus.CANCELED, state["user"])
    with sessions() as db:
        after = snapshot(db, order_id)
    assert after["order"]["status"] == OBStatus.CANCELED
    assert after["order"]["canceled_at"] is not None
    assert after["order"]["canceled_by"] == state["user"]
    for field, factor in FACTORS.items():
        assert after["allocations"][0]["allocated_" + field] == after["allocations"][0]["completed_" + field] == 0
        assert after["lots"][0]["available_" + field] == (0 if fba else 10 * factor)
        assert after["lots"][0]["allocated_" + field] == (10 * factor if fba else 0)
        if fba:
            assert after["sources"][0]["allocated_" + field] == 10 * factor
    assert after["sources"] == before["sources"]
    audits = after["audit"][len(before["audit"]):]
    assert [a["action"] for a in audits] == ["RELEASE_OUTBOUND_INVENTORY", "CANCEL_OUTBOUND"]
    assert audits[-1]["before_data"] == {"status": OBStatus.CONFIRMED}
    assert audits[-1]["after_data"] == {"status": OBStatus.CANCELED}
    tx = after["tx"][len(before["tx"]):]
    assert len(tx) == (0 if fba else 1)
    if not fba:
        assert tx[0]["transaction_type"].value == "OUTBOUND_RELEASE"
        for delta, factor in zip(DELTAS, FACTORS.values()):
            assert tx[0][delta] == 4 * factor


@pytest.mark.parametrize("fba", [False, True])
def test_cancel_release_failure_rolls_back_status_and_prior_releases(concurrent_sessions, monkeypatch, fba):
    sessions = concurrent_sessions
    state = confirmed(sessions, fba, second=True)
    order_id = state["orders"][0]
    with sessions() as db:
        before = snapshot(db, order_id)
    assert len(before["allocations"]) == 2
    original, released = service.release, []

    def fail_second(db, ob_id, allocation_id, payload, user_id, commit=True):
        assert commit is False
        if released:
            for field in FACTORS:
                assert getattr(db.get(OutboundInventoryAllocation, released[0]), "allocated_" + field) == 0
            pending = snapshot(db, order_id)
            assert len(pending["audit"]) == len(before["audit"]) + 1
            assert len(pending["tx"]) == len(before["tx"]) + (0 if fba else 1)
            assert pending["order"]["status"] == OBStatus.CANCELED
            raise HTTPException(409, "injected second release failure")
        result = original(db, ob_id, allocation_id, payload, user_id, commit=False)
        released.append(allocation_id)
        return result

    monkeypatch.setattr(service, "release", fail_second)
    with sessions() as db:
        with pytest.raises(HTTPException, match="injected second release failure"):
            service.change(db, order_id, OBStatus.CANCELED, state["user"])
    assert len(released) == 1
    with sessions() as db:
        assert snapshot(db, order_id) == before
        order = db.get(OutboundOrder, order_id)
        assert order.status == OBStatus.CONFIRMED
        assert order.canceled_at is None and order.canceled_by is None


@pytest.mark.parametrize("action", ["allocate", "release"])
def test_independent_writer_refreshes_clean_status_even_with_unrelated_dirty_field(concurrent_sessions, action):
    sessions = concurrent_sessions
    state = confirmed(sessions, False)
    order_id = state["orders"][0]
    with sessions() as stale:
        order = stale.get(OutboundOrder, order_id)
        order.remark = "pending caller note"
        with sessions.begin() as fresh:
            fresh.get(OutboundOrder, order_id).status = OBStatus.DISPATCHED
        with pytest.raises(HTTPException) as exc:
            if action == "release":
                service.release(stale, order_id, state["allocation"], ReleaseRequest(), state["user"])
            else:
                service.allocate(stale, order_id, AllocateRequest(inventory_lot_id=state["lot"], **quantities(1)), state["user"])
        assert exc.value.status_code == 409
        assert order.status == OBStatus.DISPATCHED
        assert order.remark == "pending caller note"
        stale.rollback()
