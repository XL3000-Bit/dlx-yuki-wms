from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AuditLog,
    BOL,
    Customer,
    InboundRecord,
    InventoryLot,
    OutboundInventoryAllocation,
    OutboundOrder,
    PickingList,
    User,
    Warehouse,
)
from app.models.bol import BOLStatus
from app.models.outbound import OBStatus
from app.models.picking import PickingStatus
from app.models.user import UserRole
from app.services.outbound import change
from app.services.picking_bol import ensure_outbound_documents


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_CONCURRENCY") != "1",
    reason="requires the isolated PostgreSQL concurrency gate",
)

BASE_REVISION = "20260904_0027"
TARGET_REVISION = "20260904_0028"
ROOT = Path(__file__).resolve().parents[1]
ZERO = Decimal("0")


def _alembic(engine: Engine, revision: str, *, upgrade: bool) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        (command.upgrade if upgrade else command.downgrade)(config, revision)


def _revision(engine: Engine) -> str:
    with engine.connect() as connection:
        return connection.scalar(text("select version_num from alembic_version"))


def _index_definitions(engine: Engine) -> dict[str, str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "select indexname, indexdef from pg_indexes "
                "where schemaname=current_schema() and indexname in "
                "('uq_picking_lists_active_outbound', 'uq_bols_active_outbound')"
            )
        ).all()
    return dict(rows)


@pytest.fixture(scope="session")
def picking_pg_engine() -> Engine:
    engine = create_engine(os.environ["DATABASE_URL"], pool_size=12, max_overflow=4, pool_pre_ping=True)
    with engine.connect() as connection:
        assert connection.dialect.name == "postgresql"
        assert connection.scalar(text("select current_database()")) == "dlx_yuki_wms_test"

    current = _revision(engine)
    assert current in {BASE_REVISION, TARGET_REVISION}
    if current == TARGET_REVISION:
        _alembic(engine, BASE_REVISION, upgrade=False)
    assert _revision(engine) == BASE_REVISION

    marker = f"picking-bol-mig-{uuid.uuid4().hex[:12]}"
    with engine.begin() as connection:
        connection.execute(
            text(
                "insert into audit_logs (action, entity_type, before_data, after_data) "
                "values (:marker, 'MIGRATION_GATE', CAST(:payload AS jsonb), CAST(:payload AS jsonb))"
            ),
            {"marker": marker, "payload": '{"preserved":true}'},
        )
        before_counts = {
            table: connection.scalar(text(f'SELECT count(*) FROM "{table}"'))
            for table in inspect(connection).get_table_names()
            if table != "alembic_version"
        }

    _alembic(engine, TARGET_REVISION, upgrade=True)
    definitions = _index_definitions(engine)
    assert set(definitions) == {"uq_picking_lists_active_outbound", "uq_bols_active_outbound"}
    assert all("UNIQUE INDEX" in definition and "WHERE (status <> 4)" in definition for definition in definitions.values())

    _alembic(engine, BASE_REVISION, upgrade=False)
    assert _revision(engine) == BASE_REVISION
    assert _index_definitions(engine) == {}
    with engine.connect() as connection:
        assert {
            table: connection.scalar(text(f'SELECT count(*) FROM "{table}"'))
            for table in before_counts
        } == before_counts
        assert connection.scalar(text("select count(*) from audit_logs where action=:marker"), {"marker": marker}) == 1

    _alembic(engine, TARGET_REVISION, upgrade=True)
    assert _revision(engine) == TARGET_REVISION
    assert set(_index_definitions(engine)) == {"uq_picking_lists_active_outbound", "uq_bols_active_outbound"}
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def picking_sessions(picking_pg_engine: Engine):
    return sessionmaker(picking_pg_engine, expire_on_commit=False)


def test_migration_upgrade_downgrade_upgrade_preserves_existing_data(picking_pg_engine: Engine) -> None:
    assert _revision(picking_pg_engine) == TARGET_REVISION


def _seed(sessions):
    token = uuid.uuid4().hex[:12]
    with sessions.begin() as db:
        user = User(
            username=f"pb-{token}",
            display_name="Picking BOL Gate",
            email=f"{token}@example.test",
            password_hash="unused",
            role=UserRole.ADMIN,
        )
        customer = Customer(customer_code=f"C-{token}", customer_name="PG Customer")
        warehouse = Warehouse(
            warehouse_code=f"W-{token}",
            warehouse_name="PG Warehouse",
            address="1 Test Way",
            city="Test",
            state="CA",
            zip_code="90001",
        )
        db.add_all([user, customer, warehouse])
        db.flush()
        inbound = InboundRecord(
            inbound_no=f"IB{token}",
            container_number=f"CONT-{token}",
            customer_id=customer.id,
            warehouse_id=warehouse.id,
            pallet_qty=Decimal("10"),
            carton_qty=ZERO,
            created_by=user.id,
        )
        db.add(inbound)
        db.flush()
        lot = InventoryLot(
            lot_no=f"LOT{token}",
            customer_id=customer.id,
            warehouse_id=warehouse.id,
            source_inbound_id=inbound.id,
            container_number=inbound.container_number,
            original_pallet_qty=Decimal("10"),
            original_carton_qty=ZERO,
            original_weight_lbs=ZERO,
            original_cbm=ZERO,
            available_pallet_qty=Decimal("7"),
            available_carton_qty=ZERO,
            available_weight_lbs=ZERO,
            available_cbm=ZERO,
            allocated_pallet_qty=Decimal("3"),
            allocated_carton_qty=ZERO,
            allocated_weight_lbs=ZERO,
            allocated_cbm=ZERO,
            hold_pallet_qty=ZERO,
            hold_carton_qty=ZERO,
            created_by=user.id,
        )
        outbound = OutboundOrder(
            ob_no=f"OB{token}",
            customer_id=customer.id,
            warehouse_id=warehouse.id,
            ob_type="STANDARD",
            created_by=user.id,
        )
        db.add_all([lot, outbound])
        db.flush()
        db.add(
            OutboundInventoryAllocation(
                outbound_order_id=outbound.id,
                inventory_lot_id=lot.id,
                allocated_pallet_qty=Decimal("3"),
                allocated_carton_qty=ZERO,
                allocated_weight_lbs=ZERO,
                allocated_cbm=ZERO,
                completed_pallet_qty=ZERO,
                completed_carton_qty=ZERO,
                completed_weight_lbs=ZERO,
                completed_cbm=ZERO,
                created_by=user.id,
            )
        )
        db.flush()
        return user.id, outbound.id


