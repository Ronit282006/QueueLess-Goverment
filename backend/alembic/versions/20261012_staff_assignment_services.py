"""Per-assignment service scope for staff.

Adds ``staff_assignment_services``: an optional list of services a staff member
may serve at an assigned counter. No rows for an assignment means the member is
unrestricted and may serve every service the counter handles (backward compatible).

Revision ID: 20261012_staff_svc_scope
Revises: 20261011_office_admin
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261012_staff_svc_scope"
down_revision = "20261011_office_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "staff_assignment_services" in insp.get_table_names():
        return

    op.create_table(
        "staff_assignment_services",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "assignment_id",
            sa.Integer(),
            sa.ForeignKey("staff_assignments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "service_id",
            sa.Integer(),
            sa.ForeignKey("services.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("assignment_id", "service_id", name="uq_staff_assignment_service"),
    )
    op.create_index(
        "ix_staff_assignment_services_assignment_id",
        "staff_assignment_services",
        ["assignment_id"],
    )
    op.create_index(
        "ix_staff_assignment_services_service_id",
        "staff_assignment_services",
        ["service_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_staff_assignment_services_service_id", table_name="staff_assignment_services")
    op.drop_index("ix_staff_assignment_services_assignment_id", table_name="staff_assignment_services")
    op.drop_table("staff_assignment_services")
