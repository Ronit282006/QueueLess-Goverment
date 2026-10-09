"""Offices, departments and services catalogue."""
from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from .user import utcnow


class Office(Base):
    __tablename__ = "offices"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(String(255), default="")
    location_instructions: Mapped[str] = mapped_column(String(300), default="")
    working_hours: Mapped[str] = mapped_column(String(60), default="09:30-18:00")
    working_days: Mapped[str] = mapped_column(String(60), default="mon,tue,wed,thu,fri,sat")
    # Office-configurable policy values (no hard-coded government rules).
    sla_target_wait_min: Mapped[int] = mapped_column(Integer, default=20)
    no_show_grace_min: Mapped[int] = mapped_column(Integer, default=3)
    eta_alert_threshold_min: Mapped[int] = mapped_column(Integer, default=15)
    arrival_buffer_min: Mapped[int] = mapped_column(Integer, default=15)
    incident_response_min: Mapped[int] = mapped_column(Integer, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )

    departments: Mapped[list[Department]] = relationship(back_populates="office", cascade="all, delete-orphan")


class OfficeHoliday(Base):
    __tablename__ = "office_holidays"
    __table_args__ = (UniqueConstraint("office_id", "holiday_date", name="uq_office_holiday_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    holiday_date: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(120), default="Office holiday")


class OfficeIncident(Base):
    __tablename__ = "office_incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id", ondelete="SET NULL"), nullable=True)
    incident_type: Mapped[str] = mapped_column(String(30), default="CAPACITY")
    description: Mapped[str] = mapped_column(String(400))
    location_instructions: Mapped[str] = mapped_column(String(300), default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    response_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(400), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    office: Mapped[Office] = relationship(back_populates="departments")
    services: Mapped[list[Service]] = relationship(back_populates="department", cascade="all, delete-orphan")


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    # JSON array of required document names; the citizen only ticks readiness.
    documents_json: Mapped[str] = mapped_column(String(2000), default="[]")
    average_service_min: Mapped[float] = mapped_column(default=6.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    department: Mapped[Department] = relationship(back_populates="services")

    @property
    def documents(self) -> list[str]:
        try:
            data = json.loads(self.documents_json)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    @documents.setter
    def documents(self, value: list[str]) -> None:
        self.documents_json = json.dumps(value, ensure_ascii=False)
