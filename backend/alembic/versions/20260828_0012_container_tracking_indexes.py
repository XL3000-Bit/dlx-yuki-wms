"""align container tracking indexes"""
from alembic import op
import sqlalchemy as sa
revision='20260828_0012';down_revision='20260828_0011';branch_labels=None;depends_on=None
def upgrade():
 for name,col in [('ix_container_trackings_pod_eta','pod_eta'),('ix_container_trackings_actual_delivery_at','actual_delivery_at'),('ix_container_trackings_scheduled_delivery_at','scheduled_delivery_at'),('ix_container_trackings_wa_received_at','wa_received_at'),('ix_container_trackings_wa_complete_at','wa_complete_at'),('ix_container_trackings_warehouse_id','warehouse_id'),('ix_container_trackings_tracking_status','tracking_status')]: op.create_index(name,'container_trackings',[col])
 op.alter_column('container_trackings','created_at',nullable=False);op.alter_column('container_trackings','updated_at',nullable=False)
def downgrade(): pass
