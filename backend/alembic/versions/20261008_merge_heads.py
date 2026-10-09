"""Merge email/incident and prediction schema heads.

Revision ID: 20261008_merge_heads
Revises: 20261008_incident, 20261008a001
"""
from typing import Sequence, Union

from alembic import op  # noqa: F401

revision: str = "20261008_merge_heads"
down_revision: Union[str, Sequence[str], None] = (
    "20261008_incident",
    "20261008a001",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
