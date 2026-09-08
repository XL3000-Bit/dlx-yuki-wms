"""Real row-lock regressions; opt in only against the disposable PostgreSQL DB."""
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.endpoints import outbound as endpoint
from app.models import (
    AuditLog, FBAInventoryAllocation, FBAShipment, InventoryLot,
    InventoryTransaction, OutboundInventoryAllocation, OutboundInventoryIdempotency,
    OutboundOrder, User,
)
from app.schemas.outbound import AllocateRequest, InventoryBatchRequest
from app.services import outbound as service
from test_outbound_postgres import _seed

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_CONCURRENCY") != "1",
    reason="requires the isolated PostgreSQL concurrency gate",
)
FACTORS = dict(pallet_qty=Decimal(1), carton_qty=Decimal(2),
               weight_lbs=Decimal(100), cbm=Decimal("0.5"))
DELTAS = ("pallet_delta", "carton_delta", "weight_delta", "cbm_delta")


@pytest.fixture(scope="module")
def concurrent_sessions():
    engine = create_engine(os.environ["DATABASE_URL"], pool_size=6, max_overflow=0)
    with engine.connect() as db:
        assert db.dialect.name == "postgresql"
        assert db.scalar(text("select current_database()")) == "dlx_yuki_wms_test"
    yield sessionmaker(engine, autoflush=False, expire_on_commit=False, autocommit=False, future=True)
    engine.dispose()


def quantities(n):
    return {field: factor * n for field, factor in FACTORS.items()}


def fixture_state(sessions, *, fba=False, initial=4, shared=False, full=False):
    user, warehouse, order, lot = _seed(sessions)
    source = None
    orders = [order, order]
    with sessions.begin() as db:
        inventory = db.get(InventoryLot, lot)
        ob = db.get(OutboundOrder, order)
        for field, value in quantities(10).items():
            setattr(inventory, "original_" + field, value)
            setattr(inventory, "available_" + field, 0 if fba else value)
            setattr(inventory, "allocated_" + field, value if fba else 0)
        if fba:
            shipment = FBAShipment(fba_no="FC" + uuid.uuid4().hex[:18],
                customer_id=ob.customer_id, warehouse_id=warehouse,
                amazon_fc_code="TEST", created_by=user)
            db.add(shipment); db.flush()
            allocation = FBAInventoryAllocation(fba_shipment_id=shipment.id,
                inventory_lot_id=lot, created_by=user,
                **{"allocated_" + k: v for k, v in quantities(10).items()})
            db.add(allocation); db.flush()
            source = allocation.id
            ob.ob_type = "FBA"
            ob.fba_shipment_id = shipment.id
        if shared:
            other = OutboundOrder(ob_no="OC" + uuid.uuid4().hex[:18],
                customer_id=ob.customer_id, warehouse_id=warehouse,
                ob_type=ob.ob_type, fba_shipment_id=ob.fba_shipment_id, created_by=user)
            db.add(other); db.flush()
            orders[1] = other.id
    allocation_id = None
    for index, amount in ((0, initial), (1, 6 if full else 0)):
        if amount:
            with sessions() as db:
                a = service.allocate(db, orders[index], AllocateRequest(
                    inventory_lot_id=lot, fba_allocation_id=source, **quantities(amount)), user)
                if index == 0:
                    allocation_id = a.id
    return dict(user=user, lot=lot, orders=orders, source=source,
                allocation=allocation_id, initial=initial + (6 if full else 0))


