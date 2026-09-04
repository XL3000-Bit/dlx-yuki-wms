"""merge live main heads

Revision ID: 20260904_0025
Revises: 20260831_0024, 20260901_0021
"""
from collections.abc import Sequence


revision: str = "20260904_0025"
down_revision: tuple[str, str] = ("20260831_0024", "20260901_0021")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
