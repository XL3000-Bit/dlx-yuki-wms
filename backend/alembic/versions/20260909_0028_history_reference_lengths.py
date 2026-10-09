"""Preserve historical shipment references without truncation."""
from alembic import op
import sqlalchemy as sa

revision = '20260909_0028'
down_revision = '20260909_0027'
branch_labels = None
depends_on = None

def upgrade():
    op.alter_column('fba_shipments', 'shipment_id', type_=sa.String(200), existing_type=sa.String(100))
    op.alter_column('outbound_orders', 'fc_code', type_=sa.String(100), existing_type=sa.String(20))

def downgrade():
    op.alter_column('fba_shipments', 'shipment_id', type_=sa.String(100), existing_type=sa.String(200))
    op.alter_column('outbound_orders', 'fc_code', type_=sa.String(20), existing_type=sa.String(100))
