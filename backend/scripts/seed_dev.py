"""Deterministic, all-or-nothing synthetic data for the allowlisted DEV DB."""
from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.database_safety import DatabaseSafetyError, SafeDatabaseTarget, validate_destructive_database_target
from app.core.security import hash_password
from app.db.base import Base
from app.models.amazon_fc_address import AmazonFCAddress
from app.models.bol import BOL, BOLItem, BOLStatus
from app.models.carrier import Carrier
from app.models.container_tracking import ContainerTracking, TrackingStatus
from app.models.customer import Customer
from app.models.fba import FBAInventoryAllocation, FBAShipment, FBAStatus
from app.models.inbound import InboundRecord, InboundStatus
from app.models.inventory import InventoryLot, InventoryLotLocation, InventoryStatus, InventoryTransaction, TransactionType
from app.models.outbound import OBStatus, OBType, OutboundInventoryAllocation, OutboundOrder
from app.models.picking import PickingList, PickingListItem, PickingStatus
from app.models.user import ScopeMode, User, UserRole
from app.models.warehouse import Warehouse, WarehouseArea, WarehouseLocation
from scripts.discover_dev_seed_state import BASELINE_COUNTS
from scripts.safe_alembic import EXPECTED_REVISION, SafeMigrationError, assert_connected_database, verify_revision

AT = datetime(2026, 9, 1, 8, tzinfo=UTC)
DATES = (date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3))
SEED_COUNTS = {
    "amazon_fc_addresses": 5, "bol_items": 2, "bols": 2, "carriers": 2,
    "container_trackings": 4, "customers": 2, "fba_inventory_allocations": 4,
    "fba_shipments": 5, "inbound_records": 7, "inventory_lot_locations": 8,
    "inventory_lots": 7, "inventory_transactions": 7, "outbound_inventory_allocations": 4,
    "outbound_orders": 7, "picking_list_items": 3, "picking_lists": 3,
    "users": 3, "warehouse_areas": 8, "warehouse_locations": 10, "warehouses": 2,
}
KEYS = {
    "users": ("username", {"DEV-ADMIN", "DEV-OPERATOR", "DEV-VIEWER"}),
    "customers": ("customer_code", {"DEV-CUST-01", "DEV-CUST-02"}),
    "warehouses": ("warehouse_code", {"DEV-WH-01", "DEV-WH-02"}),
    "carriers": ("carrier_code", {"DEV-CARRIER-01", "DEV-CARRIER-02"}),
    "amazon_fc_addresses": ("fc_code", {f"DEV-FC-{i:02d}" for i in range(1, 6)}),
    "inbound_records": ("inbound_no", {f"DEV-IN-{i:04d}" for i in range(1, 8)}),
    "inventory_lots": ("lot_no", {f"DEV-LOT-{i:04d}" for i in range(1, 8)}),
    "fba_shipments": ("fba_no", {f"DEV-FBA-{i:04d}" for i in range(1, 6)}),
    "outbound_orders": ("ob_no", {f"DEV-OB-{i:04d}" for i in range(1, 8)}),
    "picking_lists": ("picking_no", {f"DEV-PICK-{i:04d}" for i in range(1, 4)}),
    "bols": ("bol_no", {"DEV-BOL-0001", "DEV-BOL-0002"}),
    "container_trackings": ("source_fingerprint", {f"dev-seed-container-{i:02d}" for i in range(1, 5)}),
}

class DevSeedError(RuntimeError): pass


class DevSeedDatabaseError(DevSeedError):
    def __init__(self, stage: str):
        self.stage = stage
        super().__init__(f"DEV database operation failed during {stage}")

