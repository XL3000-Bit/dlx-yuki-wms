from __future__ import annotations

import hashlib
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException, Response
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.endpoints.outbound import inventory_batch
from app.models import (
    AuditLog,
    Customer,
    InboundRecord,
    InventoryLot,
    InventoryTransaction,
    OutboundInventoryAllocation,
    OutboundInventoryIdempotency,
    OutboundOrder,
    User,
    Warehouse,
)
from app.models.user import UserRole
from app.schemas.outbound import InventoryBatchRequest


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_CONCURRENCY") != "1",
    reason="requires the isolated PostgreSQL concurrency gate",
)

BASE_REVISION = "20260902_0026"
TARGET_REVISION = "20260904_0027"
ROOT = Path(__file__).resolve().parents[1]
ZERO = Decimal("0")


def _alembic(engine: Engine, revision: str) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision) if revision == TARGET_REVISION else command.downgrade(config, revision)


@pytest.fixture(scope="session")
def pg_engine() -> Engine:
    url = os.environ["DATABASE_URL"]
    engine = create_engine(url, pool_size=12, max_overflow=4, pool_pre_ping=True)
    with engine.connect() as connection:
        assert connection.scalar(text("select current_database()")) == "dlx_yuki_wms_test"
        assert connection.dialect.name == "postgresql"
        current_revision = connection.scalar(text("select version_num from alembic_version"))
    if current_revision == TARGET_REVISION:
        _alembic(engine, BASE_REVISION)
    with engine.connect() as connection:
        assert connection.scalar(text("select version_num from alembic_version")) == BASE_REVISION

    marker = f"mig-{uuid.uuid4().hex[:24]}"
    with engine.begin() as connection:
        connection.execute(
            text(
                "insert into audit_logs (action, entity_type, before_data, after_data) "
                "values (:marker, 'MIGRATION_GATE', CAST(:payload AS jsonb), CAST(:payload AS jsonb))"
            ),
            {"marker": marker, "payload": '{"preserved":true}'},
        )
        tables = inspect(connection).get_table_names()
        before_counts = {
            table: connection.scalar(text(f'SELECT count(*) FROM "{table}"'))
            for table in tables
            if table != "alembic_version"
        }

    _alembic(engine, TARGET_REVISION)
    inspector = inspect(engine)
    assert "outbound_inventory_idempotency" in inspector.get_table_names()
    assert any(
        constraint["name"] == "uq_outbound_inventory_idempotency_command"
        and constraint["column_names"] == ["scope", "action", "idempotency_key"]
        for constraint in inspector.get_unique_constraints("outbound_inventory_idempotency")
    )
    assert next(
        column for column in inspector.get_columns("outbound_inventory_idempotency")
        if column["name"] == "response_payload"
    )["type"].__class__.__name__ == "JSONB"

    _alembic(engine, BASE_REVISION)
    with engine.connect() as connection:
        assert connection.scalar(text("select version_num from alembic_version")) == BASE_REVISION
        assert "outbound_inventory_idempotency" not in inspect(connection).get_table_names()
        after_counts = {
            table: connection.scalar(text(f'SELECT count(*) FROM "{table}"'))
            for table in before_counts
        }
        assert after_counts == before_counts
        assert connection.scalar(
            text("select count(*) from audit_logs where action=:marker"), {"marker": marker}
        ) == 1

    _alembic(engine, TARGET_REVISION)
    with engine.connect() as connection:
        assert connection.scalar(text("select version_num from alembic_version")) == TARGET_REVISION
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def sessions(pg_engine: Engine):
    return sessionmaker(pg_engine, expire_on_commit=False)


def test_migration_upgrade_downgrade_upgrade_preserves_existing_data(pg_engine: Engine) -> None:
    assert inspect(pg_engine).has_table("outbound_inventory_idempotency")


def _seed(sessions, *, available=Decimal("10"), allocated=ZERO):
    token = uuid.uuid4().hex[:12]
    with sessions.begin() as db:
        user = User(
            username=f"pg-{token}", display_name="PG Gate", email=f"{token}@example.test",
            password_hash="unused", role=UserRole.ADMIN,
        )
        customer = Customer(customer_code=f"C-{token}", customer_name="PG Customer")
        warehouse = Warehouse(
            warehouse_code=f"W-{token}", warehouse_name="PG Warehouse",
            address="1 Test Way", city="Test", state="CA", zip_code="90001",
        )
        db.add_all([user, customer, warehouse]); db.flush()
        inbound = InboundRecord(
            inbound_no=f"IB{token}", container_number=f"CONT-{token}",
            customer_id=customer.id, warehouse_id=warehouse.id,
            pallet_qty=available + allocated, carton_qty=ZERO, created_by=user.id,
        )
        db.add(inbound); db.flush()
        lot = InventoryLot(
            lot_no=f"LOT{token}", customer_id=customer.id, warehouse_id=warehouse.id,
            source_inbound_id=inbound.id, container_number=inbound.container_number,
            original_pallet_qty=available + allocated, original_carton_qty=ZERO,
            original_weight_lbs=ZERO, original_cbm=ZERO,
            available_pallet_qty=available, available_carton_qty=ZERO,
            available_weight_lbs=ZERO, available_cbm=ZERO,
            allocated_pallet_qty=allocated, allocated_carton_qty=ZERO,
            allocated_weight_lbs=ZERO, allocated_cbm=ZERO,
            hold_pallet_qty=ZERO, hold_carton_qty=ZERO, created_by=user.id,
        )
        outbound = OutboundOrder(
            ob_no=f"OB{token}", customer_id=customer.id, warehouse_id=warehouse.id,
            ob_type="STANDARD", created_by=user.id,
        )
        db.add_all([lot, outbound]); db.flush()
        return user.id, warehouse.id, outbound.id, lot.id


