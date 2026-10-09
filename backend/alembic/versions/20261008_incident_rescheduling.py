"""Office incidents, holidays and citizen incident responses.

Revision ID: 20261008_incident
Revises: 20261008_otp_delivery
"""
from alembic import op
import sqlalchemy as sa

revision = "20261008_incident"
down_revision = "20261008_otp_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("offices", sa.Column("location_instructions", sa.String(300), nullable=False, server_default=""))
    op.add_column("offices", sa.Column("arrival_buffer_min", sa.Integer(), nullable=False, server_default="15"))
    op.add_column("offices", sa.Column("incident_response_min", sa.Integer(), nullable=False, server_default="30"))
    op.alter_column("offices", "eta_alert_threshold_min", server_default="15", existing_type=sa.Integer(), existing_nullable=False)
    op.create_table(
        "office_holidays",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("office_id", sa.Integer(), sa.ForeignKey("offices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False, server_default="Office holiday"),
        sa.UniqueConstraint("office_id", "holiday_date", name="uq_office_holiday_date"),
    )
    op.create_index("ix_office_holidays_office_id", "office_holidays", ["office_id"])
    op.create_table(
        "office_incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("office_id", sa.Integer(), sa.ForeignKey("offices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("services.id", ondelete="SET NULL"), nullable=True),
        sa.Column("incident_type", sa.String(30), nullable=False, server_default="CAPACITY"),
        sa.Column("description", sa.String(400), nullable=False),
        sa.Column("location_instructions", sa.String(300), nullable=False, server_default=""),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_office_incidents_office_id", "office_incidents", ["office_id"])
    op.create_index("ix_office_incidents_status", "office_incidents", ["status"])
    op.add_column("tokens", sa.Column("scheduled_for", sa.Date(), nullable=True))
    op.add_column("tokens", sa.Column("rescheduled_from_id", sa.Integer(), sa.ForeignKey("tokens.id", ondelete="SET NULL"), nullable=True))
    op.add_column("tokens", sa.Column("incident_id", sa.Integer(), sa.ForeignKey("office_incidents.id", ondelete="SET NULL"), nullable=True))
    op.add_column("tokens", sa.Column("incident_response_due", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tokens", sa.Column("incident_response_status", sa.String(20), nullable=False, server_default=""))
    op.add_column("tokens", sa.Column("incident_notified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tokens", sa.Column("incident_action_hash", sa.String(64), nullable=False, server_default=""))
    op.create_index("ix_tokens_scheduled_for", "tokens", ["scheduled_for"])
    op.create_index("ix_tokens_incident_id", "tokens", ["incident_id"])
    op.create_unique_constraint("uq_token_rescheduled_from", "tokens", ["rescheduled_from_id"])


def downgrade() -> None:
    op.drop_constraint("uq_token_rescheduled_from", "tokens", type_="unique")
    op.drop_index("ix_tokens_incident_id", table_name="tokens")
    op.drop_index("ix_tokens_scheduled_for", table_name="tokens")
    for name in ("incident_action_hash", "incident_notified_at", "incident_response_status", "incident_response_due", "incident_id", "rescheduled_from_id", "scheduled_for"):
        op.drop_column("tokens", name)
    op.drop_index("ix_office_incidents_status", table_name="office_incidents")
    op.drop_index("ix_office_incidents_office_id", table_name="office_incidents")
    op.drop_table("office_incidents")
    op.drop_index("ix_office_holidays_office_id", table_name="office_holidays")
    op.drop_table("office_holidays")
    op.drop_column("offices", "incident_response_min")
    op.drop_column("offices", "arrival_buffer_min")
    op.drop_column("offices", "location_instructions")
    op.alter_column("offices", "eta_alert_threshold_min", server_default="10", existing_type=sa.Integer(), existing_nullable=False)
