"""Give existing cargo stable BOL identities without changing inventory."""
from alembic import op
import sqlalchemy as sa

revision = "20260909_0033"
down_revision = "20260909_0032"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    # Keep this data migration independent of changing application models.
    for table, key in (("inbound_records", "inbound_id"), ("fba_shipments", "fba_shipment_id"),
                       ("outbound_orders", "history_outbound_id")):
        history = "" if table != "outbound_orders" else """
            AND EXISTS (SELECT 1 FROM import_jobs j WHERE j.id = source.import_job_id
                        AND j.profile_code = 'WEST_COAST_4_0_HISTORY')"""
        connection.execute(sa.text(f"""
            INSERT INTO cargo_bols ({key})
            SELECT source.id FROM {table} source
            WHERE NOT EXISTS (SELECT 1 FROM cargo_bols c WHERE c.{key} = source.id)
            {history}
            ORDER BY source.id
            ON CONFLICT DO NOTHING
        """))
    connection.execute(sa.text("""
        UPDATE outbound_inventory_allocations
        SET cargo_bol_id = (
            SELECT c.id FROM cargo_bols c
            WHERE (
                outbound_inventory_allocations.fba_allocation_id IS NOT NULL
                AND c.fba_shipment_id = (
                    SELECT f.fba_shipment_id FROM fba_inventory_allocations f
                    WHERE f.id = outbound_inventory_allocations.fba_allocation_id
                )
            ) OR (
                outbound_inventory_allocations.fba_allocation_id IS NULL
                AND c.inbound_id = (
                    SELECT lot.source_inbound_id FROM inventory_lots lot
                    WHERE lot.id = outbound_inventory_allocations.inventory_lot_id
                )
            )
        )
        WHERE cargo_bol_id IS NULL
    """))


def downgrade():
    # Published identities must stay stable, including after downgrade/re-upgrade.
    pass
