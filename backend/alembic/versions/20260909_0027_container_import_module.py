"""Add container tracking to the PostgreSQL import module enum."""
from alembic import op

revision = "20260909_0027"
down_revision = "20260902_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE import_module ADD VALUE IF NOT EXISTS 'CONTAINER_TRACKING'")


def downgrade() -> None:
    # PostgreSQL cannot remove a single enum value without rebuilding the type.
    pass
