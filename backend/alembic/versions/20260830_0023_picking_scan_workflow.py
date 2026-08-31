"""picking scan workflow

Revision ID: 20260830_0023
Revises: 20260830_0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260830_0023"
down_revision: str | None = "20260830_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scan_sessions", sa.Column("current_location_id", sa.Integer(), nullable=True))
    op.add_column(
        "scan_sessions", sa.Column("current_picking_item_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_scan_sessions_current_location_id_warehouse_locations",
        "scan_sessions",
        "warehouse_locations",
        ["current_location_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_scan_sessions_current_picking_item_id_picking_list_items",
        "scan_sessions",
        "picking_list_items",
        ["current_picking_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_scan_sessions_current_location_id",
        "scan_sessions",
        ["current_location_id"],
        unique=False,
    )
    op.create_index(
        "ix_scan_sessions_current_picking_item_id",
        "scan_sessions",
        ["current_picking_item_id"],
        unique=False,
    )
    op.create_index(
        "uq_scan_sessions_open_pick_picking",
        "scan_sessions",
        ["picking_id"],
        unique=True,
        postgresql_where=sa.text(
            "operation_type = 'PICK' AND status = 'OPEN' AND picking_id IS NOT NULL"
        ),
    )

    op.add_column(
        "scan_events",
        sa.Column(
            "event_type",
            sa.String(length=30),
            server_default="GENERIC_SCANNED",
            nullable=False,
        ),
    )
    op.add_column(
        "scan_events", sa.Column("client_operation_id", sa.String(length=64), nullable=True)
    )
    op.add_column("scan_events", sa.Column("picking_item_id", sa.Integer(), nullable=True))
    op.add_column("scan_events", sa.Column("quantity", sa.Numeric(12, 2), nullable=True))
    op.add_column("scan_events", sa.Column("quantity_unit", sa.String(length=20), nullable=True))
    op.create_foreign_key(
        "fk_scan_events_picking_item_id_picking_list_items",
        "scan_events",
        "picking_list_items",
        ["picking_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_scan_events_picking_item_id",
        "scan_events",
        ["picking_item_id"],
        unique=False,
    )
    op.create_index(
        "uq_scan_events_session_client_operation",
        "scan_events",
        ["session_id", "client_operation_id"],
        unique=True,
        postgresql_where=sa.text("client_operation_id IS NOT NULL"),
    )

    op.drop_constraint("ck_scan_events_result_values", "scan_events", type_="check")
    op.create_check_constraint(
        "ck_scan_events_result_values",
        "scan_events",
        "result IN ('ACCEPTED', 'REJECTED', 'DUPLICATE', 'NOT_FOUND', "
        "'WRONG_WAREHOUSE', 'WRONG_OUTBOUND', 'WRONG_LOCATION', 'INVALID_STATE', "
        "'PICK_SOURCE_MISMATCH')",
    )
    op.create_check_constraint(
        "ck_scan_events_event_type_values",
        "scan_events",
        "event_type IN ('GENERIC_SCANNED', 'LOCATION_SCANNED', 'LOT_SCANNED', "
        "'PICK_CONFIRMED')",
    )
    op.create_check_constraint(
        "ck_scan_events_quantity_unit_values",
        "scan_events",
        "quantity_unit IS NULL OR quantity_unit IN ('PALLET', 'CARTON')",
    )
    op.create_check_constraint(
        "ck_scan_events_quantity_positive",
        "scan_events",
        "quantity IS NULL OR quantity > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_scan_events_quantity_positive", "scan_events", type_="check")
    op.drop_constraint("ck_scan_events_quantity_unit_values", "scan_events", type_="check")
    op.drop_constraint("ck_scan_events_event_type_values", "scan_events", type_="check")
    op.drop_constraint("ck_scan_events_result_values", "scan_events", type_="check")
    op.create_check_constraint(
        "ck_scan_events_result_values",
        "scan_events",
        "result IN ('ACCEPTED', 'REJECTED', 'DUPLICATE', 'NOT_FOUND', "
        "'WRONG_WAREHOUSE', 'WRONG_OUTBOUND', 'WRONG_LOCATION', 'INVALID_STATE')",
    )

    op.drop_index("uq_scan_events_session_client_operation", table_name="scan_events")
    op.drop_index("ix_scan_events_picking_item_id", table_name="scan_events")
    op.drop_constraint(
        "fk_scan_events_picking_item_id_picking_list_items", "scan_events", type_="foreignkey"
    )
    op.drop_column("scan_events", "quantity_unit")
    op.drop_column("scan_events", "quantity")
    op.drop_column("scan_events", "picking_item_id")
    op.drop_column("scan_events", "client_operation_id")
    op.drop_column("scan_events", "event_type")

    op.drop_index("uq_scan_sessions_open_pick_picking", table_name="scan_sessions")
    op.drop_index("ix_scan_sessions_current_picking_item_id", table_name="scan_sessions")
    op.drop_index("ix_scan_sessions_current_location_id", table_name="scan_sessions")
    op.drop_constraint(
        "fk_scan_sessions_current_picking_item_id_picking_list_items",
        "scan_sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_scan_sessions_current_location_id_warehouse_locations",
        "scan_sessions",
        type_="foreignkey",
    )
    op.drop_column("scan_sessions", "current_picking_item_id")
    op.drop_column("scan_sessions", "current_location_id")