def _allocate_payload(lot_id: int, quantity: str) -> InventoryBatchRequest:
    return InventoryBatchRequest.model_validate({
        "action": "allocate",
        "items": [{"id": lot_id, "data": {"inventory_lot_id": lot_id, "pallet_qty": quantity}}],
    })


def _call(sessions, user_id: int, outbound_id: int, payload: InventoryBatchRequest, key: str, barrier=None):
    with sessions() as db:
        user = db.get(User, user_id)
        pid = db.scalar(text("select pg_backend_pid()"))
        db.execute(text("set local lock_timeout='5s'"))
        if barrier:
            barrier.wait(timeout=5)
        response = Response()
        result = inventory_batch(outbound_id, payload, response, db, user, key)
        return pid, response.headers["Idempotency-Replayed"], result


def _concurrent(sessions, user_id, outbound_id, payload, key):
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_call, sessions, user_id, outbound_id, payload, key, barrier) for _ in range(2)]
        return [future.result(timeout=15) for future in futures]


def _counts(db: Session, outbound_id: int):
    scope_suffix = f":outbound:{outbound_id}"
    return {
        "receipts": db.scalar(select(text("count(*)")).select_from(OutboundInventoryIdempotency).where(OutboundInventoryIdempotency.scope.endswith(scope_suffix))),
        "transactions": db.scalar(select(text("count(*)")).select_from(InventoryTransaction).where(InventoryTransaction.reference_type == "OUTBOUND", InventoryTransaction.reference_id == outbound_id)),
        "audits": db.scalar(select(text("count(*)")).select_from(AuditLog).where(AuditLog.entity_type == "OUTBOUND", AuditLog.entity_id == outbound_id)),
        "allocations": db.scalar(select(text("count(*)")).select_from(OutboundInventoryAllocation).where(OutboundInventoryAllocation.outbound_order_id == outbound_id)),
    }


def test_same_key_allocate_is_exactly_once_and_lock_is_released(sessions) -> None:
    user_id, _, outbound_id, lot_id = _seed(sessions)
    payload = _allocate_payload(lot_id, "3")
    results = _concurrent(sessions, user_id, outbound_id, payload, "allocate-same-key")
    assert len({row[0] for row in results}) == 2
    assert sorted(row[1] for row in results) == ["false", "true"]
    assert results[0][2] == results[1][2]
    replay = _call(sessions, user_id, outbound_id, payload, "allocate-same-key")
    assert replay[1] == "true"
    with sessions() as db:
        lot = db.get(InventoryLot, lot_id)
        assert (lot.available_pallet_qty, lot.allocated_pallet_qty) == (Decimal("7"), Decimal("3"))
        assert _counts(db, outbound_id) == {"receipts": 1, "transactions": 1, "audits": 1, "allocations": 1}
        scope = f"warehouse:{lot.warehouse_id}:outbound:{outbound_id}"
        digest = hashlib.sha256(f"{scope}\0allocate\0allocate-same-key".encode()).digest()
        lock_id = int.from_bytes(digest[:8], byteorder="big", signed=True)
        assert db.scalar(text("select pg_try_advisory_xact_lock(:id)"), {"id": lock_id}) is True


def test_same_key_release_is_exactly_once(sessions) -> None:
    user_id, _, outbound_id, lot_id = _seed(sessions, available=Decimal("7"), allocated=Decimal("3"))
    with sessions.begin() as db:
        allocation = OutboundInventoryAllocation(
            outbound_order_id=outbound_id, inventory_lot_id=lot_id,
            allocated_pallet_qty=Decimal("3"), allocated_carton_qty=ZERO,
            allocated_weight_lbs=ZERO, allocated_cbm=ZERO,
            completed_pallet_qty=ZERO, completed_carton_qty=ZERO,
            completed_weight_lbs=ZERO, completed_cbm=ZERO, created_by=user_id,
        )
        db.add(allocation); db.flush(); allocation_id = allocation.id
    payload = InventoryBatchRequest.model_validate({
        "action": "release", "items": [{"id": allocation_id, "data": {"pallet_qty": "3"}}],
    })
    results = _concurrent(sessions, user_id, outbound_id, payload, "release-same-key")
    assert sorted(row[1] for row in results) == ["false", "true"]
    with sessions() as db:
        lot = db.get(InventoryLot, lot_id)
        assert (lot.available_pallet_qty, lot.allocated_pallet_qty) == (Decimal("10"), ZERO)
        assert _counts(db, outbound_id) == {"receipts": 1, "transactions": 1, "audits": 1, "allocations": 1}


