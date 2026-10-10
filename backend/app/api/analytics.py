"""Analytics endpoints: peak hours, demand, efficiency, SLA, feedback, accuracy.

All figures are computed from real records (tokens, service-time observations,
queue snapshots, scored predictions and feedback). Demo rows are flagged with
origin="DEMO" in the database so they can be excluded from production reporting
if required.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiException
from ..models import (
    Feedback,
    Office,
    Prediction,
    QueueSnapshot,
    Service,
    ServiceTimeRecord,
    Token,
    TokenStatus,
    User,
)
from ..security import require_staff
from ..services.assignment_service import assigned_office_ids, require_office_scope
from ..services.token_service import ACTIVE_STATUSES

router = APIRouter(prefix="/api/analytics", tags=["Analytics"], dependencies=[Depends(require_staff)])


def _resolve_office(db: Session, staff: User, office_id: int | None) -> Office:
    if office_id is not None:
        require_office_scope(db, staff, office_id)
        office = db.get(Office, office_id)
    else:
        # STAFF members default to their first assigned office; admins may
        # still view any office by passing office_id explicitly.
        first_assigned = next(iter(assigned_office_ids(db, staff.id)), None)
        if first_assigned is None:
            raise ApiException(403, "no_assigned_counters", "No counters have been assigned to your account yet. Please contact your administrator.")
        office = db.get(Office, first_assigned)
    if office is None:
        raise ApiException(404, "not_found", "Office not found.")
    return office


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _wait_minutes_expr():
    # Wait = called - created, in minutes (only defined once called).
    return func.extract("epoch", Token.called_at - Token.created_at) / 60.0


@router.get("/overview")
def overview(office_id: int | None = None, staff: User = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    office = _resolve_office(db, staff, office_id)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    total_today = db.scalar(
        select(func.count()).select_from(Token).where(Token.office_id == office.id, Token.created_at >= today)
    ) or 0
    completed_today = db.scalar(
        select(func.count()).select_from(Token).where(
            Token.office_id == office.id, Token.status == TokenStatus.COMPLETED.value, Token.completed_at >= today
        )
    ) or 0
    waiting_now = db.scalar(
        select(func.count()).select_from(Token).where(
            Token.office_id == office.id, Token.status.in_(ACTIVE_STATUSES)
        )
    ) or 0
    no_shows_today = db.scalar(
        select(func.count()).select_from(Token).where(
            Token.office_id == office.id, Token.status == TokenStatus.SKIPPED.value, Token.updated_at >= today
        )
    ) or 0
    avg_wait = db.scalar(
        select(func.avg(_wait_minutes_expr())).where(
            Token.office_id == office.id, Token.called_at.is_not(None), Token.created_at >= _since(7)
        )
    )
    satisfaction = db.scalar(
        select(func.avg(Feedback.rating)).where(Feedback.office_id == office.id)
    )

    return {
        "office_id": office.id,
        "office_name": office.name,
        "tokens_today": int(total_today),
        "completed_today": int(completed_today),
        "waiting_now": int(waiting_now),
        "no_shows_today": int(no_shows_today),
        "avg_wait_min_7d": round(float(avg_wait), 1) if avg_wait is not None else None,
        "sla_target_wait_min": office.sla_target_wait_min,
        "satisfaction_avg": round(float(satisfaction), 2) if satisfaction is not None else None,
    }


@router.get("/peak-hours")
def peak_hours(
    office_id: int | None = None,
    service_id: int | None = None,
    days: int = Query(21, ge=1, le=120),
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict:
    office = _resolve_office(db, staff, office_id)
    snap = (
        select(
            QueueSnapshot.hour_of_day,
            func.avg(QueueSnapshot.queue_length).label("avg_queue"),
            func.avg(QueueSnapshot.avg_wait_min).label("avg_wait"),
            func.count().label("samples"),
        )
        .where(QueueSnapshot.office_id == office.id, QueueSnapshot.captured_at >= _since(days))
    )
    if service_id:
        snap = snap.where(QueueSnapshot.service_id == service_id)
    snap = snap.group_by(QueueSnapshot.hour_of_day).order_by(QueueSnapshot.hour_of_day)
    rows = db.execute(snap).all()

    hours = [
        {
            "hour": int(r.hour_of_day),
            "avg_queue": round(float(r.avg_queue or 0), 1),
            "avg_wait_min": round(float(r.avg_wait or 0), 1),
            "samples": int(r.samples),
        }
        for r in rows
    ]
    busiest = max(hours, key=lambda h: h["avg_queue"], default=None)
    return {"office_id": office.id, "hours": hours, "busiest_hour": busiest["hour"] if busiest else None}


@router.get("/demand")
def demand(
    office_id: int | None = None,
    days: int = Query(14, ge=1, le=120),
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict:
    office = _resolve_office(db, staff, office_id)
    day = func.date(Token.created_at).label("day")
    rows = db.execute(
        select(day, func.count().label("tokens"))
        .where(Token.office_id == office.id, Token.created_at >= _since(days))
        .group_by(day)
        .order_by(day)
    ).all()
    series = [{"day": str(r.day), "tokens": int(r.tokens)} for r in rows]
    total = sum(point["tokens"] for point in series)
    average = round(total / len(series), 1) if series else 0
    peak = max(series, key=lambda p: p["tokens"], default=None)
    return {"office_id": office.id, "series": series, "total": total, "daily_average": average, "peak_day": peak}


@router.get("/efficiency")
def efficiency(office_id: int | None = None, staff: User = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    office = _resolve_office(db, staff, office_id)
    services = db.scalars(
        select(Service).join(Service.department).where(Service.department.has(office_id=office.id))
    ).all()

    result = []
    for service in services:
        avg_service = db.scalar(
            select(func.avg(ServiceTimeRecord.duration_min)).where(ServiceTimeRecord.service_id == service.id)
        )
        samples = db.scalar(
            select(func.count()).select_from(ServiceTimeRecord).where(ServiceTimeRecord.service_id == service.id)
        ) or 0
        completed = db.scalar(
            select(func.count()).select_from(Token).where(
                Token.service_id == service.id, Token.status == TokenStatus.COMPLETED.value
            )
        ) or 0
        served = db.scalar(
            select(func.count()).select_from(Token).where(
                Token.service_id == service.id, Token.called_at.is_not(None)
            )
        ) or 0
        avg_wait = db.scalar(
            select(func.avg(_wait_minutes_expr())).where(
                Token.service_id == service.id, Token.called_at.is_not(None)
            )
        )
        # Throughput = citizens served per hour of observed service time.
        throughput = (60.0 / float(avg_service)) if avg_service else None
        result.append(
            {
                "service_id": service.id,
                "service_name": service.name,
                "avg_service_min": round(float(avg_service), 2) if avg_service else None,
                "avg_wait_min": round(float(avg_wait), 1) if avg_wait is not None else None,
                "samples": int(samples),
                "completed": int(completed),
                "served": int(served),
                "served_per_hour_per_counter": round(throughput, 1) if throughput else None,
            }
        )
    return {"office_id": office.id, "services": result}


@router.get("/sla")
def sla(
    office_id: int | None = None,
    days: int = Query(30, ge=1, le=365),
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict:
    office = _resolve_office(db, staff, office_id)
    target = office.sla_target_wait_min
    wait = _wait_minutes_expr()
    within = func.sum(case((wait <= target, 1), else_=0))
    row = db.execute(
        select(
            func.count().label("served"),
            func.avg(wait).label("avg_wait"),
            within.label("within_target"),
        ).where(
            Token.office_id == office.id,
            Token.called_at.is_not(None),
            Token.created_at >= _since(days),
        )
    ).one()
    served = int(row.served or 0)
    within_target = int(row.within_target or 0)
    return {
        "office_id": office.id,
        "sla_target_wait_min": target,
        "served": served,
        "within_target": within_target,
        "compliance_pct": round(within_target / served * 100, 1) if served else 0.0,
        "avg_wait_min": round(float(row.avg_wait), 1) if row.avg_wait is not None else None,
    }


@router.get("/feedback")
def feedback_report(office_id: int | None = None, staff: User = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    office = _resolve_office(db, staff, office_id)
    rows = db.execute(
        select(Feedback.rating, func.count().label("n")).where(Feedback.office_id == office.id).group_by(Feedback.rating)
    ).all()
    distribution = {str(star): 0 for star in range(1, 6)}
    for rating, count in rows:
        distribution[str(int(rating))] = int(count)
    total = sum(distribution.values())
    average = sum(int(k) * v for k, v in distribution.items()) / total if total else 0
    accurate = db.scalar(
        select(func.count()).select_from(Feedback).where(Feedback.office_id == office.id, Feedback.eta_accurate.is_(True))
    ) or 0
    rated_eta = db.scalar(
        select(func.count()).select_from(Feedback).where(Feedback.office_id == office.id, Feedback.eta_accurate.is_not(None))
    ) or 0
    return {
        "office_id": office.id,
        "total": total,
        "average_rating": round(average, 2) if total else None,
        "distribution": distribution,
        "eta_accuracy_pct": round(accurate / rated_eta * 100, 1) if rated_eta else None,
    }


@router.get("/prediction-accuracy")
def prediction_accuracy(office_id: int | None = None, staff: User = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    office = _resolve_office(db, staff, office_id)
    row = db.execute(
        select(
            func.count().label("scored"),
            func.avg(Prediction.absolute_error_min).label("mae"),
            func.avg(Prediction.confidence).label("confidence"),
        ).where(Prediction.office_id == office.id, Prediction.absolute_error_min.is_not(None))
    ).one()
    scored = int(row.scored or 0)
    return {
        "office_id": office.id,
        "scored_predictions": scored,
        "mean_absolute_error_min": round(float(row.mae), 2) if row.mae is not None else None,
        "avg_confidence": round(float(row.confidence), 2) if row.confidence is not None else None,
    }