"""Short-lived email verification challenges for registration and staff creation."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class EmailOTPChallenge(Base):
    __tablename__ = "email_otp_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    tags: Mapped[str] = mapped_column(String(255), default="")
    otp_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    send_count: Mapped[int] = mapped_column(Integer, default=1)
    send_window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StaffOTPChallenge(Base):
    """Admin-initiated OTP challenge for creating a STAFF account.

    The challenge is deliberately a dedicated table (not the citizen
    registration table) and is bound to the email it was created for: the OTP
    is authenticated against ``(email, otp)`` and only the email that received
    the code can later be turned into a staff account. It stores only a secure
    hash of the OTP plus a bcrypt hash of the intended password, never
    plaintext. Staff accounts are created after successful verification and
    this row is deleted the moment the account exists.
    """

    __tablename__ = "staff_otp_challenges"

    purpose: str = "STAFF_CREATION"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    otp_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    send_count: Mapped[int] = mapped_column(Integer, default=1)
    send_window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now()
    )
