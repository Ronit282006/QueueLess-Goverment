"""Configurable priority rules and AI counter recommendations."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .enums import RecommendationStatus


class PriorityRule(Base):
    """Office-configurable priority boost — no hard-coded eligibility rules.

    `required_tags` is a comma list of citizen profile tags; a token receives
    `boost` added to its queue priority when the citizen holds every tag.
    """

    __tablename__ = "priority_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int | None] = mapped_column(
        ForeignKey("offices.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(400), default="")
    required_tags: Mapped[str] = mapped_column(String(200), default="")
    boost: Mapped[int] = mapped_column(Integer, default=5)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now()
    )

    @property
    def tags(self) -> list[str]:
        return [t.strip() for t in self.required_tags.split(",") if t.strip()]


class CounterRecommendation(Base):
    """AI-generated counter reallocation suggestion (admin must approve)."""

    __tablename__ = "counter_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    from_counter_id: Mapped[int | None] = mapped_column(
        ForeignKey("counters.id", ondelete="SET NULL"), nullable=True
    )
    from_service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), nullable=True
    )
    to_service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    expected_reduction_min: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default=RecommendationStatus.PENDING.value, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now(), index=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    @property
    def detail(self) -> dict:
        try:
            data = json.loads(self.detail_json)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
