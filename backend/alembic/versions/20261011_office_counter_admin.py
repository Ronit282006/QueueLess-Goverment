"""Office administration fields and per-office counter codes.

Revision ID: 20261011_office_admin
Revises: 20261010_geo_grace
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261011_office_admin"
down_revision = "20261010_geo_grace"
branch_labels = None
depends_on = None


def _add_column_if_missing(insp, table: str, column: sa.Column) -> None:
    existing = {c["name"] for c in insp.get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def _unique_code_index_exists(insp, table: str) -> bool:
    names = {ix["name"] for ix in insp.get_indexes(table)}
    names |= {uc["name"] for uc in insp.get_unique_constraints(table)}
    return "uq_counter_office_code" in names


def upgrade() -> None:
    # Defensive like the previous migrations: ``create_all`` may have already
    # created the new columns/constraints before alembic was stamped, so every
    # step checks the live schema first.
    insp = inspect(op.get_bind())

    for column in (
        sa.Column("city", sa.String(80), nullable=False, server_default=""),
        sa.Column("state", sa.String(80), nullable=False, server_default=""),
        sa.Column("pincode", sa.String(12), nullable=False, server_default=""),
        sa.Column("contact_email", sa.String(160), nullable=False, server_default=""),
        sa.Column("contact_phone", sa.String(32), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("open_time", sa.String(5), nullable=False, server_default="09:30"),
        sa.Column("close_time", sa.String(5), nullable=False, server_default="18:00"),
    ):
        _add_column_if_missing(insp, "offices", column)

    insp = inspect(op.get_bind())
    _add_column_if_missing(insp, "counters", sa.Column("code", sa.String(40), nullable=True))
    _add_column_if_missing(insp, "counters", sa.Column("description", sa.String(300), nullable=False, server_default=""))
    if not _unique_code_index_exists(insp, "counters"):
        op.create_index("uq_counter_office_code", "counters", ["office_id", "code"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_counter_office_code", table_name="counters")
    op.drop_column("counters", "description")
    op.drop_column("counters", "code")
    for name in ("close_time", "open_time", "description", "contact_phone", "contact_email", "pincode", "state", "city"):
        op.drop_column("offices", name)
