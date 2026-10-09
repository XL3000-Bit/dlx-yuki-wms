"""scan execution foundation

Revision ID: 20260830_0022
Revises: 20260830_0021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260830_0022"
down_revision: str | None = "20260830_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scan_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_no", sa.String(length=32), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("operation_type", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("outbound_id", sa.Integer(), nullable=True),
        sa.Column("picking_id", sa.Integer(), nullable=True),
        sa.Column("load_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="OPEN", nullable=False),
        sa.Column("last_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "operation_type IN ('PICK', 'STAGE', 'LOAD_VERIFY')",
            name="ck_scan_sessions_operation_type_values",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'COMPLETED', 'CANCELED')",
            name="ck_scan_sessions_status_values",
        ),
        sa.ForeignKeyConstraint(
            ["load_id"], ["loads.id"],
            name="fk_scan_sessions_load_id_loads", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["outbound_id"], ["outbound_orders.id"],
            name="fk_scan_sessions_outbound_id_outbound_orders", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["picking_id"], ["picking_lists.id"],
            name="fk_scan_sessions_picking_id_picking_lists", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_scan_sessions_user_id_users", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"],
            name="fk_scan_sessions_warehouse_id_warehouses", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_scan_sessions"),
    )
    op.create_index("ix_scan_sessions_session_no", "scan_sessions", ["session_no"], unique=True)
    for column in ("warehouse_id", "user_id", "outbound_id", "picking_id", "load_id", "status"):
        op.create_index(f"ix_scan_sessions_{column}", "scan_sessions", [column], unique=False)
    op.create_index(
        "ix_scan_sessions_warehouse_status", "scan_sessions", ["warehouse_id", "status"], unique=False
    )
    op.create_index(
        "ix_scan_sessions_user_status", "scan_sessions", ["user_id", "status"], unique=False
    )

    op.create_table(
        "scan_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("raw_value", sa.String(length=255), nullable=False),
        sa.Column("normalized_value", sa.String(length=255), nullable=False),
        sa.Column("scan_type", sa.String(length=30), nullable=False),
        sa.Column("result", sa.String(length=30), nullable=False),
        sa.Column("matched_entity_type", sa.String(length=40), nullable=True),
        sa.Column("matched_entity_id", sa.Integer(), nullable=True),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("reference_value", sa.String(length=255), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("scanned_by", sa.Integer(), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "scan_type IN ('UNKNOWN', 'LOCATION', 'OUTBOUND', 'FBA', 'CONTAINER', "
            "'PICKING', 'INVENTORY_LOT')",
            name="ck_scan_events_scan_type_values",
        ),
        sa.CheckConstraint(
            "result IN ('ACCEPTED', 'REJECTED', 'DUPLICATE', 'NOT_FOUND', "
            "'WRONG_WAREHOUSE', 'WRONG_OUTBOUND', 'WRONG_LOCATION', 'INVALID_STATE')",
            name="ck_scan_events_result_values",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"], ["warehouse_locations.id"],
            name="fk_scan_events_location_id_warehouse_locations", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["scanned_by"], ["users.id"],
            name="fk_scan_events_scanned_by_users", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["scan_sessions.id"],
            name="fk_scan_events_session_id_scan_sessions", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_scan_events"),
    )
    for column in ("session_id", "normalized_value", "result", "matched_entity_id", "location_id", "scanned_by"):
        op.create_index(f"ix_scan_events_{column}", "scan_events", [column], unique=False)
    op.create_index(
        "ix_scan_events_session_scanned", "scan_events", ["session_id", "scanned_at", "id"], unique=False
    )
    op.create_index(
        "ix_scan_events_session_normalized", "scan_events", ["session_id", "normalized_value"], unique=False
    )

    op.execute(
        """
        CREATE FUNCTION prevent_scan_event_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'scan_events rows are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_scan_events_append_only
        BEFORE UPDATE OR DELETE ON scan_events
        FOR EACH ROW EXECUTE FUNCTION prevent_scan_event_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_scan_events_append_only ON scan_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_scan_event_mutation()")
    op.drop_table("scan_events")
    op.drop_table("scan_sessions")
