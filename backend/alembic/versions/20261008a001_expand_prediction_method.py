"""Allow descriptive prediction method names."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261008a001"
down_revision: Union[str, Sequence[str], None] = "99fa593d94ff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "predictions",
        "method",
        existing_type=sa.String(length=60),
        type_=sa.String(length=160),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "predictions",
        "method",
        existing_type=sa.String(length=160),
        type_=sa.String(length=60),
        existing_nullable=False,
    )