def race(sessions, monkeypatch, state, actions):
    """Preload both identity maps, then prove B is blocked by A before A writes."""
    barrier, locked = threading.Barrier(2), threading.Event()
    pids, observed, outcomes = {}, [], []
    original = {name: getattr(endpoint, name) for name in ("allocate", "release")}

    def wrap(action):
        def invoke(db, *args, **kwargs):
            worker = db.info["worker"]
            # Retain strong references, including other orders' source usage.
            stale = list(db.scalars(select(OutboundInventoryAllocation).where(
                OutboundInventoryAllocation.inventory_lot_id == state["lot"])))
            stale += [db.get(InventoryLot, state["lot"])]
            if state["source"]:
                stale += [db.get(FBAInventoryAllocation, state["source"])]
            barrier.wait(timeout=10)
            if worker == 0:
                service.get_ob(db, args[0], True)
                db.scalar(select(InventoryLot).where(InventoryLot.id == state["lot"]).with_for_update())
                locked.set()
                deadline = time.monotonic() + 10
                with sessions.kw["bind"].connect() as observer:
                    while time.monotonic() < deadline:
                        blockers = observer.scalar(text("select pg_blocking_pids(:pid)"), {"pid": pids[1]})
                        if pids[0] in blockers:
                            observed.append((pids[0], pids[1]))
                            break
                    else:
                        pytest.fail("the second connection never waited on the first")
            else:
                assert locked.wait(timeout=10)
            result = original[action](db, *args, **kwargs)
            assert stale  # Keep preloaded entities alive through the write.
            return result
        return invoke

    for action in original:
        monkeypatch.setattr(endpoint, action, wrap(action))

    def worker(index):
        action, amount = actions[index]
        with sessions() as db:
            db.info["worker"] = index
            user = db.get(User, state["user"])
            pids[index] = db.scalar(text("select pg_backend_pid()"))
            db.execute(text("set local lock_timeout='12s'"))
            db.execute(text("set local statement_timeout='15s'"))
            data = quantities(amount)
            item = state["lot"] if action == "allocate" else state["allocation"]
            if action == "allocate":
                data.update(inventory_lot_id=state["lot"], fba_allocation_id=state["source"])
            else:
                data["allocation_id"] = state["allocation"]
            # A release always acts on the original allocation, including shared-source tests.
            ob = state["orders"][1 if actions[0][0] != actions[1][0] else index] if action == "allocate" else state["orders"][0]
            try:
                response = Response()
                endpoint.inventory_batch(ob, InventoryBatchRequest.model_validate({
                    "action": action, "items": [{"id": item, "data": data}]}),
                    response, db, user, "cross-" + uuid.uuid4().hex)
                assert response.headers["Idempotency-Replayed"] == "false"
                return 200
            except HTTPException as exc:
                # Do not accept a swallowed DB error (including deadlock) as business rejection.
                assert "exceeds" in str(exc.detail).lower(), exc.detail
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, index) for index in range(2)]
        outcomes = [future.result(timeout=25) for future in futures]
    assert len(set(pids.values())) == 2
    assert observed == [(pids[0], pids[1])]
    return outcomes


def effects(sessions, state):
    with sessions() as db:
        ids = state["orders"]
        tx = list(db.scalars(select(InventoryTransaction).where(
            InventoryTransaction.reference_type == "OUTBOUND",
            InventoryTransaction.reference_id.in_(ids)).order_by(InventoryTransaction.id)))
        audits = list(db.scalars(select(AuditLog).where(AuditLog.entity_type == "OUTBOUND",
            AuditLog.entity_id.in_(ids)).order_by(AuditLog.id)))
        receipts = list(db.scalars(select(OutboundInventoryIdempotency).where(
            OutboundInventoryIdempotency.scope.in_([
                f"warehouse:{db.get(OutboundOrder, ob).warehouse_id}:outbound:{ob}" for ob in set(ids)]))))
        return tx, audits, receipts