def safe_failure(exc: Exception) -> tuple[str, str]:
    """Convert failures to credential-safe, console-encoding-safe output."""
    if isinstance(exc, DatabaseSafetyError):
        return exc.code, str(exc)
    if isinstance(exc, SafeMigrationError):
        return "migration_verification_failed", str(exc)
    if isinstance(exc, (DevSeedDatabaseError, SQLAlchemyError)):
        driver_error = exc.__cause__ if isinstance(exc, DevSeedDatabaseError) else exc
        original = getattr(driver_error, "orig", None)
        sqlstate = getattr(original, "sqlstate", None)
        driver_text = str(original).lower()
        if sqlstate == "28P01" or "password authentication failed" in driver_text:
            return "database_authentication_failed", "DEV database role authentication failed"
        if sqlstate == "3D000" or ("database" in driver_text and "does not exist" in driver_text):
            return "development_database_missing", "DEV database does not exist"
        if sqlstate == "28000" or ("role" in driver_text and "does not exist" in driver_text):
            return "development_role_missing", "DEV database role does not exist"
        if "connection refused" in driver_text:
            return "database_unreachable", "Local PostgreSQL refused the DEV connection"
        if isinstance(exc, DevSeedDatabaseError):
            return "dev_seed_database_failed", str(exc)
        return "database_connection_failed", "DEV database connection or transaction failed"
    if isinstance(exc, DevSeedError):
        return "dev_seed_failed", str(exc)
    return "unexpected_failure", f"DEV seed stopped on {type(exc).__name__}"

def load_dev_target(env: Mapping[str, str]) -> tuple[SafeDatabaseTarget, str, str | None]:
    target = validate_destructive_database_target(env.get("WMS_ENV"), env.get("DATABASE_URL"))
    if target.environment != "development" or target.database != "dlx_yuki_wms_dev":
        raise DevSeedError("Phase D is restricted to the development database")
    return target, env["DATABASE_URL"], env.get("DEV_SEED_USER_PASSWORD")

def d(value: int) -> Decimal: return Decimal(value)

def stamp(obj):
    if hasattr(obj, "created_at"): obj.created_at = AT
    if hasattr(obj, "updated_at"): obj.updated_at = AT
    return obj

def counts(session: Session) -> dict[str, int]:
    return {name: session.scalar(select(func.count()).select_from(table)) or 0 for name, table in Base.metadata.tables.items()}

def expected_counts() -> dict[str, int]:
    return {name: BASELINE_COUNTS.get(name, 0) + SEED_COUNTS.get(name, 0) for name in Base.metadata.tables}

def seed_state(session: Session) -> str:
    actual = counts(session)
    baseline = {name: BASELINE_COUNTS.get(name, 0) for name in Base.metadata.tables}
    if actual == baseline: return "EMPTY_BASELINE"
    if actual != expected_counts():
        changed = sorted(name for name in actual if actual[name] != baseline[name])
        raise DevSeedError("DEV contains partial or unknown business data; changed tables: " + ",".join(changed))
    for table_name, (column_name, wanted) in KEYS.items():
        table = Base.metadata.tables[table_name]
        if set(session.execute(select(table.c[column_name])).scalars()) != wanted:
            raise DevSeedError(f"DEV seed shape is inconsistent in {table_name}")
    return "ALREADY_PRESENT"

