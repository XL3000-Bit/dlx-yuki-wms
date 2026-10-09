"""Persist outbound booking quantity and related source references."""
from alembic import op
import sqlalchemy as sa
revision = '20260909_0030'
down_revision = '20260909_0029'
branch_labels = None
depends_on = None
def upgrade():
    op.add_column('outbound_orders', sa.Column('booked_pallet_qty', sa.Numeric(12,2), nullable=True))
    op.add_column('outbound_orders', sa.Column('related_bols', sa.JSON(), nullable=True))
def downgrade():
    op.drop_column('outbound_orders','related_bols')
    op.drop_column('outbound_orders','booked_pallet_qty')
