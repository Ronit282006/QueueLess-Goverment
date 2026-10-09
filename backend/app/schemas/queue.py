"""Queue, prediction and analytics-facing schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PredictionFactor(BaseModel):
    label: str
    impact_min: float
    # "increase" | "decrease" | "neutral" — how the factor pushed the estimate
    direction: str = "neutral"


class PredictionOut(BaseModel):
    people_ahead: int
    minutes: float
    minutes_low: float
    minutes_high: float
    confidence: float
    method: str
    history_samples: int
    factors: list[PredictionFactor] = []
    reliability: str = "estimate"


class TokenRow(BaseModel):
    id: int
    reference: str
    number: int
    label: str
    status: str
    stage: str
    priority: int = 0
    people_ahead: int
    eta_min: float
    created_at: datetime


class QueueSnapshot(BaseModel):
    office_id: int
    office_name: str
    service_id: int | None = None
    service_name: str | None = None
    waiting: int
    active_counters: int
    total_counters: int
    average_service_min: float
    no_show_rate: float
    tokens: list[TokenRow]
    prediction: PredictionOut
    generated_at: datetime