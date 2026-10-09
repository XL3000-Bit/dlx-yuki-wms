"""Separate the displayed Dispatch OB from each BOL's inventory order."""
from alembic import op
import sqlalchemy as sa

revision = '20260917_0036'
down_revision = '20260917_0035'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('uni_fba_bols', sa.Column('dispatch_ob_no', sa.String(100), nullable=True))
    op.create_index('ix_uni_fba_bols_dispatch_ob_no', 'uni_fba_bols', ['dispatch_ob_no'])


def downgrade():
    op.drop_index('ix_uni_fba_bols_dispatch_ob_no', 'uni_fba_bols')
    op.drop_column('uni_fba_bols', 'dispatch_ob_no')
