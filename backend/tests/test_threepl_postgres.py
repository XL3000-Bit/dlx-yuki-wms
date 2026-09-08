from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.models import BOL, Carrier, Customer, OutboundOrder, PickingList, User, Warehouse
from app.models.bol import BOLStatus
from app.models.outbound import OBStatus
from app.models.picking import PickingStatus
from app.models.user import ScopeMode, UserRole
from app.services.threepl import build_threepl_dispatch_queue
from app.utils.business_time import get_business_now


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_CONCURRENCY") != "1",
    reason="requires the isolated PostgreSQL concurrency gate",
)

BASE_REVISION = "20260904_0026"
TARGET_REVISION = "20260904_0028"
ROOT = Path(__file__).resolve().parents[1]


def _alembic(engine: Engine, revision: str, *, upgrade: bool) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        (command.upgrade if upgrade else command.downgrade)(config, revision)


def _revision(engine: Engine) -> str:
    with engine.connect() as connection:
        return connection.scalar(text("select version_num from alembic_version"))


@pytest.fixture
def threepl_pg_engine() -> Engine:
    engine = create_engine(os.environ["DATABASE_URL"], pool_size=8, max_overflow=4, pool_pre_ping=True)
    with engine.connect() as connection:
        assert connection.dialect.name == "postgresql"
        assert connection.scalar(text("select current_database()")) == "dlx_yuki_wms_test"

    current = _revision(engine)
    assert current in {BASE_REVISION, "20260904_0027", TARGET_REVISION}
    if current != BASE_REVISION:
        _alembic(engine, BASE_REVISION, upgrade=False)
    _alembic(engine, TARGET_REVISION, upgrade=True)
    assert _revision(engine) == TARGET_REVISION
    try:
        yield engine
    finally:
        _alembic(engine, BASE_REVISION, upgrade=False)
        assert _revision(engine) == BASE_REVISION
        engine.dispose()


def _table_counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            table: connection.scalar(text(f'SELECT count(*) FROM "{table}"'))
            for table in inspect(connection).get_table_names()
            if table != "alembic_version"
        }


