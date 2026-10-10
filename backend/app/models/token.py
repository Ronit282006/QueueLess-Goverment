"""Virtual tokens, their event history and the atomic number allocator."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    DateTime,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from .enums import TokenStage, TokenStatus
from .user import utcnow


class TokenSequence(Base):
    """Atomic per-(office, service) token number allocator.

    The row lock taken inside the issuing transaction guarantees two citizens
    requesting tokens at the same instant can never receive the same number.
    """

    __tablename__ = "token_sequences"
    __table_args__ = (UniqueConstraint("office_id", "service_id", name="uq_sequence_office_service"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), index=True)
    next_number: Mapped[int] = mapped_column(Integer, default=1)


class Token(Base):
    __tablename__ = "tokens"
    __table_args__ = (
        UniqueConstraint("office_id", "service_id", "number", name="uq_token_office_service_number"),
        UniqueConstraint("rescheduled_from_id", name="uq_token_rescheduled_from"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Opaque, revocable reference — the only value embedded in the QR code.
    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    number: Mapped[int] = mapped_column(Integer, index=True)
    label: Mapped[str] = mapped_column(String(20))  # e.g. Q-127

    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    counter_id: Mapped[int | None] = mapped_column(
        ForeignKey("counters.id", ondelete="SET NULL"), nullable=True
    )
    scheduled_for: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    rescheduled_from_id: Mapped[int | None] = mapped_column(ForeignKey("tokens.id", ondelete="SET NULL"), nullable=True)
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("office_incidents.id", ondelete="SET NULL"), nullable=True, index=True)
    incident_response_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    incident_response_status: Mapped[str] = mapped_column(String(20), default="")
    incident_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    incident_action_hash: Mapped[str] = mapped_column(String(64), default="")

    status: Mapped[str] = mapped_column(
        String(20), default=TokenStatus.WAITING.value, index=True
    )
    stage: Mapped[str] = mapped_column(String(20), default=TokenStage.SAFE.value)
    # Configurable priority boost obtained from office priority rules (0 = normal).
    priority_rank: Mapped[int] = mapped_column(Integer, default=0)
    fairness_score: Mapped[float] = mapped_column(Float, default=100.0)
    deferrals: Mapped[int] = mapped_column(Integer, default=0)
    no_show_count: Mapped[int] = mapped_column(Integer, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=0)  # arrival sequence for FIFO tie-break

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow, index=True
    )
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Smart arrival: routing estimate captured when the citizen shared a location ---
    travel_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    travel_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    travel_mode: Mapped[str] = mapped_column(String(20), default="")
    travel_provider: Mapped[str] = mapped_column(String(20), default="")
    travel_calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Automatic no-show grace window (starts when the previous token completes) ---
    grace_state: Mapped[str] = mapped_column(String(20), default="NOT_STARTED", index=True)
    grace_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grace_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str] = mapped_column(String(60), default="")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    events: Mapped[list[TokenEvent]] = relationship(
        back_populates="token", cascade="all, delete-orphan", order_by="TokenEvent.created_at"
    )


class TokenEvent(Base):
    """Immutable record of every state transition (audit trail for a token)."""

    __tablename__ = "token_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_id: Mapped[int] = mapped_column(
        ForeignKey("tokens.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str] = mapped_column(String(20), default="")
    to_status: Mapped[str] = mapped_column(String(20), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(20), default="SYSTEM")
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow, index=True
    )

    token: Mapped[Token] = relationship(back_populates="events")
