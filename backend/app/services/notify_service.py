"""Notification queueing. The API only records + enqueues; the worker delivers."""
from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Notification, Token, User
from ..models.enums import NotificationKind, NotificationStatus
from .cache_service import get_redis

logger = logging.getLogger("queueless.notify")

EMAIL_QUEUE_KEY = "ql:email:queue"


def enqueue(
    db: Session,
    *,
    user: User | None,
    token: Token | None,
    office_id: int | None,
    kind: NotificationKind,
    subject: str,
    body: str,
    dedupe_key: str | None = None,
    sensitive: bool = False,
) -> Notification | None:
    """Record a notification and push its id to the worker queue (never blocks email)."""
    if user is None or not user.email:
        return None
    return enqueue_email(
        db, recipient=user.email, subject=subject, body=body, user_id=user.id,
        token_id=token.id if token else None, office_id=office_id,
        kind=kind, dedupe_key=dedupe_key, sensitive=sensitive,
    )


def enqueue_email(
    db: Session,
    *,
    recipient: str,
    subject: str,
    body: str,
    kind: NotificationKind,
    user_id: int | None = None,
    token_id: int | None = None,
    office_id: int | None = None,
    dedupe_key: str | None = None,
    sensitive: bool = False,
) -> Notification:
    """Persist and enqueue an email without waiting for the provider."""
    if dedupe_key:
        existing = db.scalar(select(Notification).where(Notification.dedupe_key == dedupe_key))
        if existing is not None:
            return existing
    notification = Notification(
        user_id=user_id,
        token_id=token_id,
        office_id=office_id,
        kind=kind.value,
        subject=subject,
        body=body,
        recipient=recipient,
        status=NotificationStatus.QUEUED.value,
        dedupe_key=dedupe_key,
        sensitive=sensitive,
    )
    try:
        with db.begin_nested():
            db.add(notification)
            db.flush()
    except IntegrityError:
        if not dedupe_key:
            raise
        existing = db.scalar(select(Notification).where(Notification.dedupe_key == dedupe_key))
        if existing is None:
            raise
        return existing

    client = get_redis()
    if client is not None:
        try:
            client.rpush(EMAIL_QUEUE_KEY, json.dumps({"notification_id": notification.id}))
        except Exception:  # pragma: no cover - redis is optional
            logger.warning("could not enqueue email for notification %s", notification.id)
    return notification
