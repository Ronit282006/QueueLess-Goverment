"""Catalogue schemas."""
from __future__ import annotations

from pydantic import BaseModel

from .common import ORMModel


class ServiceOut(ORMModel):
    id: int
    code: str
    name: str
    description: str
    average_service_min: float


class ServiceDetail(ORMModel):
    id: int
    code: str
    name: str
    description: str
    documents: list[str]
    average_service_min: float
    is_active: bool


class DepartmentOut(ORMModel):
    id: int
    name: str
    description: str


class DepartmentTree(DepartmentOut):
    services: list[ServiceDetail]


class OfficeOut(ORMModel):
    id: int
    code: str
    name: str
    address: str
    working_hours: str
    working_days: str
    sla_target_wait_min: int
    no_show_grace_min: int
    eta_alert_threshold_min: int


class OfficeTree(OfficeOut):
    departments: list[DepartmentTree]


class ServiceDetailView(BaseModel):
    service: ServiceDetail
    office: OfficeOut
    department: DepartmentOut
    current_queue: int
    active_counters: int
    average_service_min: float
    estimated_wait_min: float
    estimated_wait_low_min: float
    estimated_wait_high_min: float
    confidence: float
    required_documents: list[str]