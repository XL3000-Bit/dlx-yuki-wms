"""Read-only verification of the deterministic Phase D DEV seed."""
from __future__ import annotations

import enum
import os
from collections.abc import Mapping

from sqlalchemy import and_, create_engine, distinct, exists, func, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import app.models  # noqa: F401 - register all mapped tables
from app.core.database_safety import DatabaseSafetyError, SafeDatabaseTarget, validate_destructive_database_target
from app.db.base import Base
from app.models.bol import BOLStatus
from app.models.container_tracking import TrackingStatus
from app.models.fba import FBAStatus
from app.models.inbound import InboundStatus
from app.models.inventory import InventoryStatus
from app.models.outbound import OBStatus
from app.models.picking import PickingStatus
from scripts.safe_alembic import get_code_head, SafeMigrationError, assert_connected_database, verify_revision
from scripts.seed_dev import KEYS, expected_counts, seed_state


DISPLAY_COUNTS = {
    "CUSTOMERS": "customers",
    "WAREHOUSES": "warehouses",
    "CARRIERS": "carriers",
    "USERS": "users",
    "LOCATIONS": "warehouse_locations",
    "INBOUNDS": "inbound_records",
    "INVENTORY_LOTS": "inventory_lots",
    "FBA_SHIPMENTS": "fba_shipments",
    "OUTBOUND_ORDERS": "outbound_orders",
    "PICKING_LISTS": "picking_lists",
    "BOLS": "bols",
    "CONTAINER_TRACKINGS": "container_trackings",
}

STATUS_RULES = {
    ("inbound_records", "status"): {int(value) for value in InboundStatus},
    ("inventory_lots", "status"): {int(value) for value in InventoryStatus},
    ("fba_shipments", "status"): {int(value) for value in FBAStatus},
    ("outbound_orders", "status"): {int(value) for value in OBStatus},
    ("picking_lists", "status"): {
        PickingStatus.NEW, PickingStatus.PRINTED, PickingStatus.IN_PROGRESS,
        PickingStatus.COMPLETED, PickingStatus.CANCELED, PickingStatus.EXCEPTION,
    },
    ("bols", "status"): {
        BOLStatus.DRAFT, BOLStatus.GENERATED, BOLStatus.PRINTED,
        BOLStatus.COMPLETED, BOLStatus.CANCELED,
    },
    ("container_trackings", "tracking_status"): set(TrackingStatus),
}


class DevSeedVerificationError(RuntimeError):
    """A credential-safe Phase E verification failure."""


class DevSeedVerificationDatabaseError(DevSeedVerificationError):
    def __init__(self, stage: str):
        self.stage = stage
        super().__init__(f"Read-only DEV verification failed during {stage}")


def load_dev_target(environ: Mapping[str, str]) -> tuple[SafeDatabaseTarget, str]:
    target = validate_destructive_database_target(environ.get("WMS_ENV"), environ.get("DATABASE_URL"))
    if target.environment != "development" or target.database != "dlx_yuki_wms_dev":
        raise DevSeedVerificationError("Phase E is restricted to the development database")
    return target, environ["DATABASE_URL"]


def _orphan_count(session: Session) -> int:
    total = 0
    for child in Base.metadata.tables.values():
        for constraint in child.foreign_key_constraints:
            elements = list(constraint.elements)
            parent_table = elements[0].column.table
            parent = parent_table.alias(f"phase_e_parent_{child.name}_{parent_table.name}")
            child_columns = [element.parent for element in elements]
            parent_columns = [parent.c[element.column.name] for element in elements]
            parent_match = and_(*(left == right for left, right in zip(parent_columns, child_columns)))
            checked_value = and_(*(column.is_not(None) for column in child_columns))
            missing_parent = ~exists(select(1).select_from(parent).where(parent_match))
            total += session.scalar(
                select(func.count()).select_from(child).where(and_(checked_value, missing_parent))
            ) or 0
    return total


