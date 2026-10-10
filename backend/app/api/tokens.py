"""Virtual token endpoints for citizens and staff."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..errors import ApiException
from ..models import Feedback, Office, Prediction, PriorityRule, Service, Token, TokenEvent, User
from ..models.enums import NotificationKind, TokenStatus
from ..realtime import hub
from ..security import get_optional_user
from ..services import (
    arrival_service,
    audit_service,
    catalog_service,
    notify_service,
    qr_service,
    routing_service,
    token_service,
    token_view,
)
from ..services.rate_limit import rate_limit
from ..schemas.token import CheckInRequest, FeedbackRequest, TokenCreateRequest, TransitionRequest

router = APIRouter(prefix="/api/tokens", tags=["Tokens"])


def _queue_room(office_id: int, service_id: int) -> str:
    return f"queue:{office_id}:{service_id}"


def priority_for(db: Session, office_id: int, user: User | None) -> int:
    """Highest matching office-configurable priority boost for this citizen."""
    if user is None:
        return 0
    tags = set(user.tag_list)
    if not tags:
        return 0
    rules = db.scalars(
        select(PriorityRule).where(
            PriorityRule.is_active.is_(True),
            (PriorityRule.office_id == office_id) | (PriorityRule.office_id.is_(None)),
        )
    ).all()
    best = 0
    for rule in rules:
        required = set(rule.tags)
        if required and required.issubset(tags):
            best = max(best, rule.boost)
    return best


def _resolve_office(db: Session, service_id: int, requested: int | None) -> int:
    service_office = catalog_service.office_for_service(db, service_id)
    if service_office is None:
        raise ApiException(404, "not_found", "Service not found.")
    office = service_office if requested is None else db.get(Office, requested)
    if office is None:
        raise ApiException(404, "not_found", "Office not found.")
    if not office.is_active:
        raise ApiException(409, "office_inactive", "This office is not currently accepting new bookings.")
    return office.id


@router.post("", status_code=201, dependencies=[Depends(rate_limit("token_create", 30))])
async def create_token(
    body: TokenCreateRequest,
    request: Request,
    current: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> dict:
    service = catalog_service.get_service(db, body.service_id)
    if service is None:
        raise ApiException(404, "not_found", "Service not found.")
    office_id = _resolve_office(db, body.service_id, body.office_id)

    boost = priority_for(db, office_id, current)

    token = token_service.create_token(
        db,
        office_id=office_id,
        service_id=body.service_id,
        user_id=current.id if current else None,
        priority_rank=boost,
    )
    # If the citizen shared a location, capture a travel estimate and schedule a
    # durable "time to leave" reminder. Coordinates themselves are not stored.
    if routing_service.valid_coords(body.latitude, body.longitude):
        office = db.get(Office, office_id)
        if office is not None and routing_service.valid_coords(office.latitude, office.longitude):
            origin = (float(body.latitude), float(body.longitude))
            route = routing_service.estimate_route(
                origin, (office.latitude, office.longitude), mode=body.travel_mode
            )
            if route.available:
                token.travel_min = route.duration_min
                token.travel_distance_km = route.distance_km
                token.travel_mode = route.mode
                token.travel_provider = route.provider
                token.travel_calculated_at = datetime.now(timezone.utc)
            arrival_service.schedule_departure_reminder(db, token, origin, mode=body.travel_mode)
    view = token_view.token_detail(db, token)
    if current is not None:
        office = db.get(Office, office_id)
        eta = int(view.get("eta_min", 0))
        live_link = f"{get_settings().frontend_base_url.rstrip('/')}?ticket={token.reference}"
        notify_service.enqueue(
            db,
            user=current,
            token=token,
            office_id=office_id,
            kind=NotificationKind.TOKEN_CREATED,
            subject=f"Your QueueLess token {token.label} is confirmed",
            body=(
                f"Your QueueLess virtual token is confirmed.\n\nToken: {token.label}\nService: {service.name}\n"
                f"Office: {office.name if office else 'Government office'}\nAddress: {office.address if office else 'See the live ticket'}\n"
                f"Opening hours: {office.working_hours if office else 'See the live ticket'}\n"
                f"Current estimated wait: {eta} minutes\nStatus: {token.status}\n\n"
                f"Track your ticket securely: {live_link}\nThe QR attachment contains only your secure ticket reference."
            ),
            dedupe_key=f"token-created:{token.id}",
        )
    prediction = view.get("prediction") or {}
    db.add(
        Prediction(
            token_id=token.id,
            office_id=office_id,
            service_id=body.service_id,
            people_ahead=view.get("people_ahead", 0),
            predicted_min=view.get("eta_min", 0),
            low_min=prediction.get("minutes_low", view.get("eta_min", 0)),
            high_min=prediction.get("minutes_high", view.get("eta_min", 0)),
            confidence=prediction.get("confidence", 0.0),
            method=prediction.get("method", "hybrid"),
            features_json=json.dumps({"documents_confirmed": len(body.documents_confirmed)}),
            factors_json=json.dumps(prediction.get("factors", [])),
        )
    )
    audit_service.record(
        db,
        action="token.created",
        actor_id=current.id if current else None,
        actor_role=current.role if current else "CITIZEN",
        entity_type="token",
        entity_id=token.id,
        office_id=office_id,
        detail={"label": token.label, "service_id": body.service_id},
        request_id=getattr(request.state, "request_id", ""),
    )
    db.commit()
    await hub.broadcast(_queue_room(office_id, body.service_id), {"type": "queue.updated", "service_id": body.service_id, "office_id": office_id})
    return view


@router.post("/check-in")
async def check_in(
    body: CheckInRequest,
    request: Request,
    actor: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> dict:
    """Citizen/staff check-in by scanning the QR code (or its bare reference)."""
    reference = body.reference or qr_service.reference_from_payload(body.qr_payload or "")
    if not reference:
        raise ApiException(400, "invalid_qr", "A valid QueueLess QR code or reference is required.")
    token = db.scalar(select(Token).where(Token.reference == reference))
    if token is None:
        raise ApiException(404, "not_found", "Token not found.")
    if token.status in (TokenStatus.COMPLETED.value, TokenStatus.CANCELLED.value, TokenStatus.EXPIRED.value):
        raise ApiException(409, "closed_token", "This token is no longer active.")

    if token.status != TokenStatus.ARRIVED.value:
        if token.status not in (TokenStatus.WAITING.value, TokenStatus.APPROACHING.value, TokenStatus.CREATED.value):
            raise ApiException(409, "invalid_transition", f"Cannot check in a token that is {token.status}.")
        token_service.apply_transition(
            db,
            token,
            TokenStatus.ARRIVED.value,
            note="QR check-in confirmed arrival at the office",
            actor_id=actor.id if actor else None,
            actor_role=actor.role if actor else "CITIZEN",
        )
    # Arrived: the "time to leave" reminder is no longer relevant.
    arrival_service.cancel_reminders(db, token.id)

    audit_service.record(
        db,
        action="token.checked_in",
        actor_id=actor.id if actor else None,
        actor_role=actor.role if actor else "CITIZEN",
        entity_type="token",
        entity_id=token.id,
        office_id=token.office_id,
        detail={"label": token.label},
        request_id=getattr(request.state, "request_id", ""),
    )
    view = token_view.token_detail(db, token)
    db.commit()
    await hub.broadcast(_queue_room(token.office_id, token.service_id), {"type": "queue.updated", "service_id": token.service_id, "office_id": token.office_id})
    await hub.broadcast(f"token:{token.reference}", {"type": "token.updated", "token": view})
    return view


@router.get("/{reference}")
def get_token(reference: str, db: Session = Depends(get_db)) -> dict:
    token = db.scalar(select(Token).where(Token.reference == reference))
    if token is None:
        raise ApiException(404, "not_found", "Token not found.")
    return token_view.token_detail(db, token)


@router.get("/{reference}/events")
def token_events(reference: str, db: Session = Depends(get_db)) -> list[dict]:
    token = db.scalar(select(Token).where(Token.reference == reference))
    if token is None:
        raise ApiException(404, "not_found", "Token not found.")
    events = db.scalars(
        select(TokenEvent).where(TokenEvent.token_id == token.id).order_by(TokenEvent.created_at)
    ).all()
    return [
        {
            "from_status": e.from_status,
            "to_status": e.to_status,
            "note": e.note,
            "actor_role": e.actor_role,
            "at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


@router.post("/{reference}/transition")
async def transition(
    reference: str,
    body: TransitionRequest,
    request: Request,
    actor: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> dict:
    token = db.scalar(select(Token).where(Token.reference == reference))
    if token is None:
        raise ApiException(404, "not_found", "Token not found.")
    # The opaque reference is a capability for viewing/checking in/cancelling
    # a token. It must not let a citizen mark their own service complete or
    # manipulate the staff state machine.
    if actor is None or actor.role not in ("STAFF", "ADMIN"):
        if body.status != TokenStatus.CANCELLED.value:
            raise ApiException(403, "forbidden", "Citizens may only cancel their own token here.")
        if actor is not None and token.user_id != actor.id:
            raise ApiException(403, "forbidden", "You can only cancel your own token.")
    try:
        new_status = TokenStatus(body.status)
    except ValueError as exc:
        raise ApiException(400, "invalid_status", "Unknown token status.") from exc

    token_service.apply_transition(
        db,
        token,
        new_status.value,
        note=body.note or f"Moved to {new_status.value}",
        actor_id=actor.id if actor else None,
        actor_role=actor.role if actor else "CITIZEN",
    )
    if new_status in (
        TokenStatus.CANCELLED,
        TokenStatus.COMPLETED,
        TokenStatus.EXPIRED,
        TokenStatus.ARRIVED,
        TokenStatus.RESCHEDULED,
    ):
        arrival_service.cancel_reminders(db, token.id)
    if new_status == TokenStatus.CANCELLED and token.user_id:
        user = db.get(User, token.user_id)
        notify_service.enqueue(
            db, user=user, token=token, office_id=token.office_id,
            kind=NotificationKind.TOKEN_CANCELLED,
            subject=f"Token {token.label} cancelled",
            body=f"Your {token.label} ticket for {token_view.token_detail(db, token, include_qr=False)['service_name']} has been cancelled.",
            dedupe_key=f"token-cancelled:{token.id}",
        )

    audit_service.record(
        db,
        action=f"token.{new_status.value.lower()}",
        actor_id=actor.id if actor else None,
        actor_role=actor.role if actor else "CITIZEN",
        entity_type="token",
        entity_id=token.id,
        office_id=token.office_id,
        detail={"label": token.label},
        request_id=getattr(request.state, "request_id", ""),
    )
    view = token_view.token_detail(db, token)
    db.commit()
    await hub.broadcast(_queue_room(token.office_id, token.service_id), {"type": "queue.updated", "service_id": token.service_id, "office_id": token.office_id})
    await hub.broadcast(f"token:{token.reference}", {"type": "token.updated", "token": view})
    return view


@router.post("/{reference}/feedback", status_code=201)
def submit_feedback(
    reference: str,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
) -> dict:
    token = db.scalar(select(Token).where(Token.reference == reference))
    if token is None:
        raise ApiException(404, "not_found", "Token not found.")
    if token.status != TokenStatus.COMPLETED.value:
        raise ApiException(409, "not_completed", "Feedback is available after the service is completed.")
    existing = db.scalar(select(Feedback).where(Feedback.token_id == token.id))
    if existing is not None:
        raise ApiException(409, "already_submitted", "Feedback has already been submitted for this token.")
    feedback = Feedback(
        token_id=token.id,
        user_id=token.user_id,
        office_id=token.office_id,
        rating=body.rating,
        eta_accurate=body.eta_accurate,
        comment=body.comment,
    )
    db.add(feedback)
    db.flush()
    return {"message": "Thank you for your feedback.", "id": feedback.id}
