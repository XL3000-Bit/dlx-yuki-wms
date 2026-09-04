"""enforce one active picking list and BOL per outbound

Revision ID: 20260904_0028
Revises: 20260904_0027
"""
from alembic import op
import sqlalchemy as sa


revision = "20260904_0028"
down_revision = "20260904_0027"
branch_labels = None
depends_on = None


def _fail_on_duplicates(table: str) -> None:
    connection = op.get_bind()
    duplicates = connection.execute(sa.text(
        f"SELECT outbound_order_id, count(*) FROM {table} "
        "WHERE status <> 4 GROUP BY outbound_order_id HAVING count(*) > 1 LIMIT 1"
    )).first()
    if duplicates:
        raise RuntimeError(
            f"Cannot enforce active-document uniqueness: {table} has "
            f"{duplicates[1]} active rows for outbound {duplicates[0]}"
        )


def upgrade() -> None:
    _fail_on_duplicates("picking_lists")
    _fail_on_duplicates("bols")
    active = sa.text("status <> 4")
    op.create_index("uq_picking_lists_active_outbound", "picking_lists", ["outbound_order_id"], unique=True, postgresql_where=active, sqlite_where=active)
    op.create_index("uq_bols_active_outbound", "bols", ["outbound_order_id"], unique=True, postgresql_where=active, sqlite_where=active)


def downgrade() -> None:
    op.drop_index("uq_bols_active_outbound", table_name="bols")
    op.drop_index("uq_picking_lists_active_outbound", table_name="picking_lists")
