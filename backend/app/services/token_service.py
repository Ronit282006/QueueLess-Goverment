"""Token state machine and the atomic token-number allocator."""
from __future__ import annotations

import secrets
import threading
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..errors import ApiException
from ..models import Token, TokenEvent, TokenSequence, TokenStatus
from ..models.enums import TokenStage

# ---------------------------------------------------------------------------
# State machine (spec section 10)
# ---------------------------------------------------------------------------
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    TokenStatus.CREATED.value: {TokenStatus.WAITING.value, TokenStatus.CANCELLED.value},
    TokenStatus.WAITING.value: {
        TokenStatus.APPROACHING.value,
        TokenStatus.ARRIVED.value,
        TokenStatus.CALLED.value,
        TokenStatus.SKIPPED.value,
        TokenStatus.CANCELLED.value,
        TokenStatus.EXPIRED.value,
        TokenStatus.RESCHEDULED.value,
    },
    TokenStatus.APPROACHING.value: {
        TokenStatus.ARRIVED.value,
        TokenStatus.CALLED.value,
        TokenStatus.SKIPPED.value,
        TokenStatus.CANCELLED.value,
        TokenStatus.EXPIRED.value,
        TokenStatus.RESCHEDULED.value,
    },
    TokenStatus.ARRIVED.value: {
        TokenStatus.CALLED.value,
        TokenStatus.SKIPPED.value,
        TokenStatus.CANCELLED.value,
        TokenStatus.RESCHEDULED.value,
    },
    TokenStatus.CALLED.value: {
        TokenStatus.SERVING.value,
        TokenStatus.SKIPPED.value,
        TokenStatus.EXPIRED.value,
    },
    TokenStatus.SERVING.value: {TokenStatus.COMPLETED.value},
    TokenStatus.SKIPPED.value: {TokenStatus.WAITING.value},  # configurable rejoin
    TokenStatus.COMPLETED.value: set(),
    TokenStatus.CANCELLED.value: set(),
    TokenStatus.EXPIRED.value: set(),
}

ACTIVE_STATUSES = (
    TokenStatus.WAITING.value,
    TokenStatus.APPROACHING.value,
    TokenStatus.ARRIVED.value,
    TokenStatus.CALLED.value,
    TokenStatus.SERVING.value,
)

_TIMESTAMP_FIELD = {
    TokenStatus.ARRIVED.value: "arrived_at",
    TokenStatus.CALLED.value: "called_at",
    TokenStatus.SERVING.value: "started_at",
    TokenStatus.COMPLETED.value: "completed_at",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in ALLOWED_TRANSITIONS.get(from_status, set())


# ---------------------------------------------------------------------------
# Atomic allocation (spec section 35)
# ---------------------------------------------------------------------------
# SQLite ignores SELECT ... FOR UPDATE, so a process-local lock keeps the
# SQLite development/test path correct. PostgreSQL uses row-level locking.
_SQLITE_LOCK = threading.Lock()


def _dialect_name(db: Session) -> str:
    bind = db.get_bind()
    return bind.dialect.name if bind is not None else "sqlite"


def _select_for_update(db: Session, office_id: int, service_id: int) -> TokenSequence | None:
    stmt = (
        select(TokenSequence)
        .where(TokenSequence.office_id == office_id, TokenSequence.service_id == service_id)
        .with_for_update()
    )
    return db.scalar(stmt)


def allocate_token_number(db: Session, office_id: int, service_id: int) -> int:
    """Return the next number for this (office, service) queue — never twice.

    The sequence row is locked with SELECT ... FOR UPDATE inside the caller's
    transaction, so concurrent citizens are serialized by the database itself
    and receive unique, gap-free numbers.
    """
    lock = _SQLITE_LOCK if _dialect_name(db) == "sqlite" else None
    if lock is not None:
        lock.acquire()
    try:
        seq = _select_for_update(db, office_id, service_id)
        if seq is None:
            try:
                with db.begin_nested():
                    seq = TokenSequence(office_id=office_id, service_id=service_id, next_number=1)
                    db.add(seq)
                    db.flush()
            except IntegrityError:
                # Another request created it first — take the row lock and continue.
                seq = _select_for_update(db, office_id, service_id)
                if seq is None:  # pragma: no cover - defensive
                    raise ApiException(503, "sequence_unavailable", "Could not allocate a token number.")
        number = seq.next_number
        seq.next_number = number + 1
        db.flush()
        return number
    finally:
        if lock is not None:
            lock.release()


# ---------------------------------------------------------------------------
# Creation & transitions
# ---------------------------------------------------------------------------
def create_token(
    db: Session,
    *,
    office_id: int,
    service_id: int,
    user_id: int | None,
    priority_rank: int = 0,
) -> Token:
    number = allocate_token_number(db, office_id, service_id)
    token = Token(
        reference=secrets.token_urlsafe(18),
        number=number,
        label=f"Q-{number:03d}",
        office_id=office_id,
        service_id=service_id,
        user_id=user_id,
        status=TokenStatus.CREATED.value,
        stage=TokenStage.SAFE.value,
        priority_rank=priority_rank,
    )
    db.add(token)
    db.flush()
    record_event(db, token, from_status="", to_status=TokenStatus.CREATED.value, note="Virtual token created", actor_role="CITIZEN")
    # Created tokens immediately enter the waiting queue.
    apply_transition(db, token, TokenStatus.WAITING.value, note="Joined remote queue", actor_role="CITIZEN")
    return token


def apply_transition(
    db: Session,
    token: Token,
    to_status: str,
    *,
    note: str = "",
    actor_id: int | None = None,
    actor_role: str = "SYSTEM",
    counter_id: int | None = None,
    enforce: bool = True,
) -> Token:
    from_status = token.status
    if from_status == to_status:
        return token
    if enforce and to_status not in ALLOWED_TRANSITIONS.get(from_status, set()):
        raise ApiException(
            409,
            "invalid_transition",
            f"Token {token.label} cannot move from {from_status} to {to_status}.",
        )
    token.status = to_status
    if counter_id is not None:
        token.counter_id = counter_id
    field = _TIMESTAMP_FIELD.get(to_status)
    if field and getattr(token, field) is None:
        setattr(token, field, utcnow())
    if to_status == TokenStatus.WAITING.value and from_status == TokenStatus.SKIPPED.value:
        token.deferrals += 1
    db.flush()
    record_event(db, token, from_status=from_status, to_status=to_status, note=note, actor_id=actor_id, actor_role=actor_role)
    return token


def record_event(
    db: Session,
    token: Token,
    *,
    from_status: str,
    to_status: str,
    note: str = "",
    actor_id: int | None = None,
    actor_role: str = "SYSTEM",
) -> TokenEvent:
    event = TokenEvent(
        token_id=token.id,
        from_status=from_status,
        to_status=to_status,
        note=note,
        actor_id=actor_id,
        actor_role=actor_role,
    )
    db.add(event)
    db.flush()
    return event
