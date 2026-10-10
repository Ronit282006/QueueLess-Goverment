"""Staff operations: counters, calling the next token, serving and completion.

All actions are RBAC-guarded (STAFF or ADMIN), audited, and immediately
re-broadcast to citizens over WebSockets so their ETA refreshes in real time.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiException
from ..ml import model as ml_model
from ..models import (
    Counter,
    CounterService,
    CounterStatus,
    Office,
    Prediction,
    Service,
    ServiceTimeRecord,
    Token,
    TokenStatus,
    User,
)
from ..models.enums import DataOrigin, NotificationKind
from ..realtime import hub
from ..security import require_staff
from ..services import audit_service, notify_service, queue_service, token_service, token_view
from ..services.assignment_service import (
    assigned_counter_ids,
    assigned_office_ids,
    require_counter_assignment,
    require_office_scope,
)

router = APIRouter(prefix="/api/staff", tags=["Staff"], dependencies=[Depends(require_staff)])


def _room(office_id: int, service_id: int) -> str:
    return f"queue:{office_id}:{service_id}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def get_counter(db: Session, counter_id: int) -> Counter:
    counter = db.get(Counter, counter_id)
    if counter is None:
        raise ApiException(404, "not_found", "Counter not found.")
    return counter


class CounterStatusUpdate(BaseModel):
    status: str


class CounterAssignmentUpdate(BaseModel):
    service_ids: list[int] = Field(default_factory=list)


class CallNextRequest(BaseModel):
    service_id: int


@router.get("/scope")
def staff_scope(staff: User = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    """The offices and counters this member may work on, from their assignments.

    The frontend uses this to hide everything the member has not been assigned,
    and every counter-level action re-validates against the same table.
    """
    offices = assigned_office_ids(db, staff.id)
    counters = assigned_counter_ids(db, staff.id)
    return {
        "offices": offices,
        "counters": sorted(counters),
        "counters_by_office": {
            str(office_id): sorted(assigned_counter_ids(db, staff.id, office_id))
            for office_id in offices
        },
    }


@router.get("/dashboard")
def dashboard(office_id: int | None = None, staff: User = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    resolved = office_id
    if resolved is None:
        resolved = next(iter(assigned_office_ids(db, staff.id)), None)
    if resolved is None:
        raise ApiException(403, "no_assigned_counters", "No counters have been assigned to your account yet. Please contact your administrator.")
    require_office_scope(db, staff, resolved)
    assigned = assigned_counter_ids(db, staff.id, resolved)
    snapshot = queue_service.office_snapshot(db, resolved)
    counters = [
        c for c in db.scalars(select(Counter).where(Counter.office_id == resolved).order_by(Counter.number)).all()
        if c.id in assigned
    ]
    snapshot["counters"] = [_counter_row(db, c) for c in counters]
    return snapshot


@router.get("/counters")
def list_counters(office_id: int, staff: User = Depends(require_staff), db: Session = Depends(get_db)) -> list[dict]:
    require_office_scope(db, staff, office_id)
    assigned = assigned_counter_ids(db, staff.id, office_id)
    counters = [
        c for c in db.scalars(select(Counter).where(Counter.office_id == office_id).order_by(Counter.number)).all()
        if c.id in assigned
    ]
    return [_counter_row(db, c) for c in counters]


@router.patch("/counters/{counter_id}")
async def set_counter_status(
    counter_id: int,
    body: CounterStatusUpdate,
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict:
    counter = get_counter(db, counter_id)
    require_counter_assignment(db, staff, counter)
    previous_status = counter.status
    try:
        status = CounterStatus(body.status)
    except ValueError as exc:
        raise ApiException(400, "invalid_status", "Unknown counter status.") from exc
    counter.status = status.value
    if previous_status != status.value and status in (CounterStatus.OFFLINE, CounterStatus.MAINTENANCE, CounterStatus.BREAK):
        from ..models import Office
        from ..services.token_service import ACTIVE_STATUSES
        from ..config import get_settings

        service_ids = set(db.scalars(select(CounterService.service_id).where(CounterService.counter_id == counter.id)).all())
        if not service_ids:
            service_ids = set(db.scalars(select(Service.id).join(Service.department).where(Service.department.has(office_id=counter.office_id))).all())
        office = db.get(Office, counter.office_id)
        for service_id in service_ids:
            active = db.scalars(select(Token).where(
                Token.office_id == counter.office_id, Token.service_id == service_id,
                Token.status.in_(ACTIVE_STATUSES), Token.user_id.is_not(None),
            )).all()
            for token in active:
                user = db.get(User, token.user_id)
                eta = token_view.token_detail(db, token, include_qr=False).get("eta_min", 0)
                link = f"{get_settings().frontend_base_url.rstrip('/')}?ticket={token.reference}"
                notify_service.enqueue(
                    db, user=user, token=token, office_id=counter.office_id,
                    kind=NotificationKind.QUEUE_DELAY,
                    subject=f"Queue update for token {token.label}",
                    body=(f"Counter availability changed to {status.value}. The current estimated wait is {eta} minutes. "
                          f"Office: {office.name if office else 'Government office'}. Track changes: {link}. Predictions may change."),
                    dedupe_key=f"counter-status:{counter.id}:{status.value}:{token.id}:{int(_utcnow().timestamp())}",
                )
    audit_service.record(
        db, action="counter.status_changed", actor_id=staff.id, actor_role=staff.role,
        entity_type="counter", entity_id=counter.id, office_id=counter.office_id,
        detail={"status": status.value},
    )
    db.commit()
    await hub.broadcast(_room(counter.office_id, 0), {"type": "counters.updated", "office_id": counter.office_id})
    return _counter_row(db, counter)


@router.put("/counters/{counter_id}/services")
def assign_services(
    counter_id: int,
    body: CounterAssignmentUpdate,
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict:
    counter = get_counter(db, counter_id)
    require_counter_assignment(db, staff, counter)
    valid = set(db.scalars(select(Service.id).where(Service.id.in_(body.service_ids))).all()) if body.service_ids else set()
    if len(valid) != len(set(body.service_ids)):
        raise ApiException(400, "invalid_service", "One or more services do not exist.")
    links = db.scalars(select(CounterService).where(CounterService.counter_id == counter.id)).all()
    existing = {link.service_id for link in links}
    for link in links:
        if link.service_id not in valid:
            db.delete(link)
    # Flush removals before inserting replacements so a service that remains in
    # the assignment set cannot collide with the unique counter/service key.
    db.flush()
    for service_id in valid - existing:
        db.add(CounterService(counter_id=counter.id, service_id=service_id))
    audit_service.record(
        db, action="counter.services_assigned", actor_id=staff.id, actor_role=staff.role,
        entity_type="counter", entity_id=counter.id, office_id=counter.office_id,
        detail={"service_ids": sorted(valid)},
    )
    db.commit()
    return _counter_row(db, counter)


@router.post("/counters/{counter_id}/call-next")
async def call_next(
    counter_id: int,
    body: CallNextRequest,
    request: Request,
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict:
    counter = get_counter(db, counter_id)
    require_counter_assignment(db, staff, counter)
    service = db.get(Service, body.service_id)
    if service is None:
        raise ApiException(404, "not_found", "Service not found.")
    if not _counter_serves(db, counter, body.service_id):
        raise ApiException(409, "counter_not_assigned", "This counter is not assigned to that service.")

    serving = _active_for_counter(db, counter.id)
    if serving is not None:
        raise ApiException(409, "counter_busy", "Finish or skip the current token before calling the next one.")

    candidate = _next_token(db, counter.office_id, body.service_id)
    if candidate is None:
        raise ApiException(404, "queue_empty", "No citizens are waiting for this service.")

    token_service.apply_transition(
        db, candidate, TokenStatus.CALLED.value, note=f"Called to {counter.name}",
        actor_id=staff.id, actor_role=staff.role, counter_id=counter.id,
    )
    counter.status = CounterStatus.BUSY.value
    if candidate.user_id:
        user = db.get(User, candidate.user_id)
        notify_service.enqueue(
            db, user=user, token=candidate, office_id=counter.office_id,
            kind=NotificationKind.TOKEN_CALLED,
            subject=f"Token {candidate.label}: it's your turn",
            body=(f"Your token has been called. Please proceed to {counter.name} for {service.name}. "
                  f"Office: {(db.get(Office, counter.office_id).name if db.get(Office, counter.office_id) else 'Government office')}"),
            dedupe_key=f"token-called:{candidate.id}",
        )
    audit_service.record(
        db, action="token.called", actor_id=staff.id, actor_role=staff.role,
        entity_type="token", entity_id=candidate.id, office_id=counter.office_id,
        detail={"counter_id": counter.id, "label": candidate.label},
        request_id=getattr(request.state, "request_id", ""),
    )
    view = token_view.token_detail(db, candidate)
    db.commit()
    await hub.broadcast(_room(counter.office_id, body.service_id), {"type": "queue.updated", "service_id": body.service_id, "office_id": counter.office_id})
    await hub.broadcast(f"token:{candidate.reference}", {"type": "token.updated", "token": view})
    return view


@router.post("/counters/{counter_id}/start")
async def start_service(
    counter_id: int,
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict:
    counter = get_counter(db, counter_id)
    require_counter_assignment(db, staff, counter)
    token = _active_for_counter(db, counter_id)
    if token is None or token.status != TokenStatus.CALLED.value:
        raise ApiException(409, "nothing_called", "There is no called token to start serving.")
    token_service.apply_transition(
        db, token, TokenStatus.SERVING.value, note="Service started",
        actor_id=staff.id, actor_role=staff.role, counter_id=counter.id,
    )
    view = token_view.token_detail(db, token)
    db.commit()
    await hub.broadcast(_room(token.office_id, token.service_id), {"type": "queue.updated", "service_id": token.service_id, "office_id": token.office_id})
    await hub.broadcast(f"token:{token.reference}", {"type": "token.updated", "token": view})
    return view


@router.post("/counters/{counter_id}/complete")
async def complete_service(
    counter_id: int,
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict:
    counter = get_counter(db, counter_id)
    require_counter_assignment(db, staff, counter)
    token = _active_for_counter(db, counter_id)
    if token is None or token.status != TokenStatus.SERVING.value:
        raise ApiException(409, "nothing_serving", "There is no token currently being served.")

    token_service.apply_transition(
        db, token, TokenStatus.COMPLETED.value, note="Service completed",
        actor_id=staff.id, actor_role=staff.role, counter_id=counter.id,
    )
    _record_service_time(db, token, counter)
    _score_prediction(db, token)
    counter.status = CounterStatus.AVAILABLE.value

    if token.user_id:
        user = db.get(User, token.user_id)
        notify_service.enqueue(
            db, user=user, token=token, office_id=counter.office_id,
            kind=NotificationKind.SERVICE_COMPLETED,
            subject=f"Token {token.label}: service completed",
            body="Your service is complete. Thank you for using QueueLess — please leave feedback in the app.",
            dedupe_key=f"service-completed:{token.id}",
        )
    audit_service.record(
        db, action="token.completed", actor_id=staff.id, actor_role=staff.role,
        entity_type="token", entity_id=token.id, office_id=counter.office_id,
        detail={"label": token.label, "counter_id": counter.id},
    )
    view = token_view.token_detail(db, token)
    db.commit()
    ml_model.invalidate(token.service_id)  # new data is available for retraining
    await hub.broadcast(_room(token.office_id, token.service_id), {"type": "queue.updated", "service_id": token.service_id, "office_id": token.office_id})
    await hub.broadcast(f"token:{token.reference}", {"type": "token.updated", "token": view})
    return view


@router.post("/counters/{counter_id}/skip")
async def skip_token(
    counter_id: int,
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict:
    counter = get_counter(db, counter_id)
    require_counter_assignment(db, staff, counter)
    token = _active_for_counter(db, counter_id)
    if token is None or token.status != TokenStatus.CALLED.value:
        raise ApiException(409, "nothing_called", "There is no called token to skip.")
    token.no_show_count += 1
    token_service.apply_transition(
        db, token, TokenStatus.SKIPPED.value, note="Skipped: citizen not present",
        actor_id=staff.id, actor_role=staff.role,
    )
    counter.status = CounterStatus.AVAILABLE.value
    if token.user_id:
        user = db.get(User, token.user_id)
        notify_service.enqueue(
            db, user=user, token=token, office_id=counter.office_id,
            kind=NotificationKind.TOKEN_SKIPPED,
            subject=f"Token {token.label} was skipped",
            body="You were not present when called. Rejoin the queue from the app if you still need service.",
            dedupe_key=f"token-skipped:{token.id}",
        )
    view = token_view.token_detail(db, token)
    db.commit()
    await hub.broadcast(_room(token.office_id, token.service_id), {"type": "queue.updated", "service_id": token.service_id, "office_id": token.office_id})
    return view


@router.get("/queue")
def staff_queue(
    office_id: int = Query(...),
    service_id: int = Query(...),
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict:
    require_office_scope(db, staff, office_id)
    return queue_service.snapshot(db, office_id, service_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _counter_row(db: Session, counter: Counter) -> dict:
    current = db.scalar(
        select(Token)
        .where(
            Token.counter_id == counter.id,
            Token.status.in_([TokenStatus.CALLED.value, TokenStatus.SERVING.value]),
        )
        .order_by(Token.updated_at.desc())
    )
    service_ids = list(
        db.scalars(select(CounterService.service_id).where(CounterService.counter_id == counter.id))
    )
    return {
        "id": counter.id,
        "number": counter.number,
        "name": counter.name,
        "status": counter.status,
        "office_id": counter.office_id,
        "service_ids": service_ids,
        "current_token": current.label if current else None,
        "current_status": current.status if current else None,
    }


def _counter_serves(db: Session, counter: Counter, service_id: int) -> bool:
    links = list(db.scalars(select(CounterService.service_id).where(CounterService.counter_id == counter.id)))
    return not links or service_id in links


def _active_for_counter(db: Session, counter_id: int) -> Token | None:
    return db.scalar(
        select(Token)
        .where(
            Token.counter_id == counter_id,
            Token.status.in_([TokenStatus.CALLED.value, TokenStatus.SERVING.value]),
        )
        .order_by(Token.updated_at.desc())
    )


def _next_token(db: Session, office_id: int, service_id: int) -> Token | None:
    """Fair call order: present (ARRIVED) citizens first, then priority, then FIFO."""
    ordered = queue_service.queue_for_service(db, office_id, service_id)
    eligible = [t for t in ordered if t.status != TokenStatus.SERVING.value]
    if not eligible:
        return None
    arrived = [t for t in eligible if t.status == TokenStatus.ARRIVED.value]
    pool = arrived or [t for t in eligible if t.status in (TokenStatus.WAITING.value, TokenStatus.APPROACHING.value)]
    return pool[0] if pool else None


def _record_service_time(db: Session, token: Token, counter: Counter) -> None:
    started = _aware(token.started_at) or _utcnow()
    completed = _aware(token.completed_at) or _utcnow()
    duration = max(0.5, (completed - started).total_seconds() / 60.0)
    db.add(
        ServiceTimeRecord(
            token_id=token.id,
            office_id=token.office_id,
            service_id=token.service_id,
            counter_id=counter.id,
            duration_min=round(duration, 2),
            started_at=token.started_at or started,
            completed_at=token.completed_at or completed,
            origin=DataOrigin.LIVE.value,
        )
    )


def _score_prediction(db: Session, token: Token) -> None:
    """Attach the real wait to the latest prediction so accuracy is measured."""
    prediction = db.scalar(
        select(Prediction).where(Prediction.token_id == token.id).order_by(Prediction.created_at.desc())
    )
    if prediction is None:
        return
    created = _aware(token.created_at)
    called = _aware(token.called_at) or _aware(token.completed_at)
    if created and called:
        actual = (called - created).total_seconds() / 60.0
        prediction.actual_wait_min = round(actual, 2)
        prediction.absolute_error_min = round(abs(prediction.predicted_min - actual), 2)
