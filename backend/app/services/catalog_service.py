"""Catalog queries (offices, departments, services)."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Department, Office, Service
from .cache_service import cache_delete, cache_get, cache_set

_CACHE_KEY_OFFICES = "ql:cat:offices"
_CATALOG_TTL_SECONDS = 15


def _service_row(service: Service) -> dict:
    return {
        "id": service.id,
        "code": service.code,
        "name": service.name,
        "description": service.description,
        "documents": list(service.documents),
        "average_service_min": service.average_service_min,
        "is_active": service.is_active,
    }


def _department_row(db: Session, department: Department) -> dict:
    services = db.scalars(
        select(Service)
        .where(Service.department_id == department.id, Service.is_active.is_(True))
        .order_by(Service.name)
    ).all()
    return {
        "id": department.id,
        "name": department.name,
        "description": department.description,
        "services": [_service_row(s) for s in services],
    }


def _office_row(db: Session, office: Office) -> dict:
    departments = db.scalars(
        select(Department)
        .where(Department.office_id == office.id, Department.is_active.is_(True))
        .order_by(Department.id)
    ).all()
    return {
        "id": office.id,
        "code": office.code,
        "name": office.name,
        "address": office.address,
        "location_instructions": office.location_instructions,
        "working_hours": office.working_hours,
        "working_days": office.working_days,
        "sla_target_wait_min": office.sla_target_wait_min,
        "no_show_grace_min": office.no_show_grace_min,
        "eta_alert_threshold_min": office.eta_alert_threshold_min,
        "arrival_buffer_min": office.arrival_buffer_min,
        "incident_response_min": office.incident_response_min,
        "departments": [_department_row(db, d) for d in departments],
    }


def list_offices(db: Session) -> list[dict]:
    cached = cache_get(_CACHE_KEY_OFFICES)
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            pass
    offices = db.scalars(
        select(Office).where(Office.is_active.is_(True)).order_by(Office.id)
    ).all()
    payload = [_office_row(db, office) for office in offices]
    cache_set(_CACHE_KEY_OFFICES, json.dumps(payload, default=str), ttl=10)
    return payload


def invalidate_catalog() -> None:
    """Drop cached catalog views after any admin catalog mutation."""
    cache_delete(_CACHE_KEY_OFFICES)


def get_service(db: Session, service_id: int) -> Service | None:
    return db.get(Service, service_id)


def office_for_service(db: Session, service_id: int) -> Office | None:
    service = db.get(Service, service_id)
    if service is None:
        return None
    department = db.get(Department, service.department_id)
    if department is None:
        return None
    return db.get(Office, department.office_id)


def service_with_context(db: Session, service_id: int) -> dict | None:
    service = db.get(Service, service_id)
    if service is None:
        return None
    department = db.get(Department, service.department_id)
    office = db.get(Office, department.office_id) if department else None
    return {
        "service": _service_row(service),
        "department": {
            "id": department.id,
            "name": department.name,
            "description": department.description,
        }
        if department
        else None,
        "office": {
            "id": office.id,
            "code": office.code,
            "name": office.name,
            "address": office.address,
            "location_instructions": office.location_instructions,
            "working_hours": office.working_hours,
            "working_days": office.working_days,
            "sla_target_wait_min": office.sla_target_wait_min,
            "no_show_grace_min": office.no_show_grace_min,
            "eta_alert_threshold_min": office.eta_alert_threshold_min,
            "arrival_buffer_min": office.arrival_buffer_min,
            "incident_response_min": office.incident_response_min,
        }
        if office
        else None,
    }


def first_service(db: Session) -> Service | None:
    return db.scalar(
        select(Service)
        .join(Department)
        .join(Office)
        .where(Service.is_active.is_(True), Office.is_active.is_(True))
        .order_by(Service.id)
    )
