"""Separate UNI FBA BOL business state from document state."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = '20260917_0034'
down_revision = '20260909_0033'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('uni_fba_bols',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fba_shipment_id', sa.Integer(), sa.ForeignKey('fba_shipments.id'), nullable=False, unique=True),
        sa.Column('outbound_order_id', sa.Integer(), sa.ForeignKey('outbound_orders.id'), nullable=False, unique=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('details', JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('Pre','Confirmed','In Transit','Delivered','Exception','Canceled')", name='uni_bol_status'))

def downgrade():
    op.drop_table('uni_fba_bols')