def create_seed(session: Session, password: str | None) -> None:
    if password is None or len(password) < 12:
        raise DevSeedError("A hidden DEV-only application password of at least 12 characters is required")
    pw_hash = hash_password(password)
    users = [stamp(User(username=name, display_name=label, email=email, password_hash=pw_hash, role=role, warehouse_scope_mode=ScopeMode.ALL, customer_scope_mode=ScopeMode.ALL)) for name, label, email, role in (
        ("DEV-ADMIN", "Synthetic Admin", "dev-admin@example.invalid", UserRole.ADMIN),
        ("DEV-OPERATOR", "Synthetic Operator", "dev-operator@example.invalid", UserRole.WAREHOUSE),
        ("DEV-VIEWER", "Synthetic Viewer", "dev-viewer@example.invalid", UserRole.VIEWER))]
    customers = [stamp(Customer(customer_code=f"DEV-CUST-{i:02d}", customer_name=f"Synthetic Customer {i}", contact_name="Synthetic Contact", email=f"customer-{i}@example.invalid", remark="DEV synthetic data")) for i in range(1, 3)]
    warehouses = [stamp(Warehouse(warehouse_code=f"DEV-WH-{i:02d}", warehouse_name=f"Synthetic Warehouse {i}", address=f"{i}00 Example Avenue", city="Testville", state="CA", zip_code=f"9000{i}")) for i in range(1, 3)]
    carriers = [stamp(Carrier(carrier_code=f"DEV-CARRIER-{i:02d}", carrier_name=f"Synthetic Carrier {i}", scac=f"D{i:03d}", email=f"carrier-{i}@example.invalid", remark="DEV synthetic data")) for i in range(1, 3)]
    fcs = [stamp(AmazonFCAddress(fc_code=f"DEV-FC-{i:02d}", fc_name=f"Synthetic FC {i}", address_line1=f"{i} Distribution Way", city="Testville", state="CA", zip_code=f"9100{i}")) for i in range(1, 6)]
    session.add_all(users + customers + warehouses + carriers + fcs); session.flush()

    areas, locations = {}, {}
    specs = (("DEV-RCV-01", "RECEIVING"), ("DEV-A01-01", "STORAGE"), ("DEV-A01-02", "STORAGE"), ("DEV-STAGE-01", "STAGING"), ("DEV-HOLD-01", "HOLD"))
    for wi, wh in enumerate(warehouses, 1):
        for code in ("RECEIVING", "STORAGE", "STAGING", "HOLD"):
            area = stamp(WarehouseArea(warehouse_id=wh.id, area_code=code, area_name=code.title())); session.add(area); areas[wi, code] = area
        session.flush()
        for code, area_code in specs:
            loc = stamp(WarehouseLocation(warehouse_id=wh.id, area_id=areas[wi, area_code].id, location_code=code, location_name=f"{code} / WH{wi}")); session.add(loc); locations[wi, code] = loc
    session.flush()

    inbound_statuses = (InboundStatus.PENDING, InboundStatus.UNLOADING, InboundStatus.RECEIVED, InboundStatus.PUT_AWAY, InboundStatus.COMPLETED, InboundStatus.HOLD, InboundStatus.COMPLETED)
    inbounds = []
    for i, status in enumerate(inbound_statuses, 1):
        wi = 1 if i <= 5 else 2; loc = locations[wi, "DEV-HOLD-01" if status == InboundStatus.HOLD else "DEV-A01-01"]
        row = stamp(InboundRecord(inbound_no=f"DEV-IN-{i:04d}", container_number=f"SYN-CONT-{i:04d}", customer_id=customers[(i-1)%2].id, warehouse_id=warehouses[wi-1].id, unload_date=DATES[(i-1)%3], received_date=DATES[(i-1)%3] if status >= InboundStatus.RECEIVED else None, fc_code=fcs[(i-1)%5].fc_code, marking=f"SYN-SKU-{((i-1)%3)+1:03d}", pallet_qty=d(10), carton_qty=d(100), weight_lbs=d(1000), cbm=d(10), location_id=loc.id, po_number=f"DEV-PO-{i:04d}", status=int(status), remark="DEV synthetic lifecycle coverage", created_by=users[1].id))
        session.add(row); inbounds.append(row)
    session.flush()

    shapes = ((InventoryStatus.PARTIALLY_ALLOCATED,10,8,2,0),(InventoryStatus.PARTIALLY_ALLOCATED,10,6,4,0),(InventoryStatus.FULLY_ALLOCATED,10,0,10,0),(InventoryStatus.HOLD,10,0,0,10),(InventoryStatus.DEPLETED,10,0,0,0),(InventoryStatus.AVAILABLE,10,10,0,0),(InventoryStatus.PARTIALLY_ALLOCATED,10,7,3,0))
    lots = []
    for i, (status, original, available, allocated, hold) in enumerate(shapes, 1):
        wi = 1 if i <= 5 else 2; loc = locations[wi, "DEV-HOLD-01" if status == InventoryStatus.HOLD else "DEV-A01-01"]
        row = stamp(InventoryLot(lot_no=f"DEV-LOT-{i:04d}", customer_id=customers[(i-1)%2].id, warehouse_id=warehouses[wi-1].id, source_inbound_id=inbounds[i-1].id, container_number=inbounds[i-1].container_number, fc_code=inbounds[i-1].fc_code, marking=inbounds[i-1].marking, location_id=loc.id, original_pallet_qty=d(original), original_carton_qty=d(original*10), original_weight_lbs=d(original*100), original_cbm=d(original), available_pallet_qty=d(available), available_carton_qty=d(available*10), available_weight_lbs=d(available*100), available_cbm=d(available), allocated_pallet_qty=d(allocated), allocated_carton_qty=d(allocated*10), allocated_weight_lbs=d(allocated*100), allocated_cbm=d(allocated), hold_pallet_qty=d(hold), hold_carton_qty=d(hold*10), inbound_date=DATES[(i-1)%3], status=int(status), remark="DEV synthetic inventory coverage", created_by=users[1].id))
        session.add(row); lots.append(row)
    session.flush()
    for i, lot in enumerate(lots, 1):
        wi = 1 if i <= 5 else 2; loc = locations[wi, "DEV-HOLD-01" if i == 4 else "DEV-A01-01"]
        primary_pallets = d(8) if i == 1 else lot.original_pallet_qty
        primary_cartons = d(80) if i == 1 else lot.original_carton_qty
        session.add(stamp(InventoryLotLocation(inventory_lot_id=lot.id, location_id=loc.id, pallet_qty=primary_pallets, carton_qty=primary_cartons)))
        session.add(InventoryTransaction(inventory_lot_id=lot.id, transaction_type=TransactionType.INBOUND, pallet_delta=lot.original_pallet_qty, carton_delta=lot.original_carton_qty, weight_delta=lot.original_weight_lbs, cbm_delta=lot.original_cbm, to_location_id=loc.id, reference_type="DEV_SEED", reference_id=inbounds[i-1].id, remark="DEV synthetic receipt", created_by=users[1].id, created_at=AT))
    session.add(stamp(InventoryLotLocation(inventory_lot_id=lots[0].id, location_id=locations[1,"DEV-A01-02"].id, pallet_qty=d(2), carton_qty=d(20))))

    fbas = []
    for i, status in enumerate((FBAStatus.DRAFT,FBAStatus.ALLOCATED,FBAStatus.READY,FBAStatus.COMPLETED,FBAStatus.HOLD), 1):
        row = stamp(FBAShipment(fba_no=f"DEV-FBA-{i:04d}", customer_id=customers[(i-1)%2].id, warehouse_id=warehouses[0].id, amazon_fc_code=fcs[i-1].fc_code, amazon_fc_address_id=fcs[i-1].id, status=int(status), scheduled_pickup_at=datetime(2026,9,2,9+i,tzinfo=UTC), appointment_time=datetime(2026,9,3,9+i,tzinfo=UTC), carrier_id=carriers[(i-1)%2].id, reference_no=f"DEV-FBA-REF-{i:04d}", shipment_id=f"SYN-SHIP-{i:04d}", remark="DEV synthetic shortage/exception" if status == FBAStatus.HOLD else "DEV synthetic shipment", created_by=users[1].id))
        session.add(row); fbas.append(row)
    session.flush()
    fba_allocs = []
    for fba_i, lot_i, qty in ((0,0,2),(1,1,4),(2,2,10),(2,6,3)):
        row = stamp(FBAInventoryAllocation(fba_shipment_id=fbas[fba_i].id, inventory_lot_id=lots[lot_i].id, allocated_pallet_qty=d(qty), allocated_carton_qty=d(qty*10), allocated_weight_lbs=d(qty*100), allocated_cbm=d(qty), created_by=users[1].id)); session.add(row); fba_allocs.append(row)
    session.flush()

    outbounds = []
    for i, status in enumerate((OBStatus.NEW,OBStatus.IN_PROGRESS,OBStatus.CONFIRMED,OBStatus.DISPATCHED,OBStatus.COMPLETED,OBStatus.EXCEPTION,OBStatus.CANCELED), 1):
        fba = fbas[i-1] if i <= 3 else None
        row = stamp(OutboundOrder(ob_no=f"DEV-OB-{i:04d}", customer_id=customers[(i-1)%2].id, warehouse_id=warehouses[0].id, carrier_id=carriers[(i-1)%2].id, fba_shipment_id=fba.id if fba else None, status=int(status), loading_team="DEV-TEAM", notify_carrier=False, delivery_type="SYNTHETIC", schedule_pickup_at=datetime(2026,9,2,10+i,tzinfo=UTC), ob_type=OBType.FBA.value if fba else OBType.STANDARD.value, fc_code=fba.amazon_fc_code if fba else None, reference_no=f"DEV-OB-REF-{i:04d}", exception_reason="Synthetic exception" if status == OBStatus.EXCEPTION else None, remark="DEV synthetic outbound", created_by=users[1].id))
        session.add(row); outbounds.append(row)
    session.flush()
    ob_allocs = []
    for ob_i, lot_i, fa_i, qty in ((0,0,0,2),(1,1,1,4),(2,2,2,10),(2,6,3,3)):
        done = qty if outbounds[ob_i].status == OBStatus.COMPLETED else 0
        row = stamp(OutboundInventoryAllocation(outbound_order_id=outbounds[ob_i].id, inventory_lot_id=lots[lot_i].id, fba_allocation_id=fba_allocs[fa_i].id, allocated_pallet_qty=d(qty), allocated_carton_qty=d(qty*10), allocated_weight_lbs=d(qty*100), allocated_cbm=d(qty), completed_pallet_qty=d(done), completed_carton_qty=d(done*10), completed_weight_lbs=d(done*100), completed_cbm=d(done), created_by=users[1].id)); session.add(row); ob_allocs.append(row)
    session.flush()

    picks = []
    for i, status in enumerate((PickingStatus.NEW,PickingStatus.IN_PROGRESS,PickingStatus.COMPLETED), 1):
        row = stamp(PickingList(picking_no=f"DEV-PICK-{i:04d}", outbound_order_id=outbounds[i-1].id, status=status, assigned_team="DEV-TEAM", assigned_to=users[1].id, completed_at=AT if status == PickingStatus.COMPLETED else None, completed_by=users[1].id if status == PickingStatus.COMPLETED else None, remark="DEV synthetic picking", created_by=users[1].id)); session.add(row); picks.append(row)
    session.flush()
    for i, pick in enumerate(picks):
        alloc, lot = ob_allocs[i], lots[i]; qty = int(alloc.allocated_pallet_qty)
        session.add(stamp(PickingListItem(picking_list_id=pick.id, outbound_allocation_id=alloc.id, inventory_lot_id=lot.id, location_id=lot.location_id, lot_no=lot.lot_no, container_number=lot.container_number, fc_code=lot.fc_code, marking=lot.marking, planned_pallet_qty=d(qty), planned_carton_qty=d(qty*10), planned_weight_lbs=d(qty*100), planned_cbm=d(qty), picked_pallet_qty=d(qty if i==2 else 0), picked_carton_qty=d(qty*10 if i==2 else 0), picked_weight_lbs=d(qty*100 if i==2 else 0), picked_cbm=d(qty if i==2 else 0), sequence_no=1, remark="DEV synthetic pick item")))

    for i in range(2):
        bol = stamp(BOL(bol_no=f"DEV-BOL-{i+1:04d}", outbound_order_id=outbounds[i+1].id, fba_shipment_id=fbas[i+1].id, customer_id=customers[(i+1)%2].id, warehouse_id=warehouses[0].id, carrier_id=carriers[i].id, ship_from_name=warehouses[0].warehouse_name, ship_from_address=warehouses[0].address, ship_to_name=fcs[i+1].fc_name, ship_to_address=fcs[i+1].address_line1, amazon_fc_code=fcs[i+1].fc_code, pickup_date=DATES[1], appointment_time="2026-09-03 10:00 UTC", status=BOLStatus.COMPLETED if i else BOLStatus.GENERATED, special_instructions="DEV synthetic BOL", created_by=users[1].id)); session.add(bol); session.flush()
        alloc, lot = ob_allocs[i+1], lots[i+1]
        session.add(BOLItem(bol_id=bol.id, outbound_allocation_id=alloc.id, inventory_lot_id=lot.id, container_number=lot.container_number, fc_code=lot.fc_code, marking=lot.marking, pallet_qty=alloc.allocated_pallet_qty, carton_qty=alloc.allocated_carton_qty, weight_lbs=alloc.allocated_weight_lbs, cbm=alloc.allocated_cbm, description="DEV synthetic freight"))

    for i, status in enumerate((TrackingStatus.PLANNED,TrackingStatus.IN_TRANSIT,TrackingStatus.WAREHOUSE_RECEIVED,TrackingStatus.COMPLETED), 1):
        session.add(ContainerTracking(container_number=f"SYN-TRACK-{i:04d}", mbl_number=f"SYN-MBL-{i:04d}", hbl_number=f"SYN-HBL-{i:04d}", customer_reference=f"DEV-CUST-REF-{i:04d}", pod_eta=datetime(2026,9,1,10+i,tzinfo=UTC), delivery_location="Synthetic Port", final_destination="Synthetic Warehouse", warehouse_id=warehouses[(i-1)%2].id, tracking_status=status, source_type="DEV_SEED", source_file_name="synthetic://phase-d", source_row_number=i, source_fingerprint=f"dev-seed-container-{i:02d}", created_at=AT, updated_at=AT))
    session.flush()

