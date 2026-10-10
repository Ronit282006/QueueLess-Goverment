"""Smart arrival: office recommendations, departure guidance and reminders.

All travel figures come from :mod:`routing_service`; when a live route is not
available the APIs report that honestly instead of pretending straight-line
distance is road travel time.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..errors import ApiException
from ..models import Department, Office, ScheduledReminder, Service, Token, User
from ..models.enums import NotificationKind, ReminderStatus, TokenStatus
from . import notify_service, queue_service, routing_service, token_view
from .token_service import ACTIVE_STATUSES

logger = logging.getLogger("queueless.arrival")

DEPARTURE_REMINDER_KIND = "ARRIVAL_REMINDER"
# A queue-ETA change smaller than this does not justify rescheduling a reminder.
_RESCHEDULE_MIN_DELTA_MIN = 2.0

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


def _office_for_service(db: Session, service: Service) -> Office | None:
    department = service.department or db.get(Department, service.department_id)
    if department is None:
        return None
    return db.get(Office, department.office_id)


def _sibling_services(db: Session, service: Service) -> list[Service]:
    """Other offices offering the same service name.

    Matching is case- and whitespace-insensitive so an admin who adds a service
    to a new office (perhaps with slightly different casing) still shows up in
    the cross-office recommendations.
    """
    wanted = (service.name or "").strip().lower()
    return list(
        db.scalars(
            select(Service)
            .join(Department, Service.department_id == Department.id)
            .join(Office, Department.office_id == Office.id)
            .where(
                func.lower(func.trim(Service.name)) == wanted,
                Service.is_active.is_(True),
                Department.is_active.is_(True),
                Office.is_active.is_(True),
            )
            .order_by(Service.id)
        ).all()
    )


# ---------------------------------------------------------------------------
# Office recommendations
# ---------------------------------------------------------------------------
def _assess_selection(rows: list[dict], best: dict | None, selected_office_id: int) -> dict:
    """Explain whether a citizen-chosen office is the best option for them."""
    selected = next((r for r in rows if r["office_id"] == selected_office_id), None)
    if selected is None:
        return {
            "office_id": selected_office_id,
            "office_name": "",
            "offers_service": False,
            "is_best": False,
            "extra_min": None,
            "message": "This office does not offer the selected service.",
        }

    extra_min: int | None = None
    if (
        best is not None
        and selected.get("total_min") is not None
        and best.get("total_min") is not None
    ):
        extra_min = round(selected["total_min"] - best["total_min"])

    is_best = bool(selected.get("recommended"))
    if is_best:
        message = f"{selected['office_name']} is the best choice for you right now."
    elif selected.get("total_min") is None:
        message = (
            "We cannot compare travel time for this office yet — its location has not "
            "been set, so only the queue wait is known."
        )
    elif best is not None and extra_min is not None and extra_min > 0:
        message = (
            f"{best['office_name']} is currently about {extra_min} min better for you."
        )
    elif best is not None:
        message = f"{best['office_name']} may be a better choice right now."
    else:
        message = "This office offers the selected service."

    return {
        "office_id": selected_office_id,
        "office_name": selected["office_name"],
        "offers_service": True,
        "is_best": is_best,
        "extra_min": extra_min,
        "message": message,
    }


def recommend_offices(
    db: Session,
    service_id: int,
    origin: tuple[float, float],
    *,
    mode: str | None = None,
    selected_office_id: int | None = None,
    now: datetime | None = None,
) -> dict:
    settings = get_settings()
    service = db.get(Service, service_id)
    if service is None:
        raise ApiException(404, "not_found", "Service not found.")

    buffer_min = settings.departure_buffer_min
    rows: list[dict] = []
    for sibling in _sibling_services(db, service):
        office = _office_for_service(db, sibling)
        if office is None:
            continue
        eta = queue_service.service_eta(db, office.id, sibling.id)
        queue_wait = float(eta.get("eta_min") or 0)
        row: dict = {
            "office_id": office.id,
            "office_name": office.name,
            "office_address": office.address,
            "service_id": sibling.id,
            "queue_wait_min": round(queue_wait),
            "waiting": eta.get("waiting", 0),
            "active_counters": eta.get("active_counters", 0),
            "has_coordinates": routing_service.valid_coords(office.latitude, office.longitude),
            "travel": None,
            "total_min": None,
            "departure_in_min": None,
            "note": "",
        }
        if routing_service.valid_coords(office.latitude, office.longitude):
            route = routing_service.estimate_route(
                origin, (office.latitude, office.longitude), mode=mode
            )
            row["travel"] = route.as_dict()
            if route.available and route.duration_min is not None:
                row["total_min"] = round(route.duration_min + queue_wait + buffer_min)
                row["departure_in_min"] = max(
                    0, round(queue_wait - route.duration_min - buffer_min)
                )
        else:
            row["note"] = "Office location is not available yet."
        rows.append(row)

    rankable = [r for r in rows if r.get("total_min") is not None]
    rankable.sort(key=lambda r: (r["total_min"], r["queue_wait_min"], r["office_id"]))
    best = rankable[0] if rankable else None
    for row in rows:
        row["recommended"] = bool(best and row["office_id"] == best["office_id"])

    if best is not None:
        explanation = (
            f"{best['office_name']} looks best: about {best['travel']['duration_min']:.0f} min "
            f"travel plus roughly {best['queue_wait_min']} min queue wait "
            f"(with a {buffer_min} min buffer)."
        )
    elif rows:
        explanation = (
            "Live travel estimates are unavailable right now, so offices are ordered by "
            "queue wait. Please allow extra time for your journey."
        )
        rows.sort(key=lambda r: (r["queue_wait_min"], r["office_id"]))
    else:
        explanation = "No office currently offers this service."

    result = {
        "service": {"id": service.id, "name": service.name},
        "mode": routing_service.normalise_mode(mode),
        "safety_buffer_min": buffer_min,
        "routing": routing_service.provider_info(),
        "offices": rows,
        "best_office_id": best["office_id"] if best else None,
        "explanation": explanation,
        "selected": None,
        "assessment": None,
    }
    if selected_office_id is not None:
        result["assessment"] = _assess_selection(rows, best, selected_office_id)
        result["selected"] = next(
            (r for r in rows if r["office_id"] == selected_office_id), None
        )
    return result


# ---------------------------------------------------------------------------
# Departure guidance for a specific token
# ---------------------------------------------------------------------------
def departure_guidance(
    db: Session,
    token: Token,
    origin: tuple[float, float],
    *,
    mode: str | None = None,
    now: datetime | None = None,
) -> dict:
    settings = get_settings()
    now = _aware(now) or utcnow()
    office = db.get(Office, token.office_id)
    view = token_view.token_detail(db, token, include_qr=False)
    eta_min = int(view.get("eta_min") or 0)
    buffer_min = settings.departure_buffer_min

    result: dict = {
        "token_id": token.id,
        "token_label": token.label,
        "office_id": token.office_id,
        "office_name": office.name if office else "",
        "eta_min": eta_min,
        "safety_buffer_min": buffer_min,
        "mode": routing_service.normalise_mode(mode),
        "expected_service_at": (now + timedelta(minutes=eta_min)).isoformat(),
        "travel": None,
        "departure_at": None,
        "leave_in_min": None,
        "available": False,
        "message": "",
    }
    if office is None or not routing_service.valid_coords(office.latitude, office.longitude):
        result["message"] = "This office has no location set, so departure guidance is unavailable."
        return result

    route = routing_service.estimate_route(origin, (office.latitude, office.longitude), mode=mode)
    result["travel"] = route.as_dict()
    if not route.available or route.duration_min is None:
        result["message"] = route.message
        return result

    departure_at = (now + timedelta(minutes=eta_min)) - timedelta(
        minutes=route.duration_min + buffer_min
    )
    leave_in = int((departure_at - now).total_seconds() // 60)
    result.update(
        {
            "departure_at": departure_at.isoformat(),
            "leave_in_min": leave_in,
            "available": True,
        }
    )
    if leave_in > 0:
        result["message"] = (
            f"Leave in about {leave_in} min. The journey is roughly "
            f"{route.duration_min:.0f} min and your token is about {eta_min} min away "
            f"(including a {buffer_min} min buffer)."
        )
    else:
        result["message"] = (
            f"You should be on your way now — the journey is roughly {route.duration_min:.0f} min "
            f"and your token is about {eta_min} min away."
        )
    return result


# ---------------------------------------------------------------------------
# Durable reminders
# ---------------------------------------------------------------------------
def schedule_departure_reminder(
    db: Session,
    token: Token,
    origin: tuple[float, float],
    *,
    mode: str | None = None,
    now: datetime | None = None,
) -> ScheduledReminder | None:
    """Create or reschedule the "time to leave" reminder for a token.

    Upserts on a stable dedupe key so a changing queue ETA updates the existing
    row rather than stacking duplicates.
    """
    now = _aware(now) or utcnow()
    guidance = departure_guidance(db, token, origin, mode=mode, now=now)
    if not guidance["available"] or guidance["departure_at"] is None:
        return None
    departure_at = datetime.fromisoformat(guidance["departure_at"])
    dedupe_key = f"departure-reminder:{token.id}"
    payload = json.dumps(
        {
            "office_id": token.office_id,
            "eta_min": guidance["eta_min"],
            "travel_min": guidance["travel"]["duration_min"] if guidance["travel"] else None,
            "safety_buffer_min": guidance["safety_buffer_min"],
        }
    )
    existing = db.scalar(
        select(ScheduledReminder).where(ScheduledReminder.dedupe_key == dedupe_key)
    )
    if existing is None:
        reminder = ScheduledReminder(
            token_id=token.id,
            user_id=token.user_id,
            office_id=token.office_id,
            kind=DEPARTURE_REMINDER_KIND,
            due_at=departure_at,
            status=ReminderStatus.PENDING.value,
            dedupe_key=dedupe_key,
            departure_at=departure_at,
            eta_min=guidance["eta_min"],
            travel_min=guidance["travel"]["duration_min"] if guidance["travel"] else None,
            payload_json=payload,
        )
        db.add(reminder)
        db.flush()
        return reminder
    if existing.status != ReminderStatus.PENDING.value:
        return existing
    prior_due = _aware(existing.due_at)
    if prior_due is None or abs((departure_at - prior_due).total_seconds()) / 60.0 >= _RESCHEDULE_MIN_DELTA_MIN:
        existing.due_at = departure_at
        existing.departure_at = departure_at
        existing.eta_min = guidance["eta_min"]
        existing.travel_min = guidance["travel"]["duration_min"] if guidance["travel"] else None
        existing.payload_json = payload
        db.flush()
    return existing


def cancel_reminders(db: Session, token_id: int) -> int:
    rows = db.scalars(
        select(ScheduledReminder).where(
            ScheduledReminder.token_id == token_id,
            ScheduledReminder.status == ReminderStatus.PENDING.value,
        )
    ).all()
    count = 0
    for reminder in rows:
        reminder.status = ReminderStatus.CANCELLED.value
        count += 1
    if count:
        db.flush()
    return count


def _reminder_body(db: Session, token: Token, reminder: ScheduledReminder) -> str:
    office = db.get(Office, token.office_id)
    travel = reminder.travel_min if reminder.travel_min is not None else 0
    eta = reminder.eta_min if reminder.eta_min is not None else 0
    buffer_min = get_settings().departure_buffer_min
    link = f"{get_settings().frontend_base_url.rstrip('/')}?ticket={token.reference}"
    return (
        f"It's time to leave for {office.name if office else 'the office'}.\n\n"
        f"Your token {token.label} is expected to be served in about {round(eta)} minutes.\n"
        f"Estimated journey from your location: about {round(travel)} minutes.\n"
        f"With a {buffer_min}-minute arrival buffer, leaving now helps you arrive on time.\n\n"
        f"Track your queue live: {link}\n"
        "Travel and wait times are estimates and may change."
    )


def process_due_reminders(
    db: Session, *, now: datetime | None = None, limit: int = 50
) -> int:
    """Deliver every pending reminder whose departure time has arrived."""
    now = _aware(now) or utcnow()
    lock = _SQLITE_LOCK if _dialect(db) == "sqlite" else None
    if lock is not None:
        lock.acquire()
    try:
        stmt = (
            select(ScheduledReminder)
            .where(
                ScheduledReminder.status == ReminderStatus.PENDING.value,
                ScheduledReminder.due_at <= now,
            )
            .order_by(ScheduledReminder.due_at)
            .limit(limit)
        )
        if _dialect(db) != "sqlite":
            stmt = stmt.with_for_update(skip_locked=True)
        reminders = list(db.scalars(stmt).all())

        sent = 0
        for reminder in reminders:
            token = db.get(Token, reminder.token_id) if reminder.token_id else None
            stale = (
                token is None
                or token.status not in ACTIVE_STATUSES
                or token.arrived_at is not None
            )
            if stale:
                reminder.status = ReminderStatus.CANCELLED.value
                continue
            user = db.get(User, reminder.user_id) if reminder.user_id else None
            if user is not None and user.email:
                notify_service.enqueue(
                    db,
                    user=user,
                    token=token,
                    office_id=reminder.office_id,
                    kind=NotificationKind.ARRIVAL_REMINDER,
                    subject=f"Time to leave for token {token.label}",
                    body=_reminder_body(db, token, reminder),
                    dedupe_key=f"arrival-reminder:{token.id}",
                )
                sent += 1
            reminder.status = ReminderStatus.SENT.value
            reminder.sent_at = now
        db.commit()
        return sent
    finally:
        if lock is not None:
            lock.release()
