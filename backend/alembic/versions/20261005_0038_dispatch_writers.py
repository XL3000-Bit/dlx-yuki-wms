"""Explicit dispatch domains and writer provenance; never infer legacy facts."""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0038"
down_revision = "20260925_0037"
branch_labels = depends_on = None


def upgrade():
    op.create_table("load_dispatch_executions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("load_id", sa.Integer(), sa.ForeignKey("loads.id", ondelete="RESTRICT"), nullable=False, unique=True), sa.Column("operation_id", sa.String(64), nullable=False, unique=True), sa.Column("plan_id", sa.Integer(), sa.ForeignKey("load_dispatch_plans.id", ondelete="RESTRICT"), nullable=False), sa.Column("content_revision", sa.Integer(), nullable=False), sa.Column("performed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    for table in ("loads", "outbound_orders"):
        op.add_column(table, sa.Column("dispatch_business_type", sa.String(10), nullable=True))
        op.create_check_constraint(f"ck_{table}_dispatch_domain", table,
                                   "dispatch_business_type IN ('FBA', 'PRIVATE')")
    for table, columns in (("load_allocations", ("created_by",)),
                           ("load_dispatch_plans", ("created_by", "finalized_by"))):
        for column in columns:
            op.add_column(table, sa.Column(column, sa.Integer(), nullable=True))
            op.create_foreign_key(f"fk_{table}_{column}", table, "users", [column], ["id"], ondelete="RESTRICT")


def downgrade():
    op.drop_table("load_dispatch_executions")
    for table, columns in (("load_allocations", ("created_by",)),
                           ("load_dispatch_plans", ("created_by", "finalized_by"))):
        for column in columns:
            op.drop_constraint(f"fk_{table}_{column}", table, type_="foreignkey")
            op.drop_column(table, column)
    for table in ("loads", "outbound_orders"):
        op.drop_constraint(f"ck_{table}_dispatch_domain", table, type_="check")
        op.drop_column(table, "dispatch_business_type")
