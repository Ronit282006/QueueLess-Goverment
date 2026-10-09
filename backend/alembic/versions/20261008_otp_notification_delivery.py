"""OTP registration and resilient notification delivery.

Revision ID: 20261008_otp_delivery
Revises: 99fa593d94ff
"""
from alembic import op
import sqlalchemy as sa

revision = "20261008_otp_delivery"
down_revision = "99fa593d94ff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("notifications", "kind", type_=sa.String(length=40), existing_type=sa.String(length=30), existing_nullable=False)
    op.create_table(
        "email_otp_challenges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("tags", sa.String(255), nullable=False, server_default=""),
        sa.Column("otp_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("send_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("send_window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email", name="uq_email_otp_challenges_email"),
    )
    op.create_index("ix_email_otp_challenges_email", "email_otp_challenges", ["email"])
    op.add_column("notifications", sa.Column("dedupe_key", sa.String(160), nullable=True))
    op.add_column("notifications", sa.Column("sensitive", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("notifications", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_notification_dedupe_key", "notifications", ["dedupe_key"])


def downgrade() -> None:
    op.drop_constraint("uq_notification_dedupe_key", "notifications", type_="unique")
    op.drop_column("notifications", "next_attempt_at")
    op.drop_column("notifications", "sensitive")
    op.drop_column("notifications", "dedupe_key")
    op.alter_column("notifications", "kind", type_=sa.String(length=30), existing_type=sa.String(length=40), existing_nullable=False)
    op.drop_index("ix_email_otp_challenges_email", table_name="email_otp_challenges")
    op.drop_table("email_otp_challenges")
