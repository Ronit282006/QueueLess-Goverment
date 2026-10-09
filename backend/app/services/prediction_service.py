"""Waiting-time prediction.

Phase 5 replaces the analytical baseline below with a trained scikit-learn
residual model AND keeps the analytical decomposition for the explainable AI
panel. Everything here is deterministic and works with zero history.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Office, QueueSnapshot, Service, ServiceTimeRecord
from ..ml import features as ml_features
from ..ml import model as ml_model


@dataclass
class PredictionResult:
    minutes: float
    low: float
    high: float
    confidence: float
    people_ahead: int
    method: str
    history_samples: int
    factors: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "people_ahead": self.people_ahead,
            "minutes": round(self.minutes),
            "minutes_low": max(0, round(self.low)),
            "minutes_high": max(0, round(self.high)),
            "confidence": round(self.confidence, 2),
            "method": self.method,
            "history_samples": self.history_samples,
            "factors": self.factors,
        }


def observed_service_minutes(db: Session, service_id: int, limit: int = 200) -> tuple[float, int]:
    """Average recently observed service duration (minutes) and sample count."""
    durations = db.scalars(
        select(ServiceTimeRecord.duration_min)
        .where(ServiceTimeRecord.service_id == service_id)
        .order_by(ServiceTimeRecord.completed_at.desc())
        .limit(limit)
    ).all()
    durations = [d for d in durations if d and 0.25 <= d <= 180]
    if not durations:
        return 0.0, 0
    return sum(durations) / len(durations), len(durations)


def no_show_rate(db: Session, service_id: int) -> float:
    total = db.scalar(
        select(func.count()).select_from(QueueSnapshot).where(QueueSnapshot.service_id == service_id)
    )
    if not total:
        return 0.0
    flagged = db.scalar(
        select(func.count())
        .select_from(QueueSnapshot)
        .where(QueueSnapshot.service_id == service_id, QueueSnapshot.queue_length == 0)
    )
    return min(0.4, (flagged or 0) / max(1, total))


def congestion_factor(db: Session, service_id: int, hour: int) -> float:
    """How much busier than average is this hour of day, from historical snapshots."""
    rows = db.execute(
        select(QueueSnapshot.hour_of_day, func.avg(QueueSnapshot.queue_length))
        .where(QueueSnapshot.service_id == service_id)
        .group_by(QueueSnapshot.hour_of_day)
    ).all()
    if not rows:
        return 1.0
    values = {int(h): float(avg or 0) for h, avg in rows}
    overall = sum(values.values()) / len(values)
    if overall <= 0:
        return 1.0
    return max(0.6, min(1.6, values.get(hour, overall) / overall))


def predict(
    db: Session,
    *,
    office_id: int,
    service_id: int,
    people_ahead: int,
    active_counters: int,
    statuses_ahead: list[str] | None = None,
) -> PredictionResult:
    """Analytical M/M/c-style estimate with an explainable factor breakdown."""
    settings = get_settings()
    service = db.get(Service, service_id)
    office = db.get(Office, office_id)

    measured, samples = observed_service_minutes(db, service_id)
    base_service = measured or (service.average_service_min if service else settings.service_duration_min)
    if samples < 5:
        base_service = service.average_service_min if service else settings.service_duration_min

    counters = max(1, active_counters)
    no_show = no_show_rate(db, service_id)
    # No-shows remove expected work from the queue.
    effective_ahead = max(0.0, people_ahead * (1 - no_show * 0.6))

    now = _dt.datetime.now()
    hour = now.hour
    congestion = congestion_factor(db, service_id, hour)

    # --- Learned service duration from the gradient-boosting model (Phase 5).
    method = (
        "Analytical queueing estimate from observed service durations"
        if samples >= 5
        else "Analytical estimate using service average; collecting service history"
    )
    ml_metrics = None
    try:
        vector = ml_features.inference_features(
            hour=hour,
            day_of_week=now.weekday(),
            queue_length=people_ahead,
            active_counters=counters,
        )
        learned, ml_metrics = ml_model.predict_service_minutes(db, service_id=service_id, features=vector)
    except Exception:  # model problems must never break the citizen flow
        learned = None
    if learned is not None and ml_metrics is not None and ml_metrics.r2 > 0:
        # Trust the learned duration more once the model proves it beats the mean.
        weight = 0.65 if ml_metrics.r2 > 0.3 else 0.4
        base_service = (1 - weight) * base_service + weight * learned
        samples = max(samples, ml_metrics.samples)
        method = "AI model (gradient boosting) blended with analytical queueing"

    raw = effective_ahead * base_service / counters
    center = raw * (0.85 + 0.15 * congestion)
    # Complexity/serving overhead grows slightly with queue length.
    overhead = min(6.0, 0.12 * effective_ahead)
    center += overhead
    center = max(0.0, center)

    # Uncertainty comes from how much real service history we actually have.
    relative = 0.45 if samples < 20 else 0.30 if samples < 60 else 0.20
    if ml_metrics is not None and ml_metrics.r2 > 0.3:
        relative *= 0.85
    spread = max(1.5, center * relative)
    if ml_metrics is not None:
        confidence = min(0.95, 0.55 + max(0.0, min(0.4, ml_metrics.r2)))
    else:
        confidence = min(0.6, 0.25 + samples / 400.0)

    # Additive, explainable decomposition: the factors below sum to the estimate.
    single_counter = people_ahead * base_service
    people_term = round(single_counter)
    counter_term = round(raw - single_counter)
    overhead_term = round(overhead)
    congestion_term = round(raw * 0.15 * (congestion - 1))
    no_show_term = -round((people_ahead - effective_ahead) * base_service / counters)

    factors = [
        {"label": f"{int(people_ahead)} citizen(s) ahead", "impact_min": people_term, "direction": "increase"},
        {"label": f"{counters} active counter(s)", "impact_min": counter_term, "direction": "decrease" if counter_term < 0 else "neutral"},
        {"label": "Service complexity / handling", "impact_min": overhead_term, "direction": "increase"},
        {"label": "Time-of-day congestion", "impact_min": congestion_term, "direction": "increase" if congestion_term > 0 else "decrease"},
        {"label": "Expected no-shows", "impact_min": no_show_term, "direction": "decrease" if no_show_term < 0 else "neutral"},
    ]
    if ml_metrics is not None:
        for name, weight in sorted(ml_metrics.feature_importance.items(), key=lambda kv: kv[1], reverse=True)[:2]:
            factors.append(
                {
                    "label": f"AI weighs {ml_model.FEATURE_DISPLAY.get(name, name)}",
                    "impact_min": None,
                    "direction": "learned",
                    "weight": round(weight, 3),
                }
            )

    return PredictionResult(
        minutes=center,
        low=max(0, center - spread),
        high=center + spread,
        confidence=confidence,
        people_ahead=people_ahead,
        method=method,
        history_samples=samples,
        factors=[f for f in factors if f["impact_min"] is not None or "ahead" in f["label"] or f.get("weight")],
    )