def run() -> tuple[SafeDatabaseTarget, str]:
    target, url, password = load_dev_target(os.environ); engine = create_engine(url)
    stage = "connect"
    try:
        with engine.connect() as connection:
            stage = "target_verification"
            assert_connected_database(connection, target); connection.rollback()
            with connection.begin():
                stage = "revision_verification"
                verify_revision(connection, EXPECTED_REVISION)
                stage = "schema_verification"
                if set(inspect(connection).get_table_names(schema="public")) != set(Base.metadata.tables) | {"alembic_version"}: raise DevSeedError("DEV schema table set does not match current ORM metadata")
                stage = "pre_seed_verification"
                session = Session(bind=connection); state = seed_state(session)
                if state == "ALREADY_PRESENT": return target, "PASS_NO_CHANGES"
                stage = "seed_insert"
                create_seed(session, password)
                stage = "post_seed_verification"
                if seed_state(session) != "ALREADY_PRESENT": raise DevSeedError("Post-seed verification failed")
                stage = "commit"
            return target, "PASS_CREATED"
    except SQLAlchemyError as exc:
        raise DevSeedDatabaseError(stage) from exc
    finally: engine.dispose()

def main() -> int:
    try: target, result = run()
    except Exception as exc:
        code, message = safe_failure(exc)
        print(f"REFUSED code={code}: {message}"); print("PHASE_D_DEV_SEED=STOPPED_ROLLED_BACK"); return 1
    print("DATABASE_SAFETY=PASS"); print(target.sanitized_summary()); print(f"ALEMBIC_REVISION={EXPECTED_REVISION}"); print(f"SEED_RESULT={result}"); print("PHASE_D_DEV_SEED=PASS"); return 0

if __name__ == "__main__": raise SystemExit(main())
