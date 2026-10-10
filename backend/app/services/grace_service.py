"""Automatic no-show grace period after the previous token completes service.

Flow
----
1. A staff member completes the token being served at a counter.
2. :func:`start_grace_for_next` finds the next eligible token in that queue.
   If it has *not* checked in, a durable grace window starts (default 300s).
3. If the citizen checks in, the window is closed as ``ARRIVED`` (done inside
   ``token_service.apply_transition``).
4. If the window elapses, :func:`expire_due_grace` atomically cancels the token
   with reason ``NO_SHOW_GRACE_PERIOD_EXPIRED`` and notifies the citizen.

The timer is *never* started when a token is merely called; it only starts when
the previous token completes. All times accept an explicit ``now`` so tests can
advance a controllable clock instead of sleeping.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Token, User
from ..models.enums import GraceState, NotificationKind, TokenStatus
from . import notify_service, queue_service
from .token_service import apply_transition

logger = logging.getLogger("queueless.grace")

CANCELLATION_REASON = "NO_SHOW_GRACE_PERIOD_EXPIRED"

_SQLITE_LOCK = threading.Lock()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _dialect(db: Session) -> str:
    bind = db.get_bind()
    return bind.dialect.name if bind is not None else "sqlite"


def grace_seconds() -> int:
    return max(1, int(get_settings().grace_period_seconds))


def next_eligible(db: Session, office_id: int, service_id: int) -> Token | None:
    """The token that would be served next (present citizens first, then FIFO)."""
    ordered = queue_service.queue_for_service(db, office_id, service_id)
    eligible = [t for t in ordered if t.status != TokenStatus.SERVING.value]
    if not eligible:
        return None
    arrived = [t for t in eligible if t.status == TokenStatus.ARRIVED.value]
    if arrived:
        return arrived[0]
    waiting = [
        t for t in eligible
        if t.status in (TokenStatus.WAITING.value, TokenStatus.APPROACHING.value)
    ]
    return waiting[0] if waiting else None


def start_grace_for_next(
    db: Session, completed: Token, *, now: datetime | None = None
) -> Token | None:
    """Start the grace window on the next un-checked-in token, if any."""
    now = _aware(now) or utcnow()
    candidate = next_eligible(db, completed.office_id, completed.service_id)
    if candidate is None:
        return None
    if candidate.id == completed.id:
        return None
    if candidate.arrived_at is not None or candidate.status in (
        TokenStatus.ARRIVED.value,
        TokenStatus.CALLED.value,
        TokenStatus.SERVING.value,
    ):
        return None
    if candidate.status not in (TokenStatus.WAITING.value, TokenStatus.APPROACHING.value):
        return None
    candidate.grace_state = GraceState.ACTIVE.value
    candidate.grace_started_at = now
    candidate.grace_deadline = now + timedelta(seconds=grace_seconds())
    candidate.cancellation_reason = ""
    db.flush()
    logger.info("grace started for token=%s deadline=%s", candidate.label, candidate.grace_deadline)
    return candidate


def grace_view(token: Token, *, now: datetime | None = None) -> dict:
    """Serialise the grace window for staff/citizen dashboards."""
    now = _aware(now) or utcnow()
    deadline = _aware(token.grace_deadline)
    remaining = None
    if deadline is not None:
        remaining = max(0, int((deadline - now).total_seconds()))
    return {
        "state": token.grace_state or GraceState.NOT_STARTED.value,
        "started_at": _aware(token.grace_started_at).isoformat() if token.grace_started_at else None,
        "deadline": deadline.isoformat() if deadline else None,
        "remaining_sec": remaining,
        "grace_period_sec": grace_seconds(),
        "arrived": token.arrived_at is not None,
    }


def expire_due_grace(
    db: Session, *, now: datetime | None = None, limit: int = 50
) -> list[dict]:
    """Cancel every active grace window whose deadline has passed.

    Returns a small descriptor per cancelled token so callers can broadcast.
    Idempotent: a token already cancelled/arrived in another worker is skipped.
    """
    now = _aware(now) or utcnow()
    lock = _SQLITE_LOCK if _dialect(db) == "sqlite" else None
    if lock is not None:
        lock.acquire()
    try:
        stmt = (
            select(Token)
            .where(
                Token.grace_state == GraceState.ACTIVE.value,
                Token.grace_deadline.is_not(None),
                Token.grace_deadline <= now,
                Token.arrived_at.is_(None),
            )
            .order_by(Token.grace_deadline)
            .limit(limit)
        )
        if _dialect(db) != "sqlite":
            stmt = stmt.with_for_update(skip_locked=True)
        tokens = list(db.scalars(stmt).all())

        cancelled: list[dict] = []
        for token in tokens:
            # Re-check under the lock: another worker may have changed it.
            if token.grace_state != GraceState.ACTIVE.value or token.arrived_at is not None:
                continue
            if token.status not in (TokenStatus.WAITING.value, TokenStatus.APPROACHING.value):
                # Staff already called/served it — stop the timer, leave handling
                # to the normal flow.
                token.grace_state = GraceState.CANCELLED.value
                continue
            _cancel_token(db, token, now)
            cancelled.append(
                {
                    "id": token.id,
                    "reference": token.reference,
                    "label": token.label,
                    "office_id": token.office_id,
                    "service_id": token.service_id,
                }
            )
        db.commit()
        if cancelled:
            logger.info("auto-cancelled %d no-show token(s)", len(cancelled))
        return cancelled
    finally:
        if lock is not None:
            lock.release()


def _cancel_token(db: Session, token: Token, now: datetime) -> None:
    apply_transition(
        db,
        token,
        TokenStatus.CANCELLED.value,
        note="Auto-cancelled: no check-in within the grace period",
        actor_role="SYSTEM",
        enforce=False,
    )
    token.grace_state = GraceState.EXPIRED.value
    token.cancelled_at = now
    token.cancellation_reason = CANCELLATION_REASON
    token.no_show_count = (token.no_show_count or 0) + 1
    if token.user_id:
        user = db.get(User, token.user_id)
        if user is not None:
            minutes = max(1, round(grace_seconds() / 60))
            notify_service.enqueue(
                db,
                user=user,
                token=token,
                office_id=token.office_id,
                kind=NotificationKind.TOKEN_CANCELLED,
                subject=f"Token {token.label} cancelled",
                body=(
                    f"Your token {token.label} was automatically cancelled because you did not "
                    f"check in within {minutes} minutes after the previous token's service completed. "
                    "If you still need service, please book a new token in the app."
                ),
                dedupe_key=f"grace-cancel:{token.id}",
            )
    # Cancel any pending arrival reminders for a token that no longer applies.
    try:
        from . import arrival_service

        arrival_service.cancel_reminders(db, token.id)
    except Exception:  # pragma: no cover - reminders are non-critical
        logger.warning("could not cancel reminders for token %s", token.id)
