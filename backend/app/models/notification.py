"""Email notifications queued by the API and delivered by the background worker."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .enums import NotificationKind, NotificationStatus
from .user import utcnow


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_notification_dedupe_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    token_id: Mapped[int | None] = mapped_column(ForeignKey("tokens.id", ondelete="SET NULL"), index=True, nullable=True)
    office_id: Mapped[int | None] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    recipient: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(20), default=NotificationStatus.QUEUED.value, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(String(400), default="")
    dedupe_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now(), index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationLog(Base):
    """Delivery attempt history for transparency/debugging."""

    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str] = mapped_column(String(400), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now()
    )


class ScheduledReminder(Base):
    """A durably-scheduled reminder (e.g. "time to leave") delivered by the worker.

    Rows live in the database so a restart never loses or duplicates a reminder;
    ``dedupe_key`` guards against double-scheduling the same logical reminder.
    """

    __tablename__ = "scheduled_reminders"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_scheduled_reminder_dedupe_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    token_id: Mapped[int | None] = mapped_column(ForeignKey("tokens.id", ondelete="CASCADE"), index=True, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    office_id: Mapped[int | None] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    dedupe_key: Mapped[str] = mapped_column(String(160))
    # Planned departure point captured at schedule time so a later queue change can
    # be re-evaluated without re-asking the citizen for their location.
    departure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    eta_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    travel_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="")
    last_error: Mapped[str] = mapped_column(String(400), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def kind_value(kind: NotificationKind) -> str:
    return kind.value


def status_value(status: NotificationStatus) -> str:
    return status.value
