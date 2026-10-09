"""Learned service-time model (Phase 5).

A gradient-boosted regressor predicts how long a service takes from the time of
day, weekday, queue depth and active counters. The prediction service blends
this learned duration with an analytical, fully-explainable decomposition so the
API can always show *why* it produced a number.

Models are trained on demand from PostgreSQL history, cached in-process, and can
be persisted to ``app/ml/artifacts`` for inspection.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ServiceTimeRecord
from .features import FEATURE_NAMES, build_training_frame

FEATURE_DISPLAY = {
    "hour": "Time of day",
    "day_of_week": "Day of week",
    "queue_length": "Queue length",
    "active_counters": "Active counters",
    "is_peak": "Peak-hour load",
}

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MIN_SAMPLES = 50
_CACHE_MAX_AGE_SAMPLES = 200


@dataclass
class ModelMetrics:
    samples: int
    train_samples: int
    test_samples: int
    mae: float
    r2: float
    feature_importance: dict[str, float]

    def as_dict(self) -> dict:
        return {
            "samples": self.samples,
            "train_samples": self.train_samples,
            "test_samples": self.test_samples,
            "mae_min": round(self.mae, 3),
            "r2": round(self.r2, 4),
            "feature_importance": {k: round(v, 4) for k, v in self.feature_importance.items()},
        }


class ServiceTimeModel:
    def __init__(self, service_id: int | None = None) -> None:
        self.service_id = service_id
        self.estimator = None
        self.metrics: ModelMetrics | None = None
        self._trained_at_samples = 0

    @property
    def is_fitted(self) -> bool:
        return self.estimator is not None

    def fit(self, X: np.ndarray, y: np.ndarray) -> ModelMetrics:
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.metrics import mean_absolute_error, r2_score
        from sklearn.model_selection import train_test_split

        n = len(y)
        if n < MIN_SAMPLES:
            raise ValueError(f"not enough samples to train ({n} < {MIN_SAMPLES})")
        test_size = max(10, int(round(n * 0.2)))
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )
        estimator = GradientBoostingRegressor(
            n_estimators=220, max_depth=3, learning_rate=0.05, subsample=0.9, random_state=42
        )
        estimator.fit(X_train, y_train)
        predictions = estimator.predict(X_test)
        importance = {
            name: float(value)
            for name, value in zip(FEATURE_NAMES, estimator.feature_importances_, strict=False)
        }
        self.estimator = estimator
        self.metrics = ModelMetrics(
            samples=n,
            train_samples=len(y_train),
            test_samples=len(y_test),
            mae=float(mean_absolute_error(y_test, predictions)),
            r2=float(r2_score(y_test, predictions)),
            feature_importance=importance,
        )
        self._trained_at_samples = n
        return self.metrics

    def predict(self, features: np.ndarray) -> float:
        if self.estimator is None:
            raise RuntimeError("model is not fitted")
        row = np.asarray(features, dtype=float).reshape(1, -1)
        value = float(self.estimator.predict(row)[0])
        return max(1.0, min(120.0, value))

    def needs_retrain(self, available_samples: int) -> bool:
        return self.estimator is None or available_samples - self._trained_at_samples >= _CACHE_MAX_AGE_SAMPLES

    def save(self) -> None:
        if self.estimator is None or self.metrics is None:
            return
        import joblib

        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        name = f"service_{self.service_id}" if self.service_id else "global"
        joblib.dump(self.estimator, ARTIFACT_DIR / f"{name}.joblib")
        (ARTIFACT_DIR / f"{name}.metrics.json").write_text(json.dumps(self.metrics.as_dict(), indent=2))


_registry: dict[int, ServiceTimeModel] = {}
_lock = threading.Lock()


def train_service_model(db: Session, service_id: int) -> ServiceTimeModel | None:
    df = build_training_frame(db, service_id)
    if df is None:
        return None
    X, y = df
    model = ServiceTimeModel(service_id)
    model.fit(X, y)
    model.save()
    return model


def get_service_model(db: Session, service_id: int) -> ServiceTimeModel | None:
    available = db.scalar(
        select(func.count()).select_from(ServiceTimeRecord).where(ServiceTimeRecord.service_id == service_id)
    ) or 0
    if available < MIN_SAMPLES:
        return None
    with _lock:
        model = _registry.get(service_id)
        if model is not None and not model.needs_retrain(available):
            return model
    try:
        model = train_service_model(db, service_id)
    except Exception:
        return _registry.get(service_id)
    if model is not None:
        with _lock:
            _registry[service_id] = model
    return model


def predict_service_minutes(db: Session, *, service_id: int, features: np.ndarray) -> tuple[float | None, ModelMetrics | None]:
    model = get_service_model(db, service_id)
    if model is None or not model.is_fitted:
        return None, None
    return model.predict(features), model.metrics


def invalidate(service_id: int | None = None) -> None:
    with _lock:
        if service_id is None:
            _registry.clear()
        else:
            _registry.pop(service_id, None)


def loaded_models() -> dict[int, dict]:
    """Snapshot of in-process trained models and their metrics (for admin health)."""
    with _lock:
        return {
            service_id: model.metrics.as_dict()
            for service_id, model in _registry.items()
            if model.metrics is not None
        }