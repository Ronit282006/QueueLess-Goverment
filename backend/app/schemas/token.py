"""Token schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .queue import PredictionOut


class TokenCreateRequest(BaseModel):
    office_id: int | None = None
    service_id: int
    documents_confirmed: list[str] = Field(default_factory=list)


class TokenEventOut(BaseModel):
    from_status: str | None = None
    to_status: str
    note: str = ""
    actor_role: str = "SYSTEM"
    created_at: datetime


class TokenOut(BaseModel):
    id: int
    reference: str
    number: int
    label: str
    office_id: int
    office_name: str
    service_id: int
    service_name: str
    status: str
    stage: str
    counter_id: int | None = None
    counter_name: str | None = None
    priority: int = 0
    fairness_score: float = 100
    people_ahead: int = 0
    eta_min: float = 0
    expected_service_at: datetime | None = None
    created_at: datetime
    called_at: datetime | None = None
    arrived_at: datetime | None = None
    completed_at: datetime | None = None
    qr_data_url: str | None = None
    prediction: PredictionOut | None = None
    stage_message: str | None = None


class TransitionRequest(BaseModel):
    status: str
    counter_id: int | None = None
    note: str = ""


class CheckInRequest(BaseModel):
    reference: str | None = None
    qr_payload: str | None = None


class FeedbackRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    eta_accurate: bool | None = None
    comment: str = Field(default="", max_length=1000)