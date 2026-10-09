"""Prediction engine tests (Phase 5): baseline, learned model, explainability."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select


def _first_service(db):
    from app.models import Service

    return db.scalar(select(Service).limit(1))


def test_analytical_prediction_has_explainable_factors(app):
    from app.db import SessionLocal
    from app.services import prediction_service

    db = SessionLocal()
    try:
        service = _first_service(db)
        result = prediction_service.predict(
            db,
            office_id=service.department.office_id,
            service_id=service.id,
            people_ahead=6,
            active_counters=3,
        )
        assert result.minutes >= 0
        assert result.low <= result.minutes <= result.high
        assert result.factors
        assert all("label" in f and "impact_min" in f for f in result.factors)
        assert "Analytical" in result.method
    finally:
        db.close()


def test_model_learns_structured_history(app):
    from app.db import SessionLocal
    from app.ml import model as ml_model
    from app.models import ServiceTimeRecord

    db = SessionLocal()
    try:
        service = _first_service(db)
        office_id = service.department.office_id
        rng = random.Random(7)
        base = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
        # Deliverable relationship: later hours take strictly longer.
        for i in range(160):
            hour = 9 + (i % 8)
            expected = 4.0 + 0.9 * (hour - 9)
            duration = max(1.0, rng.gauss(expected, 0.35))
            started = base + timedelta(hours=i)
            db.add(
                ServiceTimeRecord(
                    office_id=office_id,
                    service_id=service.id,
                    duration_min=duration,
                    started_at=started,
                    completed_at=started + timedelta(minutes=duration),
                    origin="TEST",
                )
            )
        db.commit()

        ml_model.invalidate(service.id)
        trained = ml_model.train_service_model(db, service.id)
        assert trained is not None and trained.is_fitted
        assert trained.metrics is not None
        assert trained.metrics.r2 > 0.5
        assert trained.metrics.mae < 1.5

        from app.ml import features

        vector = features.inference_features(hour=9, day_of_week=0, queue_length=1, active_counters=2)
        early = trained.predict(vector)
        vector = features.inference_features(hour=16, day_of_week=0, queue_length=1, active_counters=2)
        late = trained.predict(vector)
        assert late > early

        # The full prediction service should now adopt the learned model.
        from app.services import prediction_service

        result = prediction_service.predict(
            db, office_id=office_id, service_id=service.id, people_ahead=4, active_counters=2
        )
        assert "AI model" in result.method
    finally:
        db.close()