def _seed(sessions):
    token = uuid.uuid4().hex[:10]
    now = get_business_now()
    with sessions.begin() as db:
        customer = Customer(customer_code=f"3C-{token}", customer_name="3PL Visible Client")
        other_customer = Customer(customer_code=f"3X-{token}", customer_name="3PL Hidden Client")
        warehouse = Warehouse(
            warehouse_code=f"3W-{token}", warehouse_name="3PL Visible Warehouse",
            address="1 Queue Way", city="Oakland", state="CA", zip_code="94601",
        )
        other_warehouse = Warehouse(
            warehouse_code=f"3Z-{token}", warehouse_name="3PL Hidden Warehouse",
            address="2 Queue Way", city="Oakland", state="CA", zip_code="94601",
        )
        carrier = Carrier(carrier_code=f"3R-{token}", carrier_name="Queue Carrier")
        user = User(
            username=f"threepl-{token}", display_name="3PL Scoped Viewer",
            email=f"threepl-{token}@example.test", password_hash="unused", role=UserRole.VIEWER,
            warehouse_scope_mode=ScopeMode.SELECTED, customer_scope_mode=ScopeMode.SELECTED,
        )
        user.warehouses.append(warehouse)
        user.customers.append(customer)
        db.add_all([customer, other_customer, warehouse, other_warehouse, carrier, user])
        db.flush()

        common = {
            "customer_id": customer.id, "warehouse_id": warehouse.id,
            "carrier_id": carrier.id, "loading_team": "Dispatch Team", "created_by": user.id,
        }
        ready_a = OutboundOrder(
            ob_no=f"3PL-A-{token}", reference_no=f"QUEUE-{token}-A",
            status=OBStatus.IN_PROGRESS, schedule_pickup_at=now + timedelta(days=2), **common,
        )
        ready_b = OutboundOrder(
            ob_no=f"3PL-B-{token}", reference_no=f"QUEUE-{token}-B",
            status=OBStatus.IN_PROGRESS, schedule_pickup_at=now + timedelta(days=2), **common,
        )
        missing = OutboundOrder(
            ob_no=f"3PL-M-{token}", reference_no=f"QUEUE-{token}-M",
            status=OBStatus.CONFIRMED, schedule_pickup_at=now + timedelta(days=2), **common,
        )
        blocked = OutboundOrder(
            ob_no=f"3PL-H-{token}", reference_no=f"QUEUE-{token}-H",
            status=OBStatus.HOLD, exception_reason="Awaiting release", **common,
        )
        canceled = OutboundOrder(
            ob_no=f"3PL-C-{token}", customer_id=customer.id, warehouse_id=warehouse.id,
            status=OBStatus.CANCELED, created_by=user.id,
        )
        hidden = OutboundOrder(
            ob_no=f"3PL-X-{token}", customer_id=other_customer.id, warehouse_id=other_warehouse.id,
            status=OBStatus.IN_PROGRESS, created_by=user.id,
        )
        db.add_all([ready_a, ready_b, missing, blocked, canceled, hidden])
        db.flush()
        db.add_all([
            PickingList(
                picking_no=f"PK-A-{token}", outbound_order_id=ready_a.id,
                status=PickingStatus.NEW, created_by=user.id,
            ),
            BOL(
                bol_no=f"BOL-A-{token}", outbound_order_id=ready_a.id,
                customer_id=customer.id, warehouse_id=warehouse.id, carrier_id=carrier.id,
                ship_from_name="3PL Visible Warehouse", ship_from_address="1 Queue Way",
                status=BOLStatus.GENERATED, created_by=user.id,
            ),
            PickingList(
                picking_no=f"PK-C-{token}", outbound_order_id=missing.id,
                status=PickingStatus.CANCELED, created_by=user.id,
            ),
            BOL(
                bol_no=f"BOL-C-{token}", outbound_order_id=missing.id,
                customer_id=customer.id, warehouse_id=warehouse.id,
                ship_from_name="3PL Visible Warehouse", ship_from_address="1 Queue Way",
                status=BOLStatus.CANCELED, created_by=user.id,
            ),
        ])
        db.flush()
        return user.id, token, [ready_a.id, ready_b.id, missing.id, blocked.id]


def _query(sessions, user_id: int, barrier: threading.Barrier | None = None) -> dict:
    with sessions() as db:
        if barrier is not None:
            barrier.wait(timeout=5)
        return build_threepl_dispatch_queue(
            db, db.get(User, user_id), None, None, page=1, page_size=100, sort="priority",
        )


def test_postgres_dispatch_queue_is_scoped_deterministic_and_zero_write(threepl_pg_engine: Engine) -> None:
    sessions = sessionmaker(threepl_pg_engine, expire_on_commit=False)
    user_id, token, visible_ids = _seed(sessions)
    before_counts = _table_counts(threepl_pg_engine)
    with sessions() as db:
        before_statuses = db.execute(select(OutboundOrder.id, OutboundOrder.status).order_by(OutboundOrder.id)).all()

    select_statements: list[str] = []

    def record_select(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(threepl_pg_engine, "before_cursor_execute", record_select)
    try:
        first = _query(sessions, user_id)
    finally:
        event.remove(threepl_pg_engine, "before_cursor_execute", record_select)
    assert len(select_statements) <= 8, f"dispatch queue issued {len(select_statements)} SELECTs"
    repeated = _query(sessions, user_id)
    assert first["summary_scope"] == "FILTERED_RESULT"
    assert first["total"] == first["summary"]["total"] == 4
    assert first["summary"]["ready"] == 2
    assert first["summary"]["at_risk"] == 1
    assert first["summary"]["blocked"] == 1
    assert [task["id"] for task in first["tasks"]] == visible_ids[3:] + visible_ids[:3]
    assert repeated["summary"] == first["summary"]
    assert repeated["tasks"] == first["tasks"]

    by_reference = {task["reference"]: task for task in first["tasks"]}
    ready = by_reference[f"3PL-A-{token}"]
    assert ready["document_state"] == "READY"
    assert ready["picking_download_url"].startswith("/picking-lists/")
    assert ready["bol_download_url"].startswith("/bols/")
    missing = by_reference[f"3PL-M-{token}"]
    assert missing["document_state"] == "MISSING"
    assert missing["picking_download_url"] is missing["bol_download_url"] is None
    blocked = by_reference[f"3PL-H-{token}"]
    assert blocked["action_allowed"] is False
    assert blocked["action_disabled_reason"] == "Awaiting release"
    assert all(task["action_target"].startswith("/") for task in first["tasks"])

    with sessions() as db:
        searched = build_threepl_dispatch_queue(
            db, db.get(User, user_id), None, None,
            search=f"QUEUE-{token}-A", page=1, page_size=20, sort="reference",
        )
        second_page = build_threepl_dispatch_queue(
            db, db.get(User, user_id), None, None, page=2, page_size=2, sort="priority",
        )
    assert searched["summary"]["total"] == searched["total"] == 1
    assert searched["tasks"][0]["reference"] == f"3PL-A-{token}"
    assert second_page["summary"]["total"] == 4
    assert len(second_page["tasks"]) == 2

    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_query, sessions, user_id, barrier) for _ in range(2)]
        concurrent = [future.result(timeout=15) for future in futures]
    assert concurrent[0]["summary"] == concurrent[1]["summary"] == first["summary"]
    assert concurrent[0]["tasks"] == concurrent[1]["tasks"] == first["tasks"]

    with sessions() as db:
        after_statuses = db.execute(select(OutboundOrder.id, OutboundOrder.status).order_by(OutboundOrder.id)).all()
    assert after_statuses == before_statuses
    assert _table_counts(threepl_pg_engine) == before_counts


