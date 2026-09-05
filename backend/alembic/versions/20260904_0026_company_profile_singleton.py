"""enforce company profile singleton

Revision ID: 20260904_0026
Revises: 20260904_0025
"""

from alembic import op
import sqlalchemy as sa


revision = "20260904_0026"
down_revision = "20260904_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT count(*) FROM company_profiles")).scalar_one()
    if count > 1:
        raise RuntimeError(
            "company_profiles contains multiple rows; resolve duplicates before applying 20260904_0026"
        )
    op.add_column(
        "company_profiles",
        sa.Column("singleton_key", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_check_constraint(
        "singleton_key_is_one",
        "company_profiles",
        "singleton_key = 1",
    )
    op.create_unique_constraint(
        "uq_company_profiles_singleton_key", "company_profiles", ["singleton_key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_company_profiles_singleton_key", "company_profiles", type_="unique")
    op.drop_constraint("singleton_key_is_one", "company_profiles", type_="check")
    op.drop_column("company_profiles", "singleton_key")
