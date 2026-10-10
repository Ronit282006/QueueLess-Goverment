"""Temporary office/service incidents and citizen-approved ticket rescheduling."""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..errors import ApiException
from ..models import Office, OfficeHoliday, OfficeIncident, Service, Token, User
from ..models.enums import NotificationKind, TokenStatus
from ..security import get_optional_user, require_admin, require_staff
from ..services import audit_service, catalog_service, notify_service, queue_service, token_service, token_view
from ..services.assignment_service import require_office_scope

router = APIRouter(prefix="/api", tags=["Incidents"])


class IncidentCreate(BaseModel):
    office_id: int
    service_id: int | None = None
    incident_type: str = Field(default="CAPACITY", pattern="^(CAPACITY|DELAY|CLOSURE|LOCATION)$")
    description: str = Field(min_length=4, max_length=400)
    location_instructions: str = Field(default="", max_length=300)
    starts_at: datetime | None = None
    ends_at: datetime


class IncidentResponse(BaseModel):
    action: str = Field(pattern="^(TRANSFER|CANCEL)$")
    action_token: str = Field(min_length=20, max_length=100)


class OfficeScheduleUpdate(BaseModel):
    working_hours: str = Field(min_length=5, max_length=60)
    working_days: str = Field(min_length=3, max_length=60)
    arrival_buffer_min: int = Field(default=15, ge=0, le=240)
    incident_response_min: int = Field(default=30, ge=5, le=1440)


class HolidayCreate(BaseModel):
    holiday_date: date
    name: str = Field(min_length=2, max_length=120)


class OfficeLocationUpdate(BaseModel):
    address: str = Field(min_length=3, max_length=255)
    location_instructions: str = Field(default="", max_length=300)
    # Optional geo pin so travel estimates work for this office.
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


_DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_AFFECTABLE = (TokenStatus.WAITING.value, TokenStatus.APPROACHING.value, TokenStatus.ARRIVED.value)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _next_working_day(db: Session, office: Office, service_id: int, after: date) -> date:
    workdays = {v.strip().lower()[:3] for v in office.working_days.split(",") if v.strip()}
    holidays = set(db.scalars(select(OfficeHoliday.holiday_date).where(OfficeHoliday.office_id == office.id)).all())
    for offset in range(1, 367):
        candidate = after + timedelta(days=offset)
        if _DAY_NAMES[candidate.weekday()] not in workdays or candidate in holidays:
            continue
        unavailable = db.scalar(
            select(OfficeIncident.id).where(
                OfficeIncident.office_id == office.id,
                OfficeIncident.status == "ACTIVE",
                OfficeIncident.incident_type == "CLOSURE",
                OfficeIncident.starts_at < datetime.combine(candidate + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc),
                OfficeIncident.ends_at >= datetime.combine(candidate, datetime.min.time(), tzinfo=timezone.utc),
                (OfficeIncident.service_id.is_(None)) | (OfficeIncident.service_id == service_id),
            ).limit(1)
        )
        if unavailable is None:
            return candidate
    raise ApiException(409, "no_service_date", "No available working date was found in the next year.")


def _queue_incident_email(db: Session, incident: OfficeIncident, token: Token, user: User) -> None:
    raw_action = secrets.token_urlsafe(32)
    token.incident_action_hash = hashlib.sha256(raw_action.encode()).hexdigest()
    token.incident_id = incident.id
    token.incident_response_due = incident.response_deadline
    token.incident_response_status = "PENDING"
    token.incident_notified_at = datetime.now(timezone.utc)
    settings = get_settings()
    action_link = (
        f"{settings.frontend_base_url.rstrip('/')}?ticket={token.reference}"
        f"&incident_action={raw_action}"
    )
    arrived_note = (
        "You are marked as arrived. Please coordinate with counter staff before leaving; they can help protect your place.\n\n"
        if token.status == TokenStatus.ARRIVED.value else ""
    )
    notify_service.enqueue(
        db, user=user, token=token, office_id=incident.office_id,
        kind=NotificationKind.INCIDENT_ACTION_REQUIRED,
        subject=f"Action needed for token {token.label}: {incident.description[:100]}",
        body=(
            f"An office incident affects your {token.label} ticket.\nIncident: {incident.description}\n"
            f"Response deadline: {incident.response_deadline.astimezone().strftime('%Y-%m-%d %H:%M %Z')}\n\n"
            f"Temporary location instructions: {incident.location_instructions or 'No location change reported.'}\n\n"
            f"{arrived_note}Open your secure ticket page to choose transfer to the next available working day or cancel: {action_link}\n"
            "If you do not respond by the deadline, the ticket will be cancelled under the displayed incident policy."
        ),
        dedupe_key=f"incident-action:{incident.id}:{token.id}",
    )


