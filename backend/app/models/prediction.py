"""Stored predictions — used to measure real accuracy/error over time."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_id: Mapped[int | None] = mapped_column(
        ForeignKey("tokens.id", ondelete="SET NULL"), nullable=True, index=True
    )
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    people_ahead: Mapped[int] = mapped_column(Integer)
    predicted_min: Mapped[float] = mapped_column(Float)
    low_min: Mapped[float] = mapped_column(Float)
    high_min: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(160), default="hybrid")
    features_json: Mapped[str] = mapped_column(String(4000), default="{}")
    factors_json: Mapped[str] = mapped_column(String(4000), default="[]")

    # Filled in when the token completes — powers measured (not claimed) accuracy.
    actual_wait_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    absolute_error_min: Mapped[float | None] = mapped_column(Float, nullable=True)

    @property
    def features(self) -> dict:
        try:
            return json.loads(self.features_json)
        except json.JSONDecodeError:
            return {}

    @property
    def factors(self) -> list[dict]:
        try:
            data = json.loads(self.factors_json)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []
