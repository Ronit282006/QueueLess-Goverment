"""Smart arrival: office coordinates, travel metadata, no-show grace and reminders.

Revision ID: 20261010_geo_grace
Revises: 20261009_staff_management
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261010_geo_grace"
down_revision = "20261009_staff_management"
branch_labels = None
depends_on = None


def _add_column_if_missing(insp, table: str, column: sa.Column) -> None:
    existing = {c["name"] for c in insp.get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def _create_index_if_missing(insp, index_name: str, table: str, columns: list[str]) -> None:
    existing = {ix["name"] for ix in insp.get_indexes(table)}
    if index_name not in existing:
        op.create_index(index_name, table, columns)


def upgrade() -> None:
    # Written defensively (see the staff-management migration for the rationale):
    # the app may have bootstrapped tables via ``create_all`` before alembic was
    # stamped, so every step checks the live schema first. On a database created
    # normally by migrations these guards are harmless no-ops.
    insp = inspect(op.get_bind())

    # --- Office geo coordinates (nullable: offices without a pin are skipped) ---
    _add_column_if_missing(insp, "offices", sa.Column("latitude", sa.Float(), nullable=True))
    _add_column_if_missing(insp, "offices", sa.Column("longitude", sa.Float(), nullable=True))

    # --- Token travel metadata + no-show grace lifecycle ---
    _add_column_if_missing(insp, "tokens", sa.Column("travel_min", sa.Float(), nullable=True))
    _add_column_if_missing(insp, "tokens", sa.Column("travel_distance_km", sa.Float(), nullable=True))
    _add_column_if_missing(
        insp, "tokens", sa.Column("travel_mode", sa.String(20), nullable=False, server_default="")
    )
    _add_column_if_missing(
        insp, "tokens", sa.Column("travel_provider", sa.String(20), nullable=False, server_default="")
    )
    _add_column_if_missing(insp, "tokens", sa.Column("travel_calculated_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing(
        insp, "tokens", sa.Column("grace_state", sa.String(20), nullable=False, server_default="NOT_STARTED")
    )
    _add_column_if_missing(insp, "tokens", sa.Column("grace_started_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing(insp, "tokens", sa.Column("grace_deadline", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing(insp, "tokens", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing(
        insp, "tokens", sa.Column("cancellation_reason", sa.String(60), nullable=False, server_default="")
    )
    _create_index_if_missing(insp, "ix_tokens_grace_state", "tokens", ["grace_state"])
    _create_index_if_missing(insp, "ix_tokens_grace_deadline", "tokens", ["grace_deadline"])

    # --- Durably-scheduled arrival reminders ---
    if "scheduled_reminders" not in set(insp.get_table_names()):
        op.create_table(
            "scheduled_reminders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("token_id", sa.Integer(), sa.ForeignKey("tokens.id", ondelete="CASCADE"), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
            sa.Column("office_id", sa.Integer(), sa.ForeignKey("offices.id", ondelete="CASCADE"), nullable=True),
            sa.Column("kind", sa.String(40), nullable=False),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
            sa.Column("dedupe_key", sa.String(160), nullable=False),
            sa.Column("departure_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("eta_min", sa.Float(), nullable=True),
            sa.Column("travel_min", sa.Float(), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=False, server_default=""),
            sa.Column("last_error", sa.String(400), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("dedupe_key", name="uq_scheduled_reminder_dedupe_key"),
        )
        insp = inspect(op.get_bind())

    _create_index_if_missing(insp, "ix_scheduled_reminders_token_id", "scheduled_reminders", ["token_id"])
    _create_index_if_missing(insp, "ix_scheduled_reminders_user_id", "scheduled_reminders", ["user_id"])
    _create_index_if_missing(insp, "ix_scheduled_reminders_kind", "scheduled_reminders", ["kind"])
    _create_index_if_missing(insp, "ix_scheduled_reminders_due_at", "scheduled_reminders", ["due_at"])
    _create_index_if_missing(insp, "ix_scheduled_reminders_status", "scheduled_reminders", ["status"])
    _create_index_if_missing(insp, "ix_scheduled_reminders_created_at", "scheduled_reminders", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_reminders_created_at", table_name="scheduled_reminders")
    op.drop_index("ix_scheduled_reminders_status", table_name="scheduled_reminders")
    op.drop_index("ix_scheduled_reminders_due_at", table_name="scheduled_reminders")
    op.drop_index("ix_scheduled_reminders_kind", table_name="scheduled_reminders")
    op.drop_index("ix_scheduled_reminders_user_id", table_name="scheduled_reminders")
    op.drop_index("ix_scheduled_reminders_token_id", table_name="scheduled_reminders")
    op.drop_table("scheduled_reminders")

    op.drop_index("ix_tokens_grace_deadline", table_name="tokens")
    op.drop_index("ix_tokens_grace_state", table_name="tokens")
    op.drop_column("tokens", "cancellation_reason")
    op.drop_column("tokens", "cancelled_at")
    op.drop_column("tokens", "grace_deadline")
    op.drop_column("tokens", "grace_started_at")
    op.drop_column("tokens", "grace_state")
    op.drop_column("tokens", "travel_calculated_at")
    op.drop_column("tokens", "travel_provider")
    op.drop_column("tokens", "travel_mode")
    op.drop_column("tokens", "travel_distance_km")
    op.drop_column("tokens", "travel_min")

    op.drop_column("offices", "longitude")
    op.drop_column("offices", "latitude")
