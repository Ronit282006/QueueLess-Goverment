"""Queue composition, ordering, positions and ETA recalculation."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Counter,
    CounterStatus,
    Office,
    Service,
    Token,
    TokenStatus,
)
from ..models.enums import TokenStage
from . import prediction_service
from .token_service import ACTIVE_STATUSES


def _ts(value: datetime | None) -> float:
    """Timezone-safe sortable timestamp (SQLite may return naive datetimes)."""
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def available_counters(db: Session, office_id: int, service_id: int | None = None) -> list[Counter]:
    """Counters in an office that are not offline/on break/maintenance."""
    stmt = (
        select(Counter)
        .where(
            Counter.office_id == office_id,
            Counter.status.in_([CounterStatus.AVAILABLE.value, CounterStatus.BUSY.value]),
        )
        .order_by(Counter.number)
    )
    counters = list(db.scalars(stmt).all())
    if service_id is None:
        return counters
    from ..models import CounterService

    handled = set(
        db.scalars(
            select(CounterService.counter_id).where(CounterService.service_id == service_id)
        ).all()
    )
    # If no explicit mapping exists yet, every healthy counter can serve the queue.
    if not handled:
        return counters
    return [c for c in counters if c.id in handled]


def queue_for_service(db: Session, office_id: int, service_id: int) -> list[Token]:
    """Active tokens ordered by priority then arrival (fair FIFO within class)."""
    tokens = list(
        db.scalars(
            select(Token)
            .where(
                Token.office_id == office_id,
                Token.service_id == service_id,
                Token.status.in_(ACTIVE_STATUSES),
                (Token.scheduled_for.is_(None)) | (Token.scheduled_for <= datetime.now(timezone.utc).date()),
            )
            .order_by(Token.created_at, Token.id)
        ).all()
    )
    # Priority class first, then original arrival order; serving tokens stay first.
    tokens.sort(
        key=lambda t: (
            0 if t.status == TokenStatus.SERVING.value else 1,
            -t.priority_rank,
            _ts(t.created_at),
            t.id,
        )
    )
    return tokens


def token_position(tokens: list[Token], token: Token) -> int:
    for index, item in enumerate(tokens):
        if item.id == token.id:
            return index
    return len(tokens)


def stage_for(token: Token, eta_min: float, position: int, alert_threshold_min: int = 15) -> str:
    if token.status in (TokenStatus.CALLED.value, TokenStatus.SERVING.value):
        return TokenStage.YOUR_TURN.value
    if token.status == TokenStatus.ARRIVED.value:
        return TokenStage.YOUR_TURN.value if position <= 1 else TokenStage.APPROACHING.value
    if eta_min <= alert_threshold_min or position <= 1:
        return TokenStage.COME_NOW.value
    if eta_min <= alert_threshold_min + 5:
        return TokenStage.APPROACHING.value
    return TokenStage.SAFE.value


def active_service_min(db: Session, service_id: int, fallback: float) -> float:
    measured, _ = prediction_service.observed_service_minutes(db, service_id)
    if measured:
        return measured
    service = db.get(Service, service_id)
    return service.average_service_min if service else fallback


def service_eta(db: Session, office_id: int, service_id: int) -> dict:
    """Average ETA over the whole service queue (used by dashboards and alerts)."""
    tokens = queue_for_service(db, office_id, service_id)
    waiting = [t for t in tokens if t.status != TokenStatus.SERVING.value]
    counters = available_counters(db, office_id, service_id)
    pred = prediction_service.predict(
        db,
        office_id=office_id,
        service_id=service_id,
        people_ahead=len(waiting),
        active_counters=len(counters),
    )
    return {"waiting": len(waiting), "active_counters": len(counters), "eta_min": round(pred.minutes), "prediction": pred}


def snapshot(db: Session, office_id: int, service_id: int, *, with_tokens: bool = True) -> dict:
    office = db.get(Office, office_id)
    service = db.get(Service, service_id)
    tokens = queue_for_service(db, office_id, service_id)
    counters = available_counters(db, office_id, service_id)
    serving = [t for t in tokens if t.status == TokenStatus.SERVING.value]
    waiting = [t for t in tokens if t.status != TokenStatus.SERVING.value]

    from .grace_service import grace_view

    rows = []
    for index, token in enumerate(tokens):
        position = index + 1 if token.status != TokenStatus.SERVING.value else 0
        ahead = sum(1 for t in tokens[:index] if t.status != TokenStatus.SERVING.value)
        pred = prediction_service.predict(
            db,
            office_id=office_id,
            service_id=service_id,
            people_ahead=ahead,
            active_counters=len(counters),
        )
        token.stage = stage_for(token, pred.minutes, position, office.eta_alert_threshold_min if office else 15)
        grace = grace_view(token)
        rows.append(
            {
                "id": token.id,
                "reference": token.reference,
                "number": token.number,
                "label": token.label,
                "name": "",
                "service": service.name if service else "",
                "status": token.status,
                "stage": token.stage,
                "created_at": token.created_at.isoformat() if token.created_at else None,
                "people_ahead": ahead,
                "position": position,
                "eta_min": round(pred.minutes),
                "eta_low": round(pred.low),
                "eta_high": round(pred.high),
                "fairness_score": round(token.fairness_score or 100),
                "priority": token.priority_rank,
                "grace_state": grace["state"],
                "grace_deadline": grace["deadline"],
                "grace_remaining_sec": grace["remaining_sec"],
                "arrived": grace["arrived"],
            }
        )

    overall = prediction_service.predict(
        db,
        office_id=office_id,
        service_id=service_id,
        people_ahead=len(waiting),
        active_counters=len(counters),
    )
    return {
        "office_id": office_id,
        "office_name": office.name if office else "",
        "service_id": service_id,
        "service_name": service.name if service else "",
        "waiting": len(waiting),
        "serving": len(serving),
        "active_counters": len(counters),
        "average_service_min": round(active_service_min(db, service_id, 6.2), 1),
        "tokens": rows if with_tokens else [],
        "prediction": overall.as_dict(),
    }


def office_snapshot(db: Session, office_id: int) -> dict:
    """Aggregate snapshot across every service in an office (staff/admin views)."""
    services = db.scalars(
        select(Service)
        .join(Service.department)
        .where(Service.department.has(office_id=office_id))
    ).all()
    per_service = [snapshot(db, office_id, s.id, with_tokens=False) for s in services]
    total_waiting = sum(s["waiting"] for s in per_service)
    return {
        "office_id": office_id,
        "services": per_service,
        "total_waiting": total_waiting,
        "active_counters": sum(s["active_counters"] for s in per_service),
    }