def _ensure_call(sessions, user_id: int, outbound_id: int, barrier: threading.Barrier):
    with sessions() as db:
        pid = db.scalar(text("select pg_backend_pid()"))
        db.execute(text("set local lock_timeout='5s'"))
        barrier.wait(timeout=5)
        documents = ensure_outbound_documents(db, outbound_id, user_id)
        result = (
            pid,
            documents.picking.id,
            documents.bol.id,
            documents.picking_list_created,
            documents.bol_created,
        )
        db.commit()
        return result


def _confirm_call(sessions, user_id: int, outbound_id: int, barrier: threading.Barrier):
    with sessions() as db:
        pid = db.scalar(text("select pg_backend_pid()"))
        db.execute(text("set local lock_timeout='5s'"))
        barrier.wait(timeout=5)
        change(db, outbound_id, OBStatus.CONFIRMED, user_id)
        picking_id = db.scalar(
            select(PickingList.id).where(
                PickingList.outbound_order_id == outbound_id,
                PickingList.status != PickingStatus.CANCELED,
            )
        )
        bol_id = db.scalar(
            select(BOL.id).where(BOL.outbound_order_id == outbound_id, BOL.status != BOLStatus.CANCELED)
        )
        return pid, picking_id, bol_id


def _state(db: Session, outbound_id: int) -> dict[str, object]:
    active_picking = list(
        db.scalars(
            select(PickingList).where(
                PickingList.outbound_order_id == outbound_id,
                PickingList.status != PickingStatus.CANCELED,
            )
        )
    )
    active_bol = list(
        db.scalars(select(BOL).where(BOL.outbound_order_id == outbound_id, BOL.status != BOLStatus.CANCELED))
    )
    return {
        "picking": active_picking,
        "bol": active_bol,
        "picking_audits": db.scalar(
            select(text("count(*)")).select_from(AuditLog).where(
                AuditLog.action == "CREATE_PICKING_LIST",
                AuditLog.entity_id.in_([item.id for item in active_picking]),
            )
        ),
        "bol_audits": db.scalar(
            select(text("count(*)")).select_from(AuditLog).where(
                AuditLog.action == "CREATE_BOL",
                AuditLog.entity_id.in_([item.id for item in active_bol]),
            )
        ),
    }


def _assert_no_duplicate_numbers(db: Session) -> None:
    assert db.execute(text("select picking_no from picking_lists group by picking_no having count(*) > 1")).all() == []
    assert db.execute(text("select bol_no from bols group by bol_no having count(*) > 1")).all() == []


def test_concurrent_ensure_creates_exactly_one_active_pair(picking_sessions) -> None:
    user_id, outbound_id = _seed(picking_sessions)
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_ensure_call, picking_sessions, user_id, outbound_id, barrier)
            for _ in range(2)
        ]
        results = [future.result(timeout=15) for future in futures]
    assert len({row[0] for row in results}) == 2
    assert len({row[1] for row in results}) == 1
    assert len({row[2] for row in results}) == 1
    assert sorted((row[3], row[4]) for row in results) == [(False, False), (True, True)]
    with picking_sessions() as db:
        state = _state(db, outbound_id)
        assert len(state["picking"]) == len(state["bol"]) == 1
        assert state["picking_audits"] == state["bol_audits"] == 1
        _assert_no_duplicate_numbers(db)


def test_concurrent_confirm_and_ensure_are_atomic_and_idempotent(picking_sessions) -> None:
    user_id, outbound_id = _seed(picking_sessions)
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        confirm = executor.submit(_confirm_call, picking_sessions, user_id, outbound_id, barrier)
        ensure = executor.submit(_ensure_call, picking_sessions, user_id, outbound_id, barrier)
        confirm_result = confirm.result(timeout=15)
        ensure_result = ensure.result(timeout=15)
    assert confirm_result[0] != ensure_result[0]
    assert confirm_result[1:3] == ensure_result[1:3]
    with picking_sessions() as db:
        state = _state(db, outbound_id)
        assert db.get(OutboundOrder, outbound_id).status == OBStatus.CONFIRMED
        assert len(state["picking"]) == len(state["bol"]) == 1
        assert state["picking_audits"] == state["bol_audits"] == 1
        assert db.scalar(
            select(text("count(*)")).select_from(AuditLog).where(
                AuditLog.action == "CHANGE_OUTBOUND_STATUS",
                AuditLog.entity_type == "OUTBOUND",
                AuditLog.entity_id == outbound_id,
            )
        ) == 1
        _assert_no_duplicate_numbers(db)