def verify(sessions, state, actions, statuses, before):
    successful = [(action, n) for (action, n), status in zip(actions, statuses) if status == 200]
    final = state["initial"] + sum(n if action == "allocate" else -n for action, n in successful)
    with sessions() as db:
        rows = list(db.scalars(select(OutboundInventoryAllocation).where(
            OutboundInventoryAllocation.inventory_lot_id == state["lot"])))
        lot = db.get(InventoryLot, state["lot"])
        for field, factor in FACTORS.items():
            total = 0
            for row in rows:
                allocated, completed = getattr(row, "allocated_" + field), getattr(row, "completed_" + field)
                assert allocated >= completed >= 0
                total += allocated - completed
            assert total == final * factor
            available, allocated = getattr(lot, "available_" + field), getattr(lot, "allocated_" + field)
            assert available >= 0 and allocated >= 0
            assert available + allocated == 10 * factor
            if state["source"]:
                assert total <= getattr(db.get(FBAInventoryAllocation, state["source"]), "allocated_" + field)
                assert available == 0 and allocated == 10 * factor
            else:
                assert allocated == total
    tx, audits, receipts = effects(sessions, state)
    tx, audits, receipts = tx[len(before[0]):], audits[len(before[1]):], receipts[len(before[2]):]
    assert len(audits) == len(receipts) == len(successful)
    assert sorted(a.action for a in audits) == sorted(
        "ALLOCATE_OUTBOUND_INVENTORY" if a == "allocate" else "RELEASE_OUTBOUND_INVENTORY" for a, _ in successful)
    assert all(r.status == "COMPLETED" and r.response_status == 200 for r in receipts)
    # FBA outbound assignment reuses the physical FBA reservation: no second lot ledger entry.
    assert len(tx) == (0 if state["source"] else len(successful))
    if not state["source"]:
        for transaction, (action, n) in zip(tx, successful):
            assert transaction.reference_id in state["orders"]
            assert transaction.inventory_lot_id == state["lot"]
            assert transaction.transaction_type.value == "OUTBOUND_" + action.upper()
            for delta, factor in zip(DELTAS, FACTORS.values()):
                assert getattr(transaction, delta) == (n if action == "release" else -n) * factor


def run_case(sessions, monkeypatch, actions, expected, **kwargs):
    state = fixture_state(sessions, **kwargs)
    before = effects(sessions, state)
    statuses = race(sessions, monkeypatch, state, actions)
    assert statuses == expected
    verify(sessions, state, actions, statuses, before)


@pytest.mark.parametrize("fba", [False, True])
def test_concurrent_release_then_allocate_uses_fresh_allocation_state(concurrent_sessions, monkeypatch, fba):
    run_case(concurrent_sessions, monkeypatch, [("release", 3), ("allocate", 1)], [200, 200], fba=fba)


@pytest.mark.parametrize("fba", [False, True])
def test_concurrent_allocate_then_release_uses_fresh_allocation_state(concurrent_sessions, monkeypatch, fba):
    run_case(concurrent_sessions, monkeypatch, [("allocate", 1), ("release", 3)], [200, 200], fba=fba)


@pytest.mark.parametrize("fba", [False, True])
def test_concurrent_release_same_allocation_one_effect(concurrent_sessions, monkeypatch, fba):
    run_case(concurrent_sessions, monkeypatch, [("release", 3), ("release", 3)], [200, 409], fba=fba)


@pytest.mark.parametrize("fba", [False, True])
@pytest.mark.parametrize("shared", [False, True])
def test_concurrent_allocate_same_source_no_overallocation(concurrent_sessions, monkeypatch, fba, shared):
    run_case(concurrent_sessions, monkeypatch, [("allocate", 7), ("allocate", 7)], [200, 409],
             fba=fba, shared=shared, initial=0)


@pytest.mark.parametrize("release_first", [False, True])
def test_concurrent_fba_allocate_release_preserves_source_limit(concurrent_sessions, monkeypatch, release_first):
    # Source initially fully assigned across two orders; a waiting allocator must see the release.
    actions = [("release", 3), ("allocate", 1)] if release_first else [("allocate", 1), ("release", 3)]
    run_case(concurrent_sessions, monkeypatch, actions, [200, 200] if release_first else [409, 200],
             fba=True, shared=True, full=True)
