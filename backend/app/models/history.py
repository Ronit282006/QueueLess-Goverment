"""Historical queue/service observations used to train the prediction models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class QueueSnapshot(Base):
    """One observation of a service queue at a point in time."""

    __tablename__ = "queue_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    hour_of_day: Mapped[int] = mapped_column(Integer, index=True)
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0 = Monday
    queue_length: Mapped[int] = mapped_column(Integer)
    active_counters: Mapped[int] = mapped_column(Integer)
    avg_service_min: Mapped[float] = mapped_column(Float)
    avg_wait_min: Mapped[float] = mapped_column(Float)  # observed mean wait that period
    queue_speed_min: Mapped[float] = mapped_column(Float, default=0.0)  # min between completions
    no_show_rate: Mapped[float] = mapped_column(Float, default=0.0)
    priority_load: Mapped[int] = mapped_column(Integer, default=0)
    origin: Mapped[str] = mapped_column(String(10), default="DEMO")


class ServiceTimeRecord(Base):
    """A completed service duration — direct training signal for the model."""

    __tablename__ = "service_time_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_id: Mapped[int | None] = mapped_column(
        ForeignKey("tokens.id", ondelete="SET NULL"), nullable=True, index=True
    )
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), index=True)
    counter_id: Mapped[int | None] = mapped_column(
        ForeignKey("counters.id", ondelete="SET NULL"), nullable=True
    )
    duration_min: Mapped[float] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    origin: Mapped[str] = mapped_column(String(10), default="DEMO")
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now()
    )
