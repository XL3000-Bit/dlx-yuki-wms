"""PostgreSQL-only gates for inbound receive/cancel serialization.

These tests intentionally require an explicit disposable database URL.  The URL
must not use the repository's protected port 5432 database.
"""

from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Customer,
    InboundRecord,
    InventoryLot,
    InventoryTransaction,
    User,
    Warehouse,
)
from app.models.user import UserRole
from app.schemas.inbound import InboundCreate
from app.services.inbound import create_inbound
from app.services.inventory import cancel_inbound, receive_inbound_lines


POSTGRES_URL = os.getenv("INBOUND_POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="INBOUND_POSTGRES_TEST_URL is required for PostgreSQL concurrency gates",
)


@pytest.fixture(autouse=True)
def database():
    """Override the SQLite autouse fixture from the shared conftest."""
    yield


@pytest.fixture(scope="module")
def pg_sessions():
    parsed = urlparse(POSTGRES_URL or "")
    assert parsed.scheme.startswith("postgresql")
    assert parsed.port != 5432, "Concurrency gates must use a disposable non-5432 database"
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    with engine.connect() as connection:
        assert connection.scalar(text("select version()")).startswith("PostgreSQL")
        assert connection.scalar(text("select version_num from alembic_version")) == "20260908_0029"
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _new_inbound(sessions, *, line_count: int = 2) -> tuple[int, int]:
    suffix = uuid4().hex[:10]
    with sessions() as db:
        user = User(
            username=f"pg-inbound-{suffix}",
            display_name="PostgreSQL Inbound Gate",
            email=f"pg-inbound-{suffix}@test.local",
            password_hash="not-used",
            role=UserRole.ADMIN,
        )
        customer = Customer(
            customer_code=f"C{suffix}", customer_name=f"Customer {suffix}"
        )
        warehouse = Warehouse(
            warehouse_code=f"W{suffix}",
            warehouse_name=f"Warehouse {suffix}",
            address="1 Concurrency Way",
            city="Ontario",
            state="CA",
            zip_code="91761",
        )
        db.add_all([user, customer, warehouse])
        db.flush()
        inbound = create_inbound(
            db,
            InboundCreate.model_validate(
                {
                    "container_number": f"PG-{suffix}",
                    "customer_id": customer.id,
                    "warehouse_id": warehouse.id,
                    "lines": [
                        {
                            "line_no": number,
                            "fc_code": f"FC{number}",
                            "pallet_qty": number,
                            "carton_qty": number * 10,
                        }
                        for number in range(1, line_count + 1)
                    ],
                }
            ),
            user.id,
        )
        return inbound.id, user.id


def _race(barrier: Barrier, sessions, operation):
    with sessions() as db:
        barrier.wait(timeout=10)
        try:
            operation(db)
            return 200
        except HTTPException as exc:
            db.rollback()
            return exc.status_code


def test_concurrent_receive_creates_each_line_once(pg_sessions):
    inbound_id, user_id = _new_inbound(pg_sessions)
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: _race(
                    barrier,
                    pg_sessions,
                    lambda db: receive_inbound_lines(db, inbound_id, user_id),
                ),
                range(2),
            )
        )

    assert sorted(results) == [200, 409]
    with pg_sessions() as db:
        assert db.get(InboundRecord, inbound_id).status == 2
        assert db.scalar(
            select(func.count(InventoryLot.id)).where(
                InventoryLot.source_inbound_id == inbound_id
            )
        ) == 2
        assert db.scalar(
            select(func.count(InventoryTransaction.id)).where(
                InventoryTransaction.reference_type == "INBOUND",
                InventoryTransaction.reference_id == inbound_id,
            )
        ) == 2


def test_concurrent_receive_and_cancel_preserve_terminal_invariant(pg_sessions):
    inbound_id, user_id = _new_inbound(pg_sessions)
    barrier = Barrier(2)
    operations = (
        lambda db: receive_inbound_lines(db, inbound_id, user_id),
        lambda db: cancel_inbound(db, inbound_id, user_id),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda operation: _race(barrier, pg_sessions, operation), operations
            )
        )

    assert sorted(results) == [200, 409]
    with pg_sessions() as db:
        status = db.get(InboundRecord, inbound_id).status
        lot_count = db.scalar(
            select(func.count(InventoryLot.id)).where(
                InventoryLot.source_inbound_id == inbound_id
            )
        )
        transaction_count = db.scalar(
            select(func.count(InventoryTransaction.id)).where(
                InventoryTransaction.reference_type == "INBOUND",
                InventoryTransaction.reference_id == inbound_id,
            )
        )
        assert (status, lot_count, transaction_count) in {(2, 2, 2), (6, 0, 0)}