def _natural_keys_are_unique(session: Session) -> bool:
    for table_name, (column_name, _wanted) in KEYS.items():
        column = Base.metadata.tables[table_name].c[column_name]
        row_count, unique_count = session.execute(
            select(func.count(column), func.count(distinct(column)))
        ).one()
        if row_count != unique_count:
            return False
    return True


def _status_values_are_valid(session: Session) -> bool:
    for (table_name, column_name), allowed in STATUS_RULES.items():
        column = Base.metadata.tables[table_name].c[column_name]
        actual = set(session.execute(select(column).distinct()).scalars())
        normalized = {value.value if isinstance(value, enum.Enum) else value for value in actual}
        normalized_allowed = {value.value if isinstance(value, enum.Enum) else value for value in allowed}
        if not normalized <= normalized_allowed:
            return False
    return True


def verify() -> tuple[SafeDatabaseTarget, dict[str, int], int]:
    target, database_url = load_dev_target(os.environ)
    engine = create_engine(database_url)
    stage = "connect"
    try:
        with engine.connect() as connection:
            stage = "target_verification"
            assert_connected_database(connection, target)
            connection.rollback()
            transaction = connection.begin()
            try:
                stage = "read_only_guard"
                connection.execute(text("SET TRANSACTION READ ONLY"))
                stage = "revision_verification"
                verify_revision(connection)
                stage = "schema_verification"
                database_tables = set(inspect(connection).get_table_names(schema="public"))
                if database_tables != set(Base.metadata.tables) | {"alembic_version"}:
                    raise DevSeedVerificationError("DEV schema table set does not match current ORM metadata")

                session = Session(bind=connection)
                stage = "seed_shape_verification"
                if seed_state(session) != "ALREADY_PRESENT":
                    raise DevSeedVerificationError("Deterministic DEV seed is not present")
                counts = expected_counts()

                stage = "foreign_key_verification"
                orphans = _orphan_count(session)
                if orphans:
                    raise DevSeedVerificationError(f"DEV seed contains {orphans} orphaned foreign-key rows")
                stage = "natural_key_verification"
                if not _natural_keys_are_unique(session):
                    raise DevSeedVerificationError("DEV seed contains duplicate natural keys")
                stage = "status_verification"
                if not _status_values_are_valid(session):
                    raise DevSeedVerificationError("DEV seed contains an invalid lifecycle status")
            finally:
                if transaction.is_active:
                    transaction.rollback()
        return target, counts, orphans
    except (DatabaseSafetyError, SafeMigrationError, DevSeedVerificationError):
        raise
    except SQLAlchemyError as exc:
        raise DevSeedVerificationDatabaseError(stage) from exc
    finally:
        engine.dispose()


def _safe_failure(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, DatabaseSafetyError):
        return exc.code, str(exc)
    if isinstance(exc, SafeMigrationError):
        return "migration_verification_failed", str(exc)
    if isinstance(exc, DevSeedVerificationDatabaseError):
        original = getattr(exc.__cause__, "orig", None)
        if getattr(original, "sqlstate", None) == "28P01" or "password authentication failed" in str(original).lower():
            return "database_authentication_failed", "DEV database role authentication failed"
        return "dev_seed_verification_database_failed", str(exc)
    if isinstance(exc, DevSeedVerificationError):
        return "dev_seed_verification_failed", str(exc)
    return "unexpected_failure", f"Phase E stopped on {type(exc).__name__}"


def main() -> int:
    try:
        target, counts, orphans = verify()
    except Exception as exc:
        code, message = _safe_failure(exc)
        print(f"REFUSED code={code}: {message}")
        print("PHASE_E_SEED_VERIFY=STOPPED")
        return 1

    print("DATABASE_SAFETY=PASS")
    print(target.sanitized_summary())
    print(f"ALEMBIC_REVISION={get_code_head()}")
    for label, table_name in DISPLAY_COUNTS.items():
        print(f"{label}={counts[table_name]}")
    print("FOREIGN_KEYS=PASS")
    print(f"ORPHANS={orphans}")
    print("NATURAL_KEYS_UNIQUE=PASS")
    print("STATUS_VALUES_VALID=PASS")
    print("PHASE_E_SEED_VERIFY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
