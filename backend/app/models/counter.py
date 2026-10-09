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
    __table_args__ = (UniqueConstraint("office_id", "number", name="uq_counter_office_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(80), default="")
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
    __tablename__ = "staff_assignments"

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