@router.post("/staff/incidents", status_code=201)
def create_incident(
    body: IncidentCreate,
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict:
    office = db.get(Office, body.office_id)
    if office is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    require_office_scope(db, staff, office.id)
    if body.service_id is not None:
        service = db.get(Service, body.service_id)
        if service is None or service.department.office_id != office.id:
            raise ApiException(400, "invalid_service", "The service does not belong to this office.")
    now = datetime.now(timezone.utc)
    starts_at, ends_at = _aware(body.starts_at or now), _aware(body.ends_at)
    if ends_at <= starts_at:
        raise ApiException(400, "invalid_incident_window", "Incident end must be after its start.")
    incident = OfficeIncident(
        office_id=office.id, service_id=body.service_id, incident_type=body.incident_type,
        description=body.description, location_instructions=body.location_instructions,
        starts_at=starts_at, ends_at=ends_at,
        response_deadline=now + timedelta(minutes=office.incident_response_min),
        created_by=staff.id,
    )
    db.add(incident)
    db.flush()
    affected = db.scalars(
        select(Token).where(
            Token.office_id == office.id,
            Token.status.in_(_AFFECTABLE),
            (Token.service_id == body.service_id) if body.service_id is not None else True,
        )
    ).all()
    arrived_for_staff: list[dict] = []
    notified_count = 0
    for token in affected:
        if body.incident_type != "CLOSURE":
            estimate = token_view.token_detail(db, token, include_qr=False).get("eta_min", 0)
            if now + timedelta(minutes=int(estimate)) <= ends_at:
                continue
        if token.user_id is None:
            continue
        user = db.get(User, token.user_id)
        if user is not None:
            _queue_incident_email(db, incident, token, user)
            notified_count += 1
            if token.status == TokenStatus.ARRIVED.value:
                arrived_for_staff.append({"id": token.id, "label": token.label, "status": token.status})
    audit_service.record(
        db, action="office.incident_created", actor_id=staff.id, actor_role=staff.role,
        entity_type="office_incident", entity_id=incident.id, office_id=office.id,
        detail={"type": incident.incident_type, "description": incident.description},
    )
    return {"id": incident.id, "office_id": office.id, "service_id": incident.service_id,
            "description": incident.description, "response_deadline": incident.response_deadline.isoformat(),
            "status": incident.status, "notified_count": notified_count,
            "arrived_for_staff": arrived_for_staff}


@router.get("/staff/incidents")
def list_incidents(
    office_id: int | None = None,
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(OfficeIncident)
    if office_id is not None:
        query = query.where(OfficeIncident.office_id == office_id)
    rows = db.scalars(query.order_by(OfficeIncident.id.desc()).limit(50)).all()
    return [
        {
            "id": r.id,
            "office_id": r.office_id,
            "service_id": r.service_id,
            "incident_type": r.incident_type,
            "description": r.description,
            "location_instructions": r.location_instructions,
            "starts_at": r.starts_at.isoformat(),
            "ends_at": r.ends_at.isoformat(),
            "response_deadline": r.response_deadline.isoformat(),
            "status": r.status,
            "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
            "resolved_at": r.resolved_at.isoformat() if getattr(r, "resolved_at", None) else None,
        }
        for r in rows
    ]


@router.post("/staff/incidents/{incident_id}/resolve")
def resolve_incident(
    incident_id: int,
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict:
    incident = db.get(OfficeIncident, incident_id)
    if incident is None:
        raise ApiException(404, "incident_not_found", "Incident not found.")
    require_office_scope(db, staff, incident.office_id)
    incident.status = "RESOLVED"
    incident.resolved_at = datetime.now(timezone.utc)
    audit_service.record(
        db, action="office.incident_resolved", actor_id=staff.id, actor_role=staff.role,
        entity_type="office_incident", entity_id=incident.id, office_id=incident.office_id,
        detail={"description": incident.description},
    )
    db.commit()
    return {"id": incident.id, "status": "RESOLVED", "resolved_at": incident.resolved_at.isoformat()}


@router.get("/staff/incidents/arrived")
def list_arrived_incident_tokens(
    office_id: int | None = None,
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(Token).where(
        Token.incident_id.is_not(None),
        Token.status == TokenStatus.ARRIVED.value,
        Token.incident_response_status.in_(("PENDING", "STAFF_REVIEW")),
    )
    if office_id is not None:
        query = query.where(Token.office_id == office_id)
    tokens = db.scalars(query.order_by(Token.id.desc()).limit(50)).all()
    return [
        {
            "id": t.id,
            "label": t.label,
            "status": t.status,
            "incident_id": t.incident_id,
            "incident_response_status": t.incident_response_status,
        }
        for t in tokens
    ]


@router.post("/tokens/{reference}/incident-response")
def respond_to_incident(
    reference: str,
    body: IncidentResponse,
    actor: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> dict:
    token = db.scalar(select(Token).where(Token.reference == reference).with_for_update())
    if token is None or token.incident_id is None:
        raise ApiException(404, "incident_not_found", "No active incident response is attached to this ticket.")
    if actor is None or token.user_id != actor.id:
        raise ApiException(403, "forbidden", "Sign in as the citizen who owns this ticket to respond.")
    incident = db.get(OfficeIncident, token.incident_id)
    now = datetime.now(timezone.utc)
    deadline = _aware(token.incident_response_due) if token.incident_response_due else now
    expected = hashlib.sha256(body.action_token.encode()).hexdigest()
    if not secrets.compare_digest(expected, token.incident_action_hash) or token.incident_response_status != "PENDING":
        raise ApiException(403, "invalid_incident_action", "This incident action link is invalid or already used.")
    if now > deadline:
        raise ApiException(410, "incident_action_expired", "The response deadline has passed.")
    if body.action == "CANCEL":
        token_service.apply_transition(db, token, TokenStatus.CANCELLED.value,
                                       note="Citizen cancelled after office incident", actor_id=actor.id, actor_role=actor.role)
        token.incident_response_status = "CANCELLED"
        token.incident_action_hash = ""
        notify_service.enqueue(db, user=actor, token=token, office_id=token.office_id,
                               kind=NotificationKind.TOKEN_CANCELLED,
                               subject=f"Token {token.label} cancelled",
                               body="Your ticket was cancelled as requested.", dedupe_key=f"incident-cancelled:{incident.id}:{token.id}")
        audit_service.record(db, action="incident.ticket_cancelled", actor_id=actor.id, actor_role=actor.role,
                             entity_type="token", entity_id=token.id, office_id=token.office_id,
                             detail={"incident_id": incident.id})
        db.commit()
        return {"action": "CANCELLED", "token": token_view.token_detail(db, token)}

    office = db.get(Office, token.office_id)
    if office is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    scheduled = _next_working_day(db, office, token.service_id, now.date())
    if token.status not in (TokenStatus.WAITING.value, TokenStatus.APPROACHING.value, TokenStatus.ARRIVED.value):
        raise ApiException(409, "ticket_already_in_service", "Staff must finish or rebook a ticket already called for service.")
    original_id = token.id
    token_service.apply_transition(db, token, TokenStatus.RESCHEDULED.value,
                                   note=f"Citizen approved transfer to {scheduled.isoformat()}",
                                   actor_id=actor.id, actor_role=actor.role)
    token.incident_response_status = "TRANSFERRED"
    token.incident_action_hash = ""
    new_token = token_service.create_token(db, office_id=token.office_id, service_id=token.service_id,
                                           user_id=token.user_id, priority_rank=token.priority_rank)
    new_token.scheduled_for = scheduled
    new_token.rescheduled_from_id = original_id
    new_token.incident_id = incident.id
    new_token.incident_response_status = "TRANSFERRED"
    service = db.get(Service, token.service_id)
    notify_service.enqueue(
        db, user=actor, token=new_token, office_id=token.office_id,
        kind=NotificationKind.TOKEN_TRANSFERRED,
        subject=f"Token {new_token.label} rescheduled to {scheduled.isoformat()}",
        body=(f"Your {service.name if service else 'service'} ticket was transferred to {scheduled.isoformat()}. "
              f"Your new queue number is {new_token.label}. Your original waiting and ticket history remain on the earlier ticket."),
        dedupe_key=f"incident-transferred:{incident.id}:{token.id}",
    )
    audit_service.record(db, action="incident.ticket_transferred", actor_id=actor.id, actor_role=actor.role,
                         entity_type="token", entity_id=new_token.id, office_id=token.office_id,
                         detail={"from_token_id": original_id, "incident_id": incident.id, "scheduled_for": scheduled.isoformat()})
    db.commit()
    return {"action": "TRANSFERRED", "scheduled_for": scheduled.isoformat(),
            "token": token_view.token_detail(db, new_token)}


@router.post("/staff/incidents/tokens/{token_id}/transfer")
def staff_rebook_arrived_ticket(
    token_id: int,
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict:
    token = db.get(Token, token_id)
    if token is None or token.incident_id is None:
        raise ApiException(404, "incident_ticket_not_found", "Incident ticket not found.")
    require_office_scope(db, staff, token.office_id)
    if token.status != TokenStatus.ARRIVED.value or token.incident_response_status not in ("PENDING", "STAFF_REVIEW"):
        raise ApiException(409, "ticket_not_rebookable", "Only an arrived ticket awaiting incident help can be rebooked here.")
    office = db.get(Office, token.office_id)
    if office is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    scheduled = _next_working_day(db, office, token.service_id, datetime.now(timezone.utc).date())
    old_id = token.id
    token_service.apply_transition(db, token, TokenStatus.RESCHEDULED.value,
                                   note=f"Staff rebooked arrived citizen to {scheduled.isoformat()}",
                                   actor_id=staff.id, actor_role=staff.role)
    token.incident_response_status = "STAFF_TRANSFERRED"
    token.incident_action_hash = ""
    new_token = token_service.create_token(db, office_id=token.office_id, service_id=token.service_id,
                                           user_id=token.user_id, priority_rank=token.priority_rank)
    new_token.scheduled_for = scheduled
    new_token.rescheduled_from_id = old_id
    new_token.incident_id = token.incident_id
    new_token.incident_response_status = "TRANSFERRED"
    user = db.get(User, token.user_id) if token.user_id else None
    notify_service.enqueue(
        db, user=user, token=new_token, office_id=token.office_id,
        kind=NotificationKind.TOKEN_TRANSFERRED,
        subject=f"Your arrived ticket was rebooked for {scheduled.isoformat()}",
        body=f"Staff rebooked your arrived ticket to {scheduled.isoformat()}. New queue number: {new_token.label}. Your original arrival and waiting history are preserved on the earlier ticket.",
        dedupe_key=f"staff-incident-transfer:{token.incident_id}:{old_id}",
    )
    audit_service.record(db, action="incident.arrived_ticket_rebooked", actor_id=staff.id,
                         actor_role=staff.role, entity_type="token", entity_id=new_token.id,
                         office_id=token.office_id,
                         detail={"from_token_id": old_id, "scheduled_for": scheduled.isoformat()})
    db.commit()
    return {"scheduled_for": scheduled.isoformat(), "token": token_view.token_detail(db, new_token)}


@router.patch("/admin/offices/{office_id}/schedule")
def update_office_schedule(
    office_id: int,
    body: OfficeScheduleUpdate,
    staff: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    office = db.get(Office, office_id)
    if office is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    office.working_hours = body.working_hours
    office.working_days = ",".join(dict.fromkeys(day.strip().lower()[:3] for day in body.working_days.split(",") if day.strip()))
    office.arrival_buffer_min = body.arrival_buffer_min
    office.incident_response_min = body.incident_response_min
    audit_service.record(db, action="office.schedule_updated", actor_id=staff.id, actor_role=staff.role,
                         entity_type="office", entity_id=office.id, office_id=office.id)
    db.commit()
    return {"office_id": office.id, "working_hours": office.working_hours, "working_days": office.working_days,
            "arrival_buffer_min": office.arrival_buffer_min, "incident_response_min": office.incident_response_min}


@router.post("/admin/offices/{office_id}/holidays", status_code=201)
def add_office_holiday(
    office_id: int,
    body: HolidayCreate,
    staff: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    if db.get(Office, office_id) is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    if db.scalar(select(OfficeHoliday.id).where(OfficeHoliday.office_id == office_id, OfficeHoliday.holiday_date == body.holiday_date)):
        raise ApiException(409, "holiday_exists", "This holiday is already configured.")
    holiday = OfficeHoliday(office_id=office_id, holiday_date=body.holiday_date, name=body.name)
    db.add(holiday)
    db.flush()
    audit_service.record(db, action="office.holiday_added", actor_id=staff.id, actor_role=staff.role,
                         entity_type="office_holiday", entity_id=holiday.id, office_id=office_id,
                         detail={"date": body.holiday_date.isoformat(), "name": body.name})
    db.commit()
    return {"id": holiday.id, "holiday_date": holiday.holiday_date.isoformat(), "name": holiday.name}


@router.get("/admin/offices/{office_id}/holidays")
def list_office_holidays(
    office_id: int,
    staff: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    if db.get(Office, office_id) is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    rows = db.scalars(select(OfficeHoliday).where(OfficeHoliday.office_id == office_id).order_by(OfficeHoliday.holiday_date)).all()
    return [{"id": row.id, "holiday_date": row.holiday_date.isoformat(), "name": row.name} for row in rows]


@router.delete("/admin/offices/{office_id}/holidays/{holiday_id}")
def delete_office_holiday(
    office_id: int,
    holiday_id: int,
    staff: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    holiday = db.get(OfficeHoliday, holiday_id)
    if holiday is None or holiday.office_id != office_id:
        raise ApiException(404, "holiday_not_found", "Office holiday not found.")
    db.delete(holiday)
    audit_service.record(db, action="office.holiday_removed", actor_id=staff.id, actor_role=staff.role,
                         entity_type="office_holiday", entity_id=holiday_id, office_id=office_id)
    db.commit()
    return {"removed": holiday_id}


@router.patch("/admin/offices/{office_id}/location")
def update_office_location(
    office_id: int,
    body: OfficeLocationUpdate,
    staff: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    office = db.get(Office, office_id)
    if office is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    office.address = body.address
    office.location_instructions = body.location_instructions
    if body.latitude is not None:
        office.latitude = body.latitude
    if body.longitude is not None:
        office.longitude = body.longitude
    catalog_service.invalidate_catalog()
    db.flush()
    active = db.scalars(select(Token).where(
        Token.office_id == office.id,
        Token.status.in_(token_service.ACTIVE_STATUSES),
        Token.user_id.is_not(None),
    )).all()
    change_key = f"{office.id}:{int(datetime.now(timezone.utc).timestamp())}"
    for token in active:
        user = db.get(User, token.user_id)
        notify_service.enqueue(
            db, user=user, token=token, office_id=office.id,
            kind=NotificationKind.SERVICE_LOCATION_CHANGED,
            subject=f"Service location update for token {token.label}",
            body=(f"The service location has changed. New address: {office.address}. "
                  f"Instructions: {office.location_instructions or 'Ask staff at the office entrance.'}"),
            dedupe_key=f"office-location:{change_key}:{token.id}",
        )
    audit_service.record(db, action="office.location_changed", actor_id=staff.id, actor_role=staff.role,
                         entity_type="office", entity_id=office.id, office_id=office.id,
                         detail={"address": office.address})
    db.commit()
    return {
        "office_id": office.id,
        "address": office.address,
        "location_instructions": office.location_instructions,
        "latitude": office.latitude,
        "longitude": office.longitude,
    }
