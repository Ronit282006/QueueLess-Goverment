"""Staff management: dedicated OTP challenges and unique staff→counter assignment.

Revision ID: 20261009_staff_management
Revises: 20261008_merge_heads
"""
from alembic import op
import sqlalchemy as sa

revision = "20261009_staff_management"
down_revision = "20261008_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_otp_challenges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("otp_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("send_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("send_window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email", name="uq_staff_otp_challenges_email"),
    )
    op.create_index("ix_staff_otp_challenges_email", "staff_otp_challenges", ["email"])

    # A staff member may not hold duplicate rows for the same counter: drop any
    # accidental duplicates (keeping the oldest) before the unique key applies.
    op.execute(
        "DELETE FROM staff_assignments WHERE id NOT IN "
        "(SELECT MIN(id) FROM staff_assignments GROUP BY user_id, counter_id)"
    )
    op.create_unique_constraint(
        "uq_staff_assignment_user_counter", "staff_assignments", ["user_id", "counter_id"]
    )
    op.add_column(
        "staff_assignments",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("staff_assignments", "updated_at")
    op.drop_constraint("uq_staff_assignment_user_counter", "staff_assignments", type_="unique")
    op.drop_index("ix_staff_otp_challenges_email", table_name="staff_otp_challenges")
    op.drop_table("staff_otp_challenges")