"""Background worker tests (Phase 7): email delivery, no-show sweep, stages."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select


def _user_and_service(db):
    from app.models import Service, User
    from app.security import hash_password

    service = db.scalar(select(Service).limit(1))
    user = User(
        email=f"worker-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Worker Test",
        password_hash=hash_password("Sup3r-secret"),
        role="CITIZEN",
    )
    db.add(user)
    db.flush()
    return user, service


def test_email_worker_delivers_and_logs(app):
    from app.db import SessionLocal
    from app.models import Notification, NotificationLog
    from app.models.enums import NotificationKind, NotificationStatus
    from app.services import notify_service
    from app.worker import _deliver

    db = SessionLocal()
    try:
        user, service = _user_and_service(db)
        notification = notify_service.enqueue(
            db,
            user=user,
            token=None,
            office_id=service.department.office_id,
            kind=NotificationKind.TOKEN_CREATED,
            subject="Unit test subject",
            body="Unit test body",
        )
        db.commit()
        assert notification is not None and notification.status == NotificationStatus.QUEUED.value

        assert _deliver(db, notification) is True
        db.commit()

        db.refresh(notification)
        assert notification.status == NotificationStatus.LOGGED.value
        assert notification.sent_at is None
        logs = db.scalars(
            select(NotificationLog).where(NotificationLog.notification_id == notification.id)
        ).all()
        assert logs and logs[-1].status == "LOGGED"
        assert "no email was sent" in logs[-1].detail
    finally:
        db.close()


def test_email_retries_are_bounded_and_deduplicated(app, monkeypatch):
    from app.db import SessionLocal
    from app.models import Notification, NotificationLog
    from app.models.enums import NotificationKind, NotificationStatus
    from app.services.notify_service import enqueue_email
    from app.worker import _deliver, utcnow

    def fail_delivery(*args, **kwargs):
        raise TimeoutError("temporary provider timeout")

    monkeypatch.setattr("app.worker.send_email", fail_delivery)
    db = SessionLocal()
    try:
        first = enqueue_email(
            db, recipient=f"retry-{uuid.uuid4().hex[:8]}@example.com",
            subject="Retry test", body="Retry body", kind=NotificationKind.QUEUE_DELAY,
            dedupe_key=f"retry:{uuid.uuid4().hex}",
        )
        duplicate = enqueue_email(
            db, recipient=first.recipient, subject="Duplicate", body="Duplicate",
            kind=NotificationKind.QUEUE_DELAY, dedupe_key=first.dedupe_key,
        )
        assert duplicate.id == first.id
        db.commit()
        for attempt in range(3):
            assert _deliver(db, first) is False
            db.commit()
            db.refresh(first)
            if attempt < 2:
                first.next_attempt_at = utcnow() - timedelta(seconds=1)
                db.commit()
        assert first.attempts == 3
        assert first.status == NotificationStatus.FAILED.value
        logs = db.scalars(select(NotificationLog).where(NotificationLog.notification_id == first.id)).all()
        assert len(logs) == 3
        assert all(row.status == "FAILED" for row in logs)
    finally:
        db.close()


def test_no_show_sweeper_skips_overdue_token(app):
    from app.db import SessionLocal
    from app.models import Token, TokenStatus
    from app.services import token_service
    from app.worker import sweep_no_shows

    db = SessionLocal()
    try:
        user, service = _user_and_service(db)
        office_id = service.department.office_id
        token = token_service.create_token(db, office_id=office_id, service_id=service.id, user_id=user.id)
        token_service.apply_transition(db, token, TokenStatus.ARRIVED.value)
        token_service.apply_transition(db, token, TokenStatus.CALLED.value)
        token.called_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        db.commit()

        expired = sweep_no_shows(db)
        db.commit()
        assert expired >= 1
        db.refresh(token)
        assert token.status == TokenStatus.SKIPPED.value
        assert token.no_show_count >= 1
    finally:
        db.close()


def test_stage_refresh_assigns_smart_stage(app):
    from app.db import SessionLocal
    from app.models.enums import TokenStage
    from app.services import token_service
    from app.worker import refresh_active_stages

    db = SessionLocal()
    try:
        user, service = _user_and_service(db)
        office_id = service.department.office_id
        token = token_service.create_token(db, office_id=office_id, service_id=service.id, user_id=user.id)
        db.commit()

        refresh_active_stages(db)
        db.commit()
        db.refresh(token)
        assert token.stage in {s.value for s in TokenStage}
    finally:
        db.close()
