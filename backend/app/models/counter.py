"""Service counters, counter↔service routing and staff assignments."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from .enums import CounterStatus
from .user import utcnow


class Counter(Base):
    __tablename__ = "counters"
    __table_args__ = (
        UniqueConstraint("office_id", "number", name="uq_counter_office_number"),
        UniqueConstraint("office_id", "code", name="uq_counter_office_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    # Human-readable code, unique within the office when provided (nullable).
    code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    name: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(20), default=CounterStatus.AVAILABLE.value, index=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # The token currently being served is derived from tokens.counter_id + status;
    # storing a second pointer here would create a circular foreign key.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    services: Mapped[list[CounterService]] = relationship(
        back_populates="counter", cascade="all, delete-orphan"
    )

    @property
    def is_serving(self) -> bool:
        return self.status in (CounterStatus.AVAILABLE.value, CounterStatus.BUSY.value)


class CounterService(Base):
    """Which services a counter can handle (changed by admin-accepted AI recommendations)."""

    __tablename__ = "counter_services"
    __table_args__ = (UniqueConstraint("counter_id", "service_id", name="uq_counter_service"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    counter_id: Mapped[int] = mapped_column(ForeignKey("counters.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), index=True)

    counter: Mapped[Counter] = relationship(back_populates="services")


class StaffAssignment(Base):
    """Active assignment of a staff member to a counter within an office.

    A staff member may hold several active rows (one per counter) so members
    can handle multiple counters. A counter may also be shared by more than one
    staff member; the de-facto concurrency rule is enforced at write time
    (only the assigned staff may operate the counter, and the counter busy
    state serialises call/start/complete). The (user, counter) pair is unique
    so two admins cannot create conflicting duplicate rows for the same member.
    """

    __tablename__ = "staff_assignments"
    __table_args__ = (UniqueConstraint("user_id", "counter_id", name="uq_staff_assignment_user_counter"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    counter_id: Mapped[int | None] = mapped_column(
        ForeignKey("counters.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(80), default="Service Officer")
    shift_start: Mapped[str] = mapped_column(String(10), default="09:30")
    shift_end: Mapped[str] = mapped_column(String(10), default="18:00")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    services: Mapped[list[StaffAssignmentService]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan"
    )


class StaffAssignmentService(Base):
    """Optional per-assignment service scope.

    When a row exists for an assignment, the staff member may only serve the
    listed services at that counter. When no rows exist, the assignment is
    unrestricted: the member may serve every service the counter handles.
    """

    __tablename__ = "staff_assignment_services"
    __table_args__ = (
        UniqueConstraint("assignment_id", "service_id", name="uq_staff_assignment_service"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("staff_assignments.id", ondelete="CASCADE"), index=True
    )
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), index=True)

    assignment: Mapped[StaffAssignment] = relationship(back_populates="services")
