"""Token presentation view shared by citizen, staff and admin endpoints."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from ..models import Counter, Office, Service, Token
from . import prediction_service, qr_service
from .queue_service import available_counters, queue_for_service, stage_for
from .token_service import ACTIVE_STATUSES

_STAGE_MESSAGE = {
    "SAFE": "You are safely in the queue. There is no need to reach the office yet.",
    "APPROACHING": "Your turn is approaching. Please start making your way to the office.",
    "COME_NOW": "Please proceed to the office now. Your turn is coming up.",
    "YOUR_TURN": "It is your turn. Please proceed to the counter.",
}


def token_detail(db: Session, token: Token, *, include_qr: bool = True) -> dict:
    office = db.get(Office, token.office_id)
    service = db.get(Service, token.service_id)
    counter = db.get(Counter, token.counter_id) if token.counter_id else None

    tokens = queue_for_service(db, token.office_id, token.service_id)
    counters = available_counters(db, token.office_id, token.service_id)

    index = next((i for i, t in enumerate(tokens) if t.id == token.id), None)
    if index is None:
        ahead = 0
        position = 0
    elif token.status == "SERVING":
        ahead = 0
        position = 0
    else:
        position = index + 1
        ahead = sum(1 for t in tokens[:index] if t.status != "SERVING")

    pred = prediction_service.predict(
        db,
        office_id=token.office_id,
        service_id=token.service_id,
        people_ahead=ahead,
        active_counters=len(counters),
    )
    stage = stage_for(token, pred.minutes, position, office.eta_alert_threshold_min if office else 15)

    expected_at = None
    if token.status in ACTIVE_STATUSES:
        base = token.created_at
        if base is not None:
            expected_at = base + timedelta(minutes=pred.minutes)

    return {
        "id": token.id,
        "reference": token.reference,
        "number": token.number,
        "label": token.label,
        "office_id": token.office_id,
        "office_name": office.name if office else "",
        "office_address": office.address if office else "",
        "office_location_instructions": office.location_instructions if office else "",
        "office_working_hours": office.working_hours if office else "",
        "service_id": token.service_id,
        "service_name": service.name if service else "",
        "status": token.status,
        "stage": stage,
        "stage_message": _STAGE_MESSAGE.get(stage, ""),
        "counter_id": token.counter_id,
        "counter_name": counter.name if counter else None,
        "priority": token.priority_rank,
        "fairness_score": round(token.fairness_score or 100, 1),
        "people_ahead": ahead,
        "position": position,
        "eta_min": round(pred.minutes),
        "expected_service_at": expected_at.isoformat() if expected_at else None,
        "created_at": token.created_at.isoformat() if token.created_at else None,
        "called_at": token.called_at.isoformat() if token.called_at else None,
        "arrived_at": token.arrived_at.isoformat() if token.arrived_at else None,
        "completed_at": token.completed_at.isoformat() if token.completed_at else None,
        "scheduled_for": token.scheduled_for.isoformat() if token.scheduled_for else None,
        "rescheduled_from_id": token.rescheduled_from_id,
        "incident_id": token.incident_id,
        "incident_response_due": token.incident_response_due.isoformat() if token.incident_response_due else None,
        "incident_response_status": token.incident_response_status,
        "qr_data_url": qr_service.qr_data_url(token.reference) if include_qr else None,
        "prediction": pred.as_dict(),
    }


def stage_message(stage: str) -> str:
    return _STAGE_MESSAGE.get(stage, "")