@pytest.mark.parametrize(
    ("selected_day", "range_start", "range_end"),
    (
        (
            date(2026, 3, 8),
            datetime(2026, 3, 8, 8, 0, tzinfo=UTC),
            datetime(2026, 3, 9, 7, 0, tzinfo=UTC),
        ),
        (
            date(2026, 11, 1),
            datetime(2026, 11, 1, 7, 0, tzinfo=UTC),
            datetime(2026, 11, 2, 8, 0, tzinfo=UTC),
        ),
    ),
)
def test_postgres_dispatch_date_filter_uses_business_day_half_open_utc_range(
    threepl_pg_engine: Engine,
    selected_day: date,
    range_start: datetime,
    range_end: datetime,
) -> None:
    sessions = sessionmaker(threepl_pg_engine, expire_on_commit=False)
    user_id, token, _ = _seed(sessions)
    date_token = f"DATE{token}"
    with sessions.begin() as db:
        user = db.get(User, user_id)
        customer_id = user.customers[0].id
        warehouse_id = user.warehouses[0].id
        boundary_orders = [
            OutboundOrder(
                ob_no=f"3PL-{date_token}-{index}",
                customer_id=customer_id,
                warehouse_id=warehouse_id,
                status=OBStatus.IN_PROGRESS,
                loading_team="Dispatch Team",
                schedule_pickup_at=due_at,
                created_by=user_id,
            )
            for index, due_at in enumerate(
                (
                    range_start - timedelta(microseconds=1),
                    range_start,
                    range_end - timedelta(microseconds=1),
                    range_end,
                )
            )
        ]
        db.add_all(boundary_orders)
        db.flush()
        expected_ids = [boundary_orders[1].id, boundary_orders[2].id]

    before_counts = _table_counts(threepl_pg_engine)
    results = []
    for session_timezone in ("UTC", "America/Los_Angeles", "Asia/Tokyo"):
        with sessions.begin() as db:
            db.execute(
                text("SELECT set_config('TimeZone', :timezone, true)"),
                {"timezone": session_timezone},
            )
            result = build_threepl_dispatch_queue(
                db,
                db.get(User, user_id),
                None,
                None,
                search=date_token,
                date_from=selected_day,
                date_to=selected_day,
                page=1,
                page_size=100,
                sort="due_at",
            )
            results.append(result)

    for result in results:
        assert result["total"] == result["summary"]["total"] == 2
        assert len(result["tasks"]) == 2
        assert [task["id"] for task in result["tasks"]] == expected_ids
    assert all(result["summary"] == results[0]["summary"] for result in results)
    assert _table_counts(threepl_pg_engine) == before_counts
