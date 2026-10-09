"""phase 8 real data import and large workbook support

Revision ID: 20260828_0008
Revises: e852423c687a
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260828_0008"
down_revision: Union[str, None] = "e852423c687a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for value in ("READING", "MAPPING", "VALIDATING", "READY"):
        op.execute(f"ALTER TYPE import_status ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column("import_jobs", sa.Column("profile_code", sa.String(64)))
    op.add_column("import_jobs", sa.Column("source_sheet", sa.String(100)))
    op.add_column("import_jobs", sa.Column("file_size", sa.Integer()))
    op.add_column("import_jobs", sa.Column("file_hash", sa.String(64)))
    op.add_column("import_jobs", sa.Column("stored_file_path", sa.String(500)))
    op.add_column("import_jobs", sa.Column("batch_size", sa.Integer(), server_default="1000", nullable=False))
    op.add_column("import_jobs", sa.Column("processed_rows", sa.Integer(), server_default="0", nullable=False))
    op.add_column("import_jobs", sa.Column("progress_percent", sa.Numeric(6, 2), server_default="0", nullable=False))
    op.add_column("import_jobs", sa.Column("current_stage", sa.String(32), server_default="UPLOADED", nullable=False))
    op.add_column("import_jobs", sa.Column("detected_columns", postgresql.JSONB()))
    op.add_column("import_jobs", sa.Column("sheet_names", postgresql.JSONB()))
    op.add_column("import_jobs", sa.Column("sheet_row_estimates", postgresql.JSONB()))
    op.add_column("import_jobs", sa.Column("options", postgresql.JSONB()))
    op.add_column("import_jobs", sa.Column("performance", postgresql.JSONB()))
    op.add_column("import_jobs", sa.Column("reconciliation", postgresql.JSONB()))
    op.add_column("import_jobs", sa.Column("duplicate_of_job_id", sa.Integer(), sa.ForeignKey("import_jobs.id", ondelete="SET NULL")))
    op.create_index("ix_import_jobs_profile_code", "import_jobs", ["profile_code"])
    op.create_index("ix_import_jobs_file_hash", "import_jobs", ["file_hash"])
    op.create_index("ix_import_jobs_duplicate_of_job_id", "import_jobs", ["duplicate_of_job_id"])

    op.add_column("import_rows", sa.Column("source_sheet", sa.String(100)))
    op.add_column("import_rows", sa.Column("row_fingerprint", sa.String(64)))
    op.create_index("ix_import_rows_row_fingerprint", "import_rows", ["row_fingerprint"])
    op.add_column("import_errors", sa.Column("suggested_fix", sa.Text()))

    op.add_column("inbound_records", sa.Column("raw_location_text", sa.Text()))
    op.add_column("inbound_records", sa.Column("po_number", sa.String(200)))
    op.add_column("inbound_records", sa.Column("fba_reference", sa.String(200)))
    op.add_column("inbound_records", sa.Column("weight_source", sa.String(32)))
    op.add_column("inbound_records", sa.Column("source_metadata", postgresql.JSONB()))
    op.add_column("inbound_records", sa.Column("import_row_id", sa.Integer(), sa.ForeignKey("import_rows.id", ondelete="SET NULL")))
    op.create_index("ix_inbound_records_po_number", "inbound_records", ["po_number"])
    op.create_index("ix_inbound_records_fba_reference", "inbound_records", ["fba_reference"])
    op.create_index("ix_inbound_records_import_row_id", "inbound_records", ["import_row_id"])

    op.add_column("inventory_lots", sa.Column("raw_location_text", sa.Text()))
    op.add_column("inventory_lots", sa.Column("import_row_id", sa.Integer(), sa.ForeignKey("import_rows.id", ondelete="SET NULL")))
    op.create_index("ix_inventory_lots_import_row_id", "inventory_lots", ["import_row_id"])
    op.create_table(
        "inventory_lot_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inventory_lot_id", sa.Integer(), sa.ForeignKey("inventory_lots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("warehouse_locations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("pallet_qty", sa.Numeric(12, 2)),
        sa.Column("carton_qty", sa.Numeric(12, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("inventory_lot_id", "location_id", name="uq_inventory_lot_location"),
    )
    op.create_index("ix_inventory_lot_locations_inventory_lot_id", "inventory_lot_locations", ["inventory_lot_id"])
    op.create_index("ix_inventory_lot_locations_location_id", "inventory_lot_locations", ["location_id"])

    op.add_column("fba_shipments", sa.Column("po_number", sa.String(200)))
    op.add_column("fba_shipments", sa.Column("source_reference", sa.String(200)))
    op.add_column("fba_shipments", sa.Column("import_job_id", sa.Integer(), sa.ForeignKey("import_jobs.id", ondelete="SET NULL")))
    op.create_index("ix_fba_shipments_po_number", "fba_shipments", ["po_number"])
    op.create_index("ix_fba_shipments_source_reference", "fba_shipments", ["source_reference"])
    op.create_index("ix_fba_shipments_import_job_id", "fba_shipments", ["import_job_id"])
    op.add_column("fba_inventory_allocations", sa.Column("import_row_id", sa.Integer(), sa.ForeignKey("import_rows.id", ondelete="SET NULL")))
    op.create_index("ix_fba_inventory_allocations_import_row_id", "fba_inventory_allocations", ["import_row_id"])

    for name, type_ in (
        ("actual_outbound_time", sa.DateTime(timezone=True)),
        ("appointment_reference", sa.String(100)), ("picking_reference", sa.String(100)),
        ("bol_reference", sa.String(100)), ("redirect_code", sa.String(100)),
        ("pod_reference", sa.String(500)), ("po_number", sa.String(100)),
    ):
        op.add_column("outbound_orders", sa.Column(name, type_))
    op.add_column("outbound_orders", sa.Column("import_job_id", sa.Integer(), sa.ForeignKey("import_jobs.id", ondelete="SET NULL")))
    for name in ("actual_outbound_time", "appointment_reference", "picking_reference", "bol_reference", "po_number", "import_job_id"):
        op.create_index(f"ix_outbound_orders_{name}", "outbound_orders", [name])
    op.add_column("outbound_inventory_allocations", sa.Column("import_row_id", sa.Integer(), sa.ForeignKey("import_rows.id", ondelete="SET NULL")))
    op.create_index("ix_outbound_inventory_allocations_import_row_id", "outbound_inventory_allocations", ["import_row_id"])


def downgrade() -> None:
    op.drop_index("ix_outbound_inventory_allocations_import_row_id", table_name="outbound_inventory_allocations")
    op.drop_column("outbound_inventory_allocations", "import_row_id")
    for name in ("import_job_id", "po_number", "bol_reference", "picking_reference", "appointment_reference", "actual_outbound_time"):
        op.drop_index(f"ix_outbound_orders_{name}", table_name="outbound_orders")
    for name in ("import_job_id", "po_number", "pod_reference", "redirect_code", "bol_reference", "picking_reference", "appointment_reference", "actual_outbound_time"):
        op.drop_column("outbound_orders", name)
    op.drop_index("ix_fba_inventory_allocations_import_row_id", table_name="fba_inventory_allocations")
    op.drop_column("fba_inventory_allocations", "import_row_id")
    for name in ("import_job_id", "source_reference", "po_number"):
        op.drop_index(f"ix_fba_shipments_{name}", table_name="fba_shipments")
        op.drop_column("fba_shipments", name)
    op.drop_table("inventory_lot_locations")
    op.drop_index("ix_inventory_lots_import_row_id", table_name="inventory_lots")
    op.drop_column("inventory_lots", "import_row_id")
    op.drop_column("inventory_lots", "raw_location_text")
    for name in ("import_row_id", "fba_reference", "po_number"):
        op.drop_index(f"ix_inbound_records_{name}", table_name="inbound_records")
    for name in ("import_row_id", "source_metadata", "weight_source", "fba_reference", "po_number", "raw_location_text"):
        op.drop_column("inbound_records", name)
    op.drop_column("import_errors", "suggested_fix")
    op.drop_index("ix_import_rows_row_fingerprint", table_name="import_rows")
    op.drop_column("import_rows", "row_fingerprint")
    op.drop_column("import_rows", "source_sheet")
    for name in ("duplicate_of_job_id", "file_hash", "profile_code"):
        op.drop_index(f"ix_import_jobs_{name}", table_name="import_jobs")
    for name in ("duplicate_of_job_id", "reconciliation", "performance", "options", "sheet_row_estimates", "sheet_names", "detected_columns", "current_stage", "progress_percent", "processed_rows", "batch_size", "stored_file_path", "file_hash", "file_size", "source_sheet", "profile_code"):
        op.drop_column("import_jobs", name)
