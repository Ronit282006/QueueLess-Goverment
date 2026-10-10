"""Background workers: email delivery, no-show sweeping and smart-stage refresh.

These loops run inside the API process (started in the lifespan) and are safe on
every instance: the email queue is a Redis list (competing consumers) and the
sweeper/stage work is idempotent. Every core step is a plain sync function so it
can be unit-tested without the event loop.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import smtplib
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal
from .models import Notification, NotificationLog, Office, Token, TokenStatus, User
from .models.enums import GraceState, NotificationKind, NotificationStatus, TokenStage
from .services import (
    arrival_service,
    audit_service,
    grace_service,
    prediction_service,
    queue_service,
    token_service,
    token_view,
)
from .services.cache_service import get_redis, publish
from .services.email_templates import render_email_html
from .services.notify_service import EMAIL_QUEUE_KEY, enqueue

logger = logging.getLogger("queueless.worker")

CHANNEL_PREFIX = "ql:events"

_EMAIL_MAX_ATTEMPTS = 3
# One SMTP session is cheap; a transient socket refusal (Windows firewall,
# antivirus, flaky network) usually clears within a second, so retry inside the
# delivery attempt instead of parking the message on a 30s backoff.
_SMTP_INLINE_ATTEMPTS = 3
_SMTP_TRANSIENT_ERRORS = (
    ConnectionError,
    TimeoutError,
    OSError,
    smtplib.SMTPConnectError,
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPDataError,
    smtplib.SMTPResponseException,
)
# Retries before the message is parked: 5s, 15s, 45s.
_RETRY_DELAY_SEC = (5, 15, 45)
_STAGE_ORDER = {
    TokenStage.SAFE.value: 0,
    TokenStage.APPROACHING.value: 1,
    TokenStage.COME_NOW.value: 2,
    TokenStage.YOUR_TURN.value: 3,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def publish_queue_update(office_id: int, service_id: int) -> None:
    """Broadcast a queue change from worker (sync) code via Redis pub/sub."""
    publish(
        f"{CHANNEL_PREFIX}:queue:{office_id}:{service_id}",
        json.dumps({"type": "queue.updated", "service_id": service_id, "office_id": office_id}),
    )


def publish_token_update(reference: str, view: dict | None = None) -> None:
    """Broadcast a single-token change (e.g. auto-cancellation) to its room."""
    payload: dict = {"type": "token.updated", "reference": reference}
    if view is not None:
        payload["token"] = view
    publish(f"{CHANNEL_PREFIX}:token:{reference}", json.dumps(payload, default=str))


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------
def _sender_address(settings) -> str:
    """Envelope sender; fall back to the authenticated user when unset/placeholder."""
    sender = (settings.smtp_from or "").strip()
    if not sender or "@" not in sender or sender.lower().endswith(".local"):
        sender = (settings.smtp_username or "").strip()
    return sender


def _build_message(recipient: str, subject: str, body: str, sender: str, qr_reference: str | None) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr(("QueueLess", sender))
    message["To"] = recipient
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    # Spam filters treat mail without a Message-ID as suspicious.
    message["Message-ID"] = make_msgid(domain=sender.split("@")[-1] or "queueless.local")
    message.set_content(body)
    # Send multipart/alternative: the plain text body stays the source of truth
    # (tests, logs, screen readers) while clients render the formatted HTML.
    message.add_alternative(render_email_html(subject, body), subtype="html")
    if qr_reference:
        from .services.qr_service import qr_data_url

        image = base64.b64decode(qr_data_url(qr_reference).split(",", 1)[1])
        message.add_attachment(image, maintype="image", subtype="png", filename="queueless-ticket.png")
    return message


def send_email(recipient: str, subject: str, body: str, *, sensitive: bool = False, qr_reference: str | None = None) -> bool:
    settings = get_settings()
    if settings.email_mode != "smtp" or not settings.smtp_host:
        if sensitive and settings.environment.lower() == "production":
            logger.info("[email:log] to=%s subject=%s body=[redacted]", recipient, subject)
        else:
            logger.info("[email:log] to=%s subject=%s body=%s", recipient, subject, body)
        return False
    recipient = (recipient or "").strip()
    if recipient.count("@") != 1 or not recipient.split("@", 1)[0]:
        raise ValueError(f"Refusing to send to malformed recipient {recipient!r}")
    sender = _sender_address(settings)
    if not sender:
        raise ValueError("SMTP is enabled but neither SMTP_FROM nor SMTP_USERNAME is set.")
    message = _build_message(recipient, subject, body, sender, qr_reference)

    smtp_type = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
    for attempt in range(1, _SMTP_INLINE_ATTEMPTS + 1):
        try:
            with smtp_type(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                if settings.smtp_use_starttls and not settings.smtp_use_ssl:
                    smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username.strip(), "".join(settings.smtp_password.split()))
                refused = smtp.send_message(message)
                if refused:
                    raise smtplib.SMTPRecipientsRefused(refused)
            return True
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPSenderRefused, smtplib.SMTPRecipientsRefused):
            raise  # configuration/recipient problem: retrying cannot help
        except _SMTP_TRANSIENT_ERRORS as exc:
            if attempt >= _SMTP_INLINE_ATTEMPTS:
                raise
            logger.warning(
                "smtp attempt %s/%s to %s failed (%s: %s); retrying",
                attempt, _SMTP_INLINE_ATTEMPTS, recipient, type(exc).__name__, exc,
            )
            time.sleep(float(attempt))
    raise RuntimeError("unreachable")  # pragma: no cover


def _deliver(db: Session, notification: Notification) -> bool:
    notification.attempts += 1
    try:
        token = db.get(Token, notification.token_id) if notification.token_id else None
        delivered = send_email(
            notification.recipient, notification.subject, notification.body,
            sensitive=notification.sensitive,
            qr_reference=token.reference if token and notification.kind in (
                NotificationKind.TOKEN_CREATED.value, NotificationKind.TOKEN_TRANSFERRED.value
            ) else None,
        )
        notification.status = (
            NotificationStatus.SENT.value if delivered else NotificationStatus.LOGGED.value
        )
        notification.last_error = ""
        notification.sent_at = utcnow() if delivered else None
        notification.next_attempt_at = None
        # Only destroy the body once the provider actually accepted it; in log
        # mode the body is the only place a developer can read the OTP.
        if notification.sensitive and delivered:
            notification.body = "[redacted after delivery]"
        db.add(
            NotificationLog(
                notification_id=notification.id,
                attempt=notification.attempts,
                status="SENT" if delivered else "LOGGED",
                detail="" if delivered else "Demo email mode: event logged locally; no email was sent.",
            )
        )
        return True
    except Exception as exc:  # pragma: no cover - depends on SMTP
        safe_error = "Sensitive email delivery failed." if notification.sensitive else str(exc)[:400]
        notification.last_error = safe_error
        notification.status = (
            NotificationStatus.FAILED.value
            if notification.attempts >= _EMAIL_MAX_ATTEMPTS
            else NotificationStatus.QUEUED.value
        )
        notification.next_attempt_at = (
            utcnow() + timedelta(seconds=_RETRY_DELAY_SEC[min(len(_RETRY_DELAY_SEC), notification.attempts) - 1])
            if notification.status == NotificationStatus.QUEUED.value else None
        )
        db.add(
            NotificationLog(
                notification_id=notification.id,
                attempt=notification.attempts,
                status="FAILED",
                detail=safe_error,
            )
        )
        return False


def _queued_ids(limit: int) -> list[int]:
    """Atomically dequeue notification ids from Redis (empty when Redis is down).

    ``LPOP`` with a count is a single atomic command, so competing workers can
    never claim the same id — the old LRANGE+LTRIM pair let two instances
    deliver the same message twice.
    """
    client = get_redis()
    if client is None:
        return []
    try:
        raw_ids = client.lpop(EMAIL_QUEUE_KEY, limit)
    except Exception:  # pragma: no cover - redis optional
        return []
    if not raw_ids:
        return []
    if isinstance(raw_ids, (bytes, str)):
        raw_ids = [raw_ids]
    ids: list[int] = []
    for raw in raw_ids:
        try:
            ids.append(int(json.loads(raw)["notification_id"]))
        except Exception:
            continue
    return ids


def process_pending(limit: int = 25) -> int:
    """Deliver queued notifications; fall back to scanning the DB when Redis is down.

    Both queries take ``FOR UPDATE SKIP LOCKED`` rows so concurrent workers hold
    disjoint claims for the whole deliver-then-commit window.
    """
    db = SessionLocal()
    try:
        now = utcnow()
        ids = _queued_ids(limit)
        if ids:
            by_id = {
                n.id: n
                for n in db.scalars(
                    select(Notification)
                    .where(Notification.id.in_(ids), Notification.status == NotificationStatus.QUEUED.value)
                    .with_for_update(skip_locked=True)
                ).all()
            }
            pending = []
            for notification_id in ids:
                notification = by_id.get(notification_id)
                if notification is None:
                    continue
                due_at = notification.next_attempt_at
                if due_at is None or (due_at.replace(tzinfo=timezone.utc) if due_at.tzinfo is None else due_at) <= now:
                    pending.append(notification)
        else:
            pending = list(
                db.scalars(
                    select(Notification)
                    .where(
                        Notification.status == NotificationStatus.QUEUED.value,
                        (Notification.next_attempt_at.is_(None)) | (Notification.next_attempt_at <= now),
                    )
                    .order_by(Notification.created_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                ).all()
            )
        delivered = 0
        for notification in pending:
            if _deliver(db, notification):
                delivered += 1
        db.commit()
        return delivered
    finally:
        db.close()


async def email_worker_loop(poll_seconds: float = 1.5) -> None:
    while True:
        try:
            delivered = await asyncio.to_thread(process_pending)
        except asyncio.CancelledError:
            break
        except Exception:  # pragma: no cover - defensive
            logger.exception("email worker iteration failed")
            delivered = 0
        if delivered == 0:
            await asyncio.sleep(poll_seconds)


# ---------------------------------------------------------------------------
# No-show sweeper
# ---------------------------------------------------------------------------
def sweep_no_shows(db: Session) -> int:
    """Expire tokens that were called but never arrived within the grace window."""
    now = utcnow()
    called = list(
        db.scalars(
            select(Token).where(
                Token.status == TokenStatus.CALLED.value, Token.called_at.is_not(None)
            )
        ).all()
    )
    expired = 0
    for token in called:
        # A token inside the post-completion grace window is owned by
        # grace_service; do not double-handle it here.
        if token.grace_state == GraceState.ACTIVE.value:
            continue
        office = db.get(Office, token.office_id)
        grace = office.no_show_grace_min if office else get_settings().no_show_grace_min
        called_at = token.called_at
        if called_at is not None and called_at.tzinfo is None:
            called_at = called_at.replace(tzinfo=timezone.utc)
        if called_at is not None and now - called_at > timedelta(minutes=grace):
            token.no_show_count += 1
            token_service.apply_transition(
                db,
                token,
                TokenStatus.SKIPPED.value,
                note="No-show: grace period elapsed",
                actor_role="SYSTEM",
            )
            if token.user_id:
                user = db.get(User, token.user_id)
                enqueue(
                    db,
                    user=user,
                    token=token,
                    office_id=token.office_id,
                    kind=NotificationKind.TOKEN_SKIPPED,
                    subject=f"Token {token.label}: you were marked as a no-show",
                    body="You did not arrive within the grace period. You can rejoin the queue if you are still coming.",
                    dedupe_key=f"token-no-show:{token.id}",
                )
            expired += 1
            publish_queue_update(token.office_id, token.service_id)
    return expired


# ---------------------------------------------------------------------------
# Smart come-to-office stages
# ---------------------------------------------------------------------------
def refresh_active_stages(db: Session) -> int:
    """Recompute the come-to-office stage for active tokens and notify on upgrades."""
    pairs = db.execute(
        select(Token.office_id, Token.service_id)
        .where(Token.status.in_(token_service.ACTIVE_STATUSES))
        .distinct()
    ).all()
    changed = 0
    for office_id, service_id in pairs:
        office = db.get(Office, office_id)
        tokens = queue_service.queue_for_service(db, office_id, service_id)
        counters = queue_service.available_counters(db, office_id, service_id)
        pair_changed = False
        for index, token in enumerate(tokens):
            position = index + 1
            ahead = sum(1 for t in tokens[:index] if t.status != TokenStatus.SERVING.value)
            eta_min = 0.0
            eta_low = eta_high = 0.0
            if token.status in (TokenStatus.CALLED.value, TokenStatus.SERVING.value):
                new_stage = TokenStage.YOUR_TURN.value
            else:
                pred = prediction_service.predict(
                    db,
                    office_id=office_id,
                    service_id=service_id,
                    people_ahead=ahead,
                    active_counters=len(counters),
                )
                eta_min = pred.minutes
                eta_low, eta_high = pred.low, pred.high
                new_stage = queue_service.stage_for(token, pred.minutes, position, office.eta_alert_threshold_min if office else 15)
            old_stage = token.stage
            if new_stage == old_stage:
                continue
            token.stage = new_stage
            changed += 1
            pair_changed = True
            if _STAGE_ORDER.get(new_stage, 0) > _STAGE_ORDER.get(old_stage, 0):
                _notify_stage(db, token, new_stage, eta_min, eta_low, eta_high)
        if pair_changed:
            publish_queue_update(office_id, service_id)
    return changed


def _notify_stage(
    db: Session, token: Token, stage: str, eta_min: float = 0.0,
    eta_low: float = 0.0, eta_high: float = 0.0,
) -> None:
    if not token.user_id:
        return
    user = db.get(User, token.user_id)
    if user is None:
        return
    office = db.get(Office, token.office_id)
    eta = max(0, round(eta_min))
    now = utcnow()
    turn_at = now + timedelta(minutes=eta)
    buffer_min = office.arrival_buffer_min if office else get_settings().arrival_buffer_min
    recommended_arrival = max(now, turn_at - timedelta(minutes=buffer_min))
    live_link = f"{get_settings().frontend_base_url.rstrip('/')}?ticket={token.reference}"
    details = (
        f"Current estimated turn: {max(0, round(eta_low))}–{max(0, round(eta_high))} minutes (likely around {turn_at.astimezone().strftime('%H:%M %Z')}).\n"
        f"Recommended arrival: by {recommended_arrival.astimezone().strftime('%H:%M %Z')} (arrival buffer: {buffer_min} minutes).\n"
        f"Office: {office.name if office else 'Government office'}\n"
        f"Address: {office.address if office else 'See the live ticket'}\n"
        f"Building/location directions: {office.location_instructions if office and office.location_instructions else 'See the live ticket'}\n"
        f"Counter/location instructions: check the live ticket page.\n"
        f"Predictions can change as the queue changes. {live_link}"
    )
    if stage == TokenStage.COME_NOW.value:
        enqueue(
            db,
            user=user,
            token=token,
            office_id=token.office_id,
            kind=NotificationKind.COME_TO_OFFICE,
            subject=f"Token {token.label}: please proceed to the office",
            body=f"Your turn is approaching. Please make your way to the office.\n\n{details}",
            dedupe_key=f"turn-approaching:{token.id}",
        )
    elif stage == TokenStage.APPROACHING.value:
        enqueue(
            db,
            user=user,
            token=token,
            office_id=token.office_id,
            kind=NotificationKind.QUEUE_APPROACHING,
            subject=f"Token {token.label}: your turn is approaching",
            body=f"Your position in the queue is getting close.\n\n{details}",
            dedupe_key=f"turn-approaching:{token.id}",
        )


def sweep_incident_deadlines(db: Session) -> dict[str, int]:
    """Apply disclosed timeout policy; preserve already-arrived citizens for staff review."""
    now = utcnow()
    pending = db.scalars(
        select(Token).where(
            Token.incident_response_status == "PENDING",
            Token.incident_response_due.is_not(None),
            Token.incident_response_due <= now,
        )
    ).all()
    cancelled = 0
    staff_review = 0
    for token in pending:
        user = db.get(User, token.user_id) if token.user_id else None
        incident_id = token.incident_id
        if token.status == TokenStatus.ARRIVED.value:
            token.incident_response_status = "STAFF_REVIEW"
            token.incident_action_hash = ""
            if user:
                enqueue(
                    db, user=user, token=token, office_id=token.office_id,
                    kind=NotificationKind.QUEUE_DELAY,
                    subject=f"Staff assistance needed for token {token.label}",
                    body="Your incident response deadline passed while you were checked in. Your place has been held; please speak with counter staff for transfer or rebooking.",
                    dedupe_key=f"incident-arrived-review:{incident_id}:{token.id}",
                )
            audit_service.record(
                db, action="incident.arrived_staff_review", actor_role="SYSTEM",
                entity_type="token", entity_id=token.id, office_id=token.office_id,
                detail={"incident_id": incident_id},
            )
            staff_review += 1
            continue
        if token.status not in (TokenStatus.WAITING.value, TokenStatus.APPROACHING.value):
            continue
        token_service.apply_transition(
            db, token, TokenStatus.CANCELLED.value,
            note="Incident response deadline passed without citizen approval", actor_role="SYSTEM",
        )
        token.incident_response_status = "TIMED_OUT"
        token.incident_action_hash = ""
        if user:
            enqueue(
                db, user=user, token=token, office_id=token.office_id,
                kind=NotificationKind.TOKEN_CANCELLED,
                subject=f"Token {token.label} cancelled after the response deadline",
                body="Your ticket was cancelled because no transfer or cancellation choice was received before the disclosed incident response deadline.",
                dedupe_key=f"incident-timeout-cancel:{incident_id}:{token.id}",
            )
        audit_service.record(
            db, action="incident.ticket_timed_out", actor_role="SYSTEM",
            entity_type="token", entity_id=token.id, office_id=token.office_id,
            detail={"incident_id": incident_id},
        )
        publish_queue_update(token.office_id, token.service_id)
        cancelled += 1
    return {"cancelled": cancelled, "staff_review": staff_review}


def sweep_grace_periods(db: Session) -> int:
    """Cancel tokens whose post-completion no-show grace window has elapsed."""
    cancelled = grace_service.expire_due_grace(db)
    for item in cancelled:
        token = db.get(Token, item["id"])
        view = token_view.token_detail(db, token, include_qr=False) if token else None
        publish_queue_update(item["office_id"], item["service_id"])
        publish_token_update(item["reference"], view)
    return len(cancelled)


def process_arrival_reminders(db: Session) -> int:
    """Deliver any "time to leave" reminders whose departure time has arrived."""
    return arrival_service.process_due_reminders(db)


def run_sweep_once() -> dict:
    db = SessionLocal()
    try:
        expired = sweep_no_shows(db)
        grace_cancelled = sweep_grace_periods(db)
        reminders_sent = process_arrival_reminders(db)
        changed = refresh_active_stages(db)
        incidents = sweep_incident_deadlines(db)
        db.commit()
        if expired or changed or grace_cancelled or reminders_sent:
            logger.info(
                "sweeper: expired=%s grace_cancelled=%s reminders=%s stages_changed=%s",
                expired, grace_cancelled, reminders_sent, changed,
            )
        return {
            "expired": expired,
            "grace_cancelled": grace_cancelled,
            "reminders_sent": reminders_sent,
            "stages_changed": changed,
            **incidents,
        }
    finally:
        db.close()


async def sweeper_loop(interval_seconds: int = 15) -> None:
    while True:
        try:
            await asyncio.to_thread(run_sweep_once)
        except asyncio.CancelledError:
            break
        except Exception:  # pragma: no cover - defensive
            logger.exception("sweeper iteration failed")
        await asyncio.sleep(interval_seconds)


async def main() -> None:
    """Run queue notifications and maintenance in the dedicated worker service."""
    settings = get_settings()
    await asyncio.gather(
        email_worker_loop(poll_seconds=settings.email_poll_sec),
        sweeper_loop(interval_seconds=settings.sweeper_interval_sec),
    )


if __name__ == "__main__":
    asyncio.run(main())
