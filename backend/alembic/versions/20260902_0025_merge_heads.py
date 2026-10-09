"""Merge staging/load verification and company profile heads.

Revision ID: 20260902_0025
Revises: 20260831_0024, 20260901_0021
Create Date: 2026-09-02
"""

from collections.abc import Sequence


revision: str = "20260902_0025"
down_revision: tuple[str, str] = ("20260831_0024", "20260901_0021")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge the two schema histories without changing the database."""


def downgrade() -> None:
    """Split the history back to the two parent revisions."""
