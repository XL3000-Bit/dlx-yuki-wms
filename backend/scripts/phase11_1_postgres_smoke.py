"""Isolated PostgreSQL validation for PHASE 11.1 Picking Scan Workflow.

The default command creates a temporary schema in the configured PostgreSQL
database, exercises the Alembic chain, runs API-level picking scenarios against
that schema, and drops it. Pass ``--keep-schema`` to retain the generated
browser-smoke fixture temporarily.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import URL, make_url


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "WarehousePassword!"

# Scripts are executed by file path during acceptance, so make the backend
# package importable without requiring callers to preconfigure PYTHONPATH.
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _schema_url(base_url: URL, schema: str) -> URL:
    query = {key: value for key, value in base_url.query.items() if key != "options"}
    query["options"] = f"-csearch_path={schema}"
    return base_url.set(query=query)


def _admin_url(base_url: URL) -> URL:
    return base_url.set(
        query={key: value for key, value in base_url.query.items() if key != "options"}
    )


def _run(command: list[str], env: dict[str, str]) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=BACKEND_ROOT, env=env, check=True)


def _post(client, path: str, payload: dict | None = None, expected: int = 200) -> dict:
    response = client.post(path, json=payload) if payload is not None else client.post(path)
    if response.status_code != expected:
        raise AssertionError(
            f"POST {path}: expected {expected}, got {response.status_code}: {response.text}"
        )
    return response.json()


def _create_inventory(client, seed: dict, container_number: str, pallet_qty: int) -> dict:
    inbound = _post(
        client,
        "/api/v1/inbound",
        {
            "container_number": container_number,
            "customer_id": seed["customer_id"],
            "warehouse_id": seed["warehouse_id"],
            "received_date": str(date.today()),
            "fc_code": "ONT8",
            "pallet_qty": pallet_qty,
            "carton_qty": pallet_qty * 2,
            "weight_lbs": pallet_qty * 100,
            "cbm": pallet_qty,
            "location_id": seed["location_id"],
            "status": 3,
        },
        expected=201,
    )
    return _post(client, f"/api/v1/inbound/{inbound['id']}/receive-to-inventory")


def _create_pick(client, seed: dict, container_number: str, pallet_qty: int) -> dict:
    lot = _create_inventory(client, seed, container_number, pallet_qty)
    outbound = _post(
        client,
        "/api/v1/outbounds",
        {
            "customer_id": seed["customer_id"],
            "warehouse_id": seed["warehouse_id"],
            "carrier_id": seed["carrier_id"],
            "ob_type": "STANDARD",
            "delivery_type": "FTL",
        },
        expected=201,
    )
    _post(
        client,
        f"/api/v1/outbounds/{outbound['id']}/allocate",
        {"inventory_lot_id": lot["id"], "pallet_qty": pallet_qty},
    )
    picking = _post(client, f"/api/v1/outbounds/{outbound['id']}/picking-lists")
    return {"lot": lot, "outbound": outbound, "picking": picking}


def _create_session(client, seed: dict, picking_ref: str) -> dict:
    body = _post(
        client,
        "/api/v1/scan-sessions",
        {
            "warehouse_id": seed["warehouse_id"],
            "operation_type": "PICK",
            "picking_ref": picking_ref,
        },
        expected=201,
    )
    return body["session"]


def _scan(client, session_id: int, value: str) -> dict:
    return _post(client, f"/api/v1/scan-sessions/{session_id}/scan", {"value": value})


def _confirm(client, session_id: int, quantity: int, operation_id: str, expected=200):
    response = client.post(
        f"/api/v1/scan-sessions/{session_id}/confirm-pick",
        json={"quantity": quantity, "client_operation_id": operation_id},
    )
    if response.status_code != expected:
        raise AssertionError(
            f"confirm-pick: expected {expected}, got {response.status_code}: {response.text}"
        )
    return response


def _prime(client, seed: dict, facts: dict) -> dict:
    session = _create_session(client, seed, facts["picking"]["picking_no"])
    location = _scan(client, session["id"], seed["location_code"])
    lot = _scan(client, session["id"], facts["lot"]["lot_no"])
    assert location["event"]["event_type"] == "LOCATION_SCANNED"
    assert lot["event"]["event_type"] == "LOT_SCANNED"
    return session


def _seed_database() -> dict:
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models import Carrier, Customer, User, Warehouse, WarehouseArea, WarehouseLocation
    from app.models.user import UserRole

    with SessionLocal.begin() as db:
        admin = User(
            username="phase11_admin",
            display_name="PHASE 11 Smoke Admin",
            email="phase11.admin@example.com",
            password_hash=hash_password(PASSWORD),
            role=UserRole.ADMIN,
        )
        customer = Customer(customer_code="P11", customer_name="PHASE 11 Customer")
        warehouse = Warehouse(
            warehouse_code="DLX-P11",
            warehouse_name="DLX PHASE 11 Warehouse",
            address="11 Scan Way",
            city="Los Angeles",
            state="CA",
            zip_code="90001",
        )
        carrier = Carrier(carrier_code="P11C", carrier_name="PHASE 11 Carrier", scac="P11C")
        db.add_all([admin, customer, warehouse, carrier])
        db.flush()
        area = WarehouseArea(
            warehouse_id=warehouse.id,
            area_code="PICK",
            area_name="Picking",
        )
        db.add(area)
        db.flush()
        location = WarehouseLocation(
            warehouse_id=warehouse.id,
            area_id=area.id,
            location_code="P11-A01",
            location_name="P11 A01",
        )
        db.add(location)
        db.flush()
        return {
            "admin_id": admin.id,
            "customer_id": customer.id,
            "warehouse_id": warehouse.id,
            "carrier_id": carrier.id,
            "location_id": location.id,
            "location_code": location.location_code,
        }


def _run_scenarios() -> dict:
    # Imports intentionally occur only after DATABASE_URL points to the isolated schema.
    from fastapi.testclient import TestClient

    from app.db.session import SessionLocal
    from app.main import app
    from app.models import (
        InventoryLot,
        OutboundInventoryAllocation,
        OutboundOrder,
        PickingList,
        PickingListItem,
        PickingStatus,
        ScanEvent,
    )

    seed = _seed_database()
    client = TestClient(app)
    tokens = _post(
        client,
        "/api/v1/auth/login",
        {"username": "phase11_admin", "password": PASSWORD},
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    client.headers.update(headers)

    # One-shot pick validates the smallest successful mutation.
    single = _create_pick(client, seed, "P11-SINGLE", 1)
    single_session = _prime(client, seed, single)
    _confirm(client, single_session["id"], 1, "pg-single-1")
    with SessionLocal() as db:
        assert db.get(PickingList, single["picking"]["id"]).status == PickingStatus.COMPLETED

    # Partial then full pick, over-pick rejection, idempotency, and mutation boundary.
    facts = _create_pick(client, seed, "P11-PARTIAL-FULL", 4)
    session = _prime(client, seed, facts)
    duplicate_session = client.post(
        "/api/v1/scan-sessions",
        json={
            "warehouse_id": seed["warehouse_id"],
            "operation_type": "PICK",
            "picking_ref": facts["picking"]["picking_no"],
        },
    )
    assert duplicate_session.status_code == 409, duplicate_session.text

    with SessionLocal() as db:
        allocation = db.scalar(
            select(OutboundInventoryAllocation).where(
                OutboundInventoryAllocation.outbound_order_id == facts["outbound"]["id"]
            )
        )
        stored_lot = db.get(InventoryLot, facts["lot"]["id"])
        stored_outbound = db.get(OutboundOrder, facts["outbound"]["id"])
        mutation_before = (
            stored_lot.available_pallet_qty,
            stored_lot.allocated_pallet_qty,
            allocation.allocated_pallet_qty,
            allocation.completed_pallet_qty,
            stored_outbound.status,
        )

    over_pick = _confirm(client, session["id"], 5, "pg-over-pick", expected=409)
    assert "remaining quantity" in over_pick.text
    first = _confirm(client, session["id"], 1, "pg-partial-1").json()
    repeated = _confirm(client, session["id"], 1, "pg-partial-1").json()
    assert repeated["event"]["id"] == first["event"]["id"]
    with SessionLocal() as db:
        picking = db.get(PickingList, facts["picking"]["id"])
        item = db.scalar(
            select(PickingListItem).where(PickingListItem.picking_list_id == picking.id)
        )
        assert picking.status == PickingStatus.IN_PROGRESS
        assert item.picked_pallet_qty == Decimal("1")
        assert db.scalar(
            select(func.count(ScanEvent.id)).where(
                ScanEvent.session_id == session["id"],
                ScanEvent.client_operation_id == "pg-partial-1",
            )
        ) == 1

    _scan(client, session["id"], seed["location_code"])
    _scan(client, session["id"], facts["lot"]["lot_no"])
    _confirm(client, session["id"], 3, "pg-full-3")
    with SessionLocal() as db:
        picking = db.get(PickingList, facts["picking"]["id"])
        allocation = db.scalar(
            select(OutboundInventoryAllocation).where(
                OutboundInventoryAllocation.outbound_order_id == facts["outbound"]["id"]
            )
        )
        stored_lot = db.get(InventoryLot, facts["lot"]["id"])
        stored_outbound = db.get(OutboundOrder, facts["outbound"]["id"])
        mutation_after = (
            stored_lot.available_pallet_qty,
            stored_lot.allocated_pallet_qty,
            allocation.allocated_pallet_qty,
            allocation.completed_pallet_qty,
            stored_outbound.status,
        )
        assert picking.status == PickingStatus.COMPLETED
        assert mutation_after == mutation_before

    # Two distinct operation IDs race for the final unit. PostgreSQL row locks must
    # serialize the confirmations: exactly one succeeds and one observes completion.
    race = _create_pick(client, seed, "P11-CONCURRENT", 1)
    race_session = _prime(client, seed, race)
    barrier = threading.Barrier(2)

    def contender(operation_id: str) -> tuple[int, str]:
        contender_client = TestClient(app, headers=headers)
        barrier.wait(timeout=10)
        response = contender_client.post(
            f"/api/v1/scan-sessions/{race_session['id']}/confirm-pick",
            json={"quantity": 1, "client_operation_id": operation_id},
        )
        return response.status_code, response.text

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(contender, ("pg-race-a", "pg-race-b"))
        )
    assert sorted(status for status, _ in outcomes) == [200, 409], outcomes
    with SessionLocal() as db:
        race_item = db.scalar(
            select(PickingListItem).where(
                PickingListItem.picking_list_id == race["picking"]["id"]
            )
        )
        accepted_race_events = db.scalar(
            select(func.count(ScanEvent.id)).where(
                ScanEvent.session_id == race_session["id"],
                ScanEvent.event_type == "PICK_CONFIRMED",
            )
        )
        assert race_item.picked_pallet_qty == Decimal("1")
        assert accepted_race_events == 1

    # Leave one clean fixture with no session so browser smoke can exercise the UI.
    browser = _create_pick(client, seed, "P11-BROWSER", 2)
    return {
        "status": "PASS",
        "scenarios": [
            "single pick",
            "partial then full pick",
            "over-pick rejection",
            "duplicate operation id",
            "concurrent final-unit race",
            "inventory/allocation/outbound mutation boundary",
        ],
        "browser_fixture": {
            "username": "phase11_admin",
            "password": PASSWORD,
            "warehouse_id": seed["warehouse_id"],
            "warehouse_code": "DLX-P11",
            "picking_ref": browser["picking"]["picking_no"],
            "outbound_ref": browser["outbound"]["ob_no"],
            "location_code": seed["location_code"],
            "lot_no": browser["lot"]["lot_no"],
            "quantity": 2,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--keep-schema",
        action="store_true",
        help="Retain the isolated schema and print its name for manual browser smoke",
    )
    args = parser.parse_args()
    if args.scenario:
        print(json.dumps(_run_scenarios(), indent=2), flush=True)
        return 0

    # Importing settings here does not create the application's global engine.
    from app.core.config import settings

    base_url = make_url(settings.database_url)
    schema = f"phase11_1_smoke_{uuid.uuid4().hex[:10]}"
    admin_engine = create_engine(_admin_url(base_url), isolation_level="AUTOCOMMIT")
    schema_url = _schema_url(base_url, schema)
    schema_url_text = schema_url.render_as_string(hide_password=False)
    env = os.environ.copy()
    env["DATABASE_URL"] = schema_url_text

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    print(f"Created isolated schema: {schema}", flush=True)
    try:
        python = str(Path(sys.executable).resolve())
        _run([python, "-m", "alembic", "upgrade", "head"], env)
        _run([python, "-m", "alembic", "check"], env)
        _run([python, "-m", "alembic", "downgrade", "20260830_0022"], env)
        _run([python, "-m", "alembic", "upgrade", "20260830_0023"], env)
        _run([python, "-m", "alembic", "check"], env)
        _run([python, str(Path(__file__).resolve()), "--scenario"], env)
        print("PHASE 11.1 PostgreSQL smoke: PASS", flush=True)
        if args.keep_schema:
            print(f"Retained schema: {schema}", flush=True)
            print(
                "For local manual smoke, set DATABASE_URL to the same database with "
                f"options=-csearch_path={schema} before starting the backend.",
                flush=True,
            )
    finally:
        if not args.keep_schema:
            with admin_engine.connect() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            print(f"Dropped isolated schema: {schema}", flush=True)
        admin_engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