def test_key_conflict_is_409_without_mutation(sessions) -> None:
    user_id, _, outbound_id, lot_id = _seed(sessions)
    _call(sessions, user_id, outbound_id, _allocate_payload(lot_id, "3"), "conflict-key")
    with pytest.raises(HTTPException) as caught:
        _call(sessions, user_id, outbound_id, _allocate_payload(lot_id, "4"), "conflict-key")
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "OUTBOUND_IDEMPOTENCY_CONFLICT"
    with sessions() as db:
        lot = db.get(InventoryLot, lot_id)
        assert (lot.available_pallet_qty, lot.allocated_pallet_qty) == (Decimal("7"), Decimal("3"))
        assert _counts(db, outbound_id) == {"receipts": 1, "transactions": 1, "audits": 1, "allocations": 1}


def test_different_keys_both_execute(sessions) -> None:
    user_id, _, outbound_id, lot_id = _seed(sessions)
    payload = _allocate_payload(lot_id, "1")
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_call, sessions, user_id, outbound_id, payload, key, barrier)
            for key in ("different-key-a", "different-key-b")
        ]
        results = [future.result(timeout=15) for future in futures]
    assert all(row[1] == "false" for row in results)
    with sessions() as db:
        lot = db.get(InventoryLot, lot_id)
        allocation = db.scalar(select(OutboundInventoryAllocation).where(OutboundInventoryAllocation.outbound_order_id == outbound_id))
        assert (lot.available_pallet_qty, lot.allocated_pallet_qty, allocation.allocated_pallet_qty) == (Decimal("8"), Decimal("2"), Decimal("2"))
        assert _counts(db, outbound_id) == {"receipts": 2, "transactions": 2, "audits": 2, "allocations": 1}


def test_failed_batch_rolls_back_and_same_key_can_retry(sessions) -> None:
    user_id, warehouse_id, outbound_id, first_lot_id = _seed(sessions)
    with sessions.begin() as db:
        customer_id = db.get(OutboundOrder, outbound_id).customer_id
        token = uuid.uuid4().hex[:12]
        inbound = InboundRecord(
            inbound_no=f"IB{token}", container_number=f"CONT-{token}", customer_id=customer_id,
            warehouse_id=warehouse_id, pallet_qty=Decimal("10"), carton_qty=ZERO, created_by=user_id,
        )
        db.add(inbound); db.flush()
        second = InventoryLot(
            lot_no=f"LOT{token}", customer_id=customer_id, warehouse_id=warehouse_id,
            source_inbound_id=inbound.id, container_number=inbound.container_number,
            original_pallet_qty=Decimal("10"), original_carton_qty=ZERO,
            original_weight_lbs=ZERO, original_cbm=ZERO,
            available_pallet_qty=Decimal("1"), available_carton_qty=ZERO,
            available_weight_lbs=ZERO, available_cbm=ZERO,
            allocated_pallet_qty=ZERO, allocated_carton_qty=ZERO,
            allocated_weight_lbs=ZERO, allocated_cbm=ZERO,
            hold_pallet_qty=ZERO, hold_carton_qty=ZERO, created_by=user_id,
        )
        db.add(second); db.flush(); second_lot_id = second.id
    payload = InventoryBatchRequest.model_validate({"action": "allocate", "items": [
        {"id": first_lot_id, "data": {"inventory_lot_id": first_lot_id, "pallet_qty": "3"}},
        {"id": second_lot_id, "data": {"inventory_lot_id": second_lot_id, "pallet_qty": "9"}},
    ]})
    with pytest.raises(HTTPException) as caught:
        _call(sessions, user_id, outbound_id, payload, "retry-after-rollback")
    assert caught.value.status_code == 409
    with sessions() as db:
        assert db.get(InventoryLot, first_lot_id).available_pallet_qty == Decimal("10")
        assert db.get(InventoryLot, second_lot_id).available_pallet_qty == Decimal("1")
        assert _counts(db, outbound_id) == {"receipts": 0, "transactions": 0, "audits": 0, "allocations": 0}
    with sessions.begin() as db:
        db.get(InventoryLot, second_lot_id).available_pallet_qty = Decimal("9")
    result = _call(sessions, user_id, outbound_id, payload, "retry-after-rollback")
    assert result[1] == "false"
    with sessions() as db:
        assert db.get(InventoryLot, first_lot_id).available_pallet_qty == Decimal("7")
        assert db.get(InventoryLot, second_lot_id).available_pallet_qty == ZERO
        assert _counts(db, outbound_id) == {"receipts": 1, "transactions": 2, "audits": 2, "allocations": 2}
        assert db.scalar(select(text("count(*)")).select_from(OutboundInventoryIdempotency).where(OutboundInventoryIdempotency.status == "PENDING")) == 0
