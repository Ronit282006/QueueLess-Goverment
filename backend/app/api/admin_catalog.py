"""Admin office and counter management.

Offices were previously created only through a minimal endpoint. This module
owns the full office lifecycle (create/list/detail/edit/activate) plus counter
lifecycle (create/edit/status/services) while reusing the existing ``Office``,
``Department``, ``Service``, ``Counter`` and ``CounterService`` models, the
queue engine and the audit log. Nothing here duplicates the queue, GPS or
no-show features — it only feeds them accurate, validated data.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiException
from ..models import (
    Counter,
    CounterService,
    CounterStatus,
    Department,
    Office,
    Service,
    StaffAssignment,
    Token,
    TokenStatus,
    User,
)
from ..realtime import hub
from ..security import require_admin
from ..services import audit_service, catalog_service, queue_service

router = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_admin)])

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[0-9+\-() ]{7,20}$")
_PIN_RE = re.compile(r"^\d{4,12}$")
_DAY_ALIASES = {
    "mon": "mon", "tue": "tue", "wed": "wed", "thu": "thu",
    "fri": "fri", "sat": "sat", "sun": "sun",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _queue_room(office_id: int, service_id: int) -> str:
    return f"queue:{office_id}:{service_id}"


def _publish_queue(office_id: int, service_ids: list[int]) -> None:
    for service_id in set(service_ids):
        hub.publish(_queue_room(office_id, service_id), {
            "type": "queue.updated", "office_id": office_id, "service_id": service_id,
        })


# ---------------------------------------------------------------------------
# Validation helpers (format checks the admin frontend also mirrors)
# ---------------------------------------------------------------------------
def _clean_time(value: str, field: str) -> str:
    value = (value or "").strip()
    if not _TIME_RE.match(value):
        raise ApiException(422, "invalid_time", f"{field} must be HH:MM (24-hour).", {"field": field})
    return value


def _clean_days(days) -> str:
    if isinstance(days, str):
        parts = [d.strip() for d in days.replace(";", ",").split(",")]
    else:
        parts = [str(d).strip() for d in (days or [])]
    normalised = []
    for part in parts:
        if not part:
            continue
        key = part[:3].lower()
        if key not in _DAY_ALIASES:
            raise ApiException(422, "invalid_working_days", "Working days contain an unknown day.", {"field": "working_days"})
        if _DAY_ALIASES[key] not in normalised:
            normalised.append(_DAY_ALIASES[key])
    if not normalised:
        raise ApiException(422, "invalid_working_days", "At least one working day is required.", {"field": "working_days"})
    return ",".join(normalised)


def _clean_email(value: str | None) -> str:
    value = (value or "").strip()
    if value and not _EMAIL_RE.match(value):
        raise ApiException(422, "invalid_email", "Enter a valid contact email address.", {"field": "contact_email"})
    return value


def _clean_phone(value: str | None) -> str:
    value = (value or "").strip()
    if value and not _PHONE_RE.match(value):
        raise ApiException(422, "invalid_phone", "Enter a valid contact phone number.", {"field": "contact_phone"})
    return value


def _clean_pincode(value: str | None) -> str:
    value = (value or "").strip()
    if value and not _PIN_RE.match(value):
        raise ApiException(422, "invalid_pincode", "PIN code must be 4-12 digits.", {"field": "pincode"})
    return value


def _clean_coords(latitude: float | None, longitude: float | None) -> tuple[float | None, float | None]:
    if latitude is not None and not (-90.0 <= latitude <= 90.0):
        raise ApiException(422, "invalid_latitude", "Latitude must be between -90 and 90.", {"field": "latitude"})
    if longitude is not None and not (-180.0 <= longitude <= 180.0):
        raise ApiException(422, "invalid_longitude", "Longitude must be between -180 and 180.", {"field": "longitude"})
    return latitude, longitude


# ---------------------------------------------------------------------------
# Office schemas
# ---------------------------------------------------------------------------
class OfficeIn(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=160)
    address: str = Field(default="", max_length=255)
    city: str = Field(default="", max_length=80)
    state: str = Field(default="", max_length=80)
    pincode: str = Field(default="", max_length=12)
    contact_email: str = Field(default="", max_length=160)
    contact_phone: str = Field(default="", max_length=32)
    description: str = Field(default="", max_length=400)
    open_time: str = Field(default="09:30", max_length=5)
    close_time: str = Field(default="18:00", max_length=5)
    working_days: list[str] = Field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri", "sat"])
    latitude: float | None = None
    longitude: float | None = None
    is_active: bool = True


class OfficeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    address: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=80)
    state: str | None = Field(default=None, max_length=80)
    pincode: str | None = Field(default=None, max_length=12)
    contact_email: str | None = Field(default=None, max_length=160)
    contact_phone: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=400)
    open_time: str | None = Field(default=None, max_length=5)
    close_time: str | None = Field(default=None, max_length=5)
    working_days: list[str] | None = None
    latitude: float | None = None
    longitude: float | None = None


class StatusIn(BaseModel):
    is_active: bool


# ---------------------------------------------------------------------------
# Office endpoints
# ---------------------------------------------------------------------------
def _office_admin_row(db: Session, office: Office) -> dict:
    services_count = db.scalar(
        select(func.count(Service.id))
        .join(Department, Service.department_id == Department.id)
        .where(Department.office_id == office.id, Service.is_active.is_(True))
    ) or 0
    counters_count = db.scalar(select(func.count(Counter.id)).where(Counter.office_id == office.id)) or 0
    active_counters = db.scalar(
        select(func.count(Counter.id)).where(
            Counter.office_id == office.id,
            Counter.status == CounterStatus.AVAILABLE.value,
        )
    ) or 0
    staff_count = db.scalar(
        select(func.count(func.distinct(StaffAssignment.user_id))).where(
            StaffAssignment.office_id == office.id,
            StaffAssignment.is_active.is_(True),
        )
    ) or 0
    return {
        "id": office.id,
        "code": office.code,
        "name": office.name,
        "address": office.address,
        "city": office.city,
        "state": office.state,
        "pincode": office.pincode,
        "contact_email": office.contact_email,
        "contact_phone": office.contact_phone,
        "description": office.description,
        "open_time": office.open_time,
        "close_time": office.close_time,
        "working_hours": office.working_hours,
        "working_days": office.working_days,
        "latitude": office.latitude,
        "longitude": office.longitude,
        "is_active": office.is_active,
        "has_coordinates": office.latitude is not None and office.longitude is not None,
        "services_count": services_count,
        "counters_count": counters_count,
        "active_counters_count": active_counters,
        "staff_count": staff_count,
    }


@router.get("/offices")
def list_admin_offices(
    search: str | None = Query(None, max_length=120),
    status: str | None = Query(None, pattern="^(active|inactive)$"),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(Office).order_by(Office.name, Office.id)
    if status == "active":
        stmt = stmt.where(Office.is_active.is_(True))
    elif status == "inactive":
        stmt = stmt.where(Office.is_active.is_(False))
    if search:
        term = f"%{search.strip().lower()}%"
        stmt = stmt.where(or_(
            func.lower(Office.code).like(term),
            func.lower(Office.name).like(term),
            func.lower(Office.city).like(term),
        ))
    return [_office_admin_row(db, o) for o in db.scalars(stmt).all()]


@router.post("/offices", status_code=201)
def create_office(body: OfficeIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    code = body.code.strip()
    name = body.name.strip()
    if not code or not name:
        raise ApiException(422, "validation_error", "Office code and name are required.")
    open_time = _clean_time(body.open_time, "open_time")
    close_time = _clean_time(body.close_time, "close_time")
    if open_time >= close_time:
        raise ApiException(422, "invalid_hours", "Opening time must be before closing time.", {"field": "close_time"})
    _clean_coords(body.latitude, body.longitude)
    if db.scalar(select(Office.id).where(func.lower(Office.code) == code.lower())):
        raise ApiException(409, "code_taken", "An office with this code already exists.")

    office = Office(
        code=code,
        name=name,
        address=body.address.strip(),
        city=body.city.strip(),
        state=body.state.strip(),
        pincode=_clean_pincode(body.pincode),
        contact_email=_clean_email(body.contact_email),
        contact_phone=_clean_phone(body.contact_phone),
        description=body.description.strip(),
        open_time=open_time,
        close_time=close_time,
        working_hours=f"{open_time}-{close_time}",
        working_days=_clean_days(body.working_days),
        latitude=body.latitude,
        longitude=body.longitude,
        is_active=body.is_active,
    )
    try:
        with db.begin_nested():
            db.add(office)
            db.flush()
    except IntegrityError:
        # A concurrent request created the same code first.
        raise ApiException(409, "code_taken", "An office with this code already exists.") from None

    audit_service.record(
        db, action="office.created", actor_id=admin.id, actor_role=admin.role,
        entity_type="office", entity_id=office.id, office_id=office.id,
        detail={"code": office.code, "name": office.name},
    )
    db.commit()
    catalog_service.invalidate_catalog()
    return _office_admin_row(db, office)


@router.get("/offices/{office_id}")
def office_detail(office_id: int, db: Session = Depends(get_db)) -> dict:
    office = db.get(Office, office_id)
    if office is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    return {**_office_admin_row(db, office), "metrics": _office_metrics(db, office)}


@router.patch("/offices/{office_id}")
def update_office(
    office_id: int, body: OfficeUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    office = db.get(Office, office_id)
    if office is None:
        raise ApiException(404, "office_not_found", "Office not found.")

    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        name = (data["name"] or "").strip()
        if len(name) < 2:
            raise ApiException(422, "validation_error", "Office name is too short.", {"field": "name"})
        office.name = name
    for field in ("address", "city", "state", "description"):
        if field in data and data[field] is not None:
            setattr(office, field, data[field].strip())
    if "pincode" in data:
        office.pincode = _clean_pincode(data["pincode"])
    if "contact_email" in data:
        office.contact_email = _clean_email(data["contact_email"])
    if "contact_phone" in data:
        office.contact_phone = _clean_phone(data["contact_phone"])
    if "working_days" in data and data["working_days"] is not None:
        office.working_days = _clean_days(data["working_days"])

    open_time = _clean_time(data["open_time"], "open_time") if data.get("open_time") else office.open_time
    close_time = _clean_time(data["close_time"], "close_time") if data.get("close_time") else office.close_time
    if open_time >= close_time:
        raise ApiException(422, "invalid_hours", "Opening time must be before closing time.", {"field": "close_time"})
    office.open_time = open_time
    office.close_time = close_time
    office.working_hours = f"{open_time}-{close_time}"

    if "latitude" in data or "longitude" in data:
        lat = data.get("latitude", office.latitude)
        lng = data.get("longitude", office.longitude)
        _clean_coords(lat, lng)
        office.latitude = lat
        office.longitude = lng

    audit_service.record(
        db, action="office.updated", actor_id=admin.id, actor_role=admin.role,
        entity_type="office", entity_id=office.id, office_id=office.id,
        detail={"fields": sorted(data.keys())},
    )
    db.commit()
    catalog_service.invalidate_catalog()
    return _office_admin_row(db, office)


@router.post("/offices/{office_id}/status")
def set_office_status(
    office_id: int, body: StatusIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    office = db.get(Office, office_id)
    if office is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    office.is_active = body.is_active
    audit_service.record(
        db, action="office.activated" if body.is_active else "office.deactivated",
        actor_id=admin.id, actor_role=admin.role,
        entity_type="office", entity_id=office.id, office_id=office.id,
    )
    db.commit()
    catalog_service.invalidate_catalog()
    return _office_admin_row(db, office)


@router.get("/offices/{office_id}/services")
def office_services(
    office_id: int,
    include_inactive: bool = Query(False, description="Include deactivated services."),
    db: Session = Depends(get_db),
) -> list[dict]:
    if db.get(Office, office_id) is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    stmt = (
        select(Service, Department, CounterService.counter_id)
        .join(Department, Service.department_id == Department.id)
        .outerjoin(CounterService, CounterService.service_id == Service.id)
        .where(Department.office_id == office_id)
        .order_by(Service.name, Service.id)
    )
    if not include_inactive:
        stmt = stmt.where(Service.is_active.is_(True))
    rows = db.execute(stmt).all()
    grouped: dict[int, dict] = {}
    for service, department, counter_id in rows:
        entry = grouped.setdefault(service.id, {
            "id": service.id,
            "code": service.code,
            "name": service.name,
            "description": service.description,
            "documents": service.documents,
            "average_service_min": service.average_service_min,
            "is_active": service.is_active,
            "department_id": department.id,
            "department_name": department.name,
            "counter_ids": [],
        })
        if counter_id is not None and counter_id not in entry["counter_ids"]:
            entry["counter_ids"].append(counter_id)
    return list(grouped.values())


# ---------------------------------------------------------------------------
# Office department & service management
# ---------------------------------------------------------------------------
def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug[:32] or "service"


def _unique_service_code(db: Session, base: str, *, exclude_id: int | None = None) -> str:
    root = _slugify(base)
    candidate = root
    counter = 1
    while True:
        stmt = select(Service.id).where(func.lower(Service.code) == candidate.lower())
        if exclude_id is not None:
            stmt = stmt.where(Service.id != exclude_id)
        if db.scalar(stmt) is None:
            return candidate
        counter += 1
        candidate = f"{root}-{counter}"[:40]


def _office_service_row(db: Session, service: Service) -> dict:
    department = service.department or db.get(Department, service.department_id)
    counter_ids = sorted(set(db.scalars(
        select(CounterService.counter_id).where(CounterService.service_id == service.id)
    ).all()))
    return {
        "id": service.id,
        "code": service.code,
        "name": service.name,
        "description": service.description,
        "documents": service.documents,
        "average_service_min": service.average_service_min,
        "is_active": service.is_active,
        "department_id": department.id if department else None,
        "department_name": department.name if department else "",
        "counter_ids": counter_ids,
    }


def _resolve_department(
    db: Session, office_id: int, *, department_id: int | None, department_name: str | None
) -> Department:
    if department_id is not None:
        department = db.get(Department, department_id)
        if department is None:
            raise ApiException(404, "department_not_found", "Department not found.")
        if department.office_id != office_id:
            raise ApiException(
                422, "department_not_in_office",
                "That department belongs to a different office.", {"field": "department_id"},
            )
        return department
    name = (department_name or "").strip() or "General"
    existing = db.scalar(
        select(Department).where(
            Department.office_id == office_id,
            func.lower(Department.name) == name.lower(),
        )
    )
    if existing is not None:
        return existing
    department = Department(office_id=office_id, name=name)
    db.add(department)
    db.flush()
    return department


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=400)


class ServiceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str | None = Field(default=None, max_length=40)
    description: str = Field(default="", max_length=2000)
    average_service_min: float = Field(default=6.2, gt=0, le=120)
    documents: list[str] = Field(default_factory=list)
    department_id: int | None = None
    department_name: str | None = Field(default=None, max_length=120)
    is_active: bool = True


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    average_service_min: float | None = Field(default=None, gt=0, le=120)
    documents: list[str] | None = None
    department_id: int | None = None
    is_active: bool | None = None


@router.get("/offices/{office_id}/departments")
def office_departments(office_id: int, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Office, office_id) is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    counts = dict(db.execute(
        select(Service.department_id, func.count(Service.id))
        .join(Department, Service.department_id == Department.id)
        .where(Department.office_id == office_id)
        .group_by(Service.department_id)
    ).all())
    departments = db.scalars(
        select(Department).where(Department.office_id == office_id).order_by(Department.name, Department.id)
    ).all()
    return [
        {
            "id": d.id,
            "name": d.name,
            "description": d.description,
            "is_active": d.is_active,
            "services_count": int(counts.get(d.id, 0)),
        }
        for d in departments
    ]


@router.post("/offices/{office_id}/departments", status_code=201)
def create_office_department(
    office_id: int, body: DepartmentCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    if db.get(Office, office_id) is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    name = body.name.strip()
    if db.scalar(select(Department.id).where(
        Department.office_id == office_id, func.lower(Department.name) == name.lower()
    )):
        raise ApiException(409, "department_exists", "A department with this name already exists in this office.")
    department = Department(office_id=office_id, name=name, description=body.description.strip())
    db.add(department)
    db.flush()
    audit_service.record(
        db, action="catalog.department_created", actor_id=admin.id, actor_role=admin.role,
        entity_type="department", entity_id=department.id, office_id=office_id, detail={"name": name},
    )
    db.commit()
    catalog_service.invalidate_catalog()
    return {"id": department.id, "name": department.name, "description": department.description, "is_active": department.is_active, "services_count": 0}


@router.post("/offices/{office_id}/services", status_code=201)
def create_office_service(
    office_id: int, body: ServiceCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    if db.get(Office, office_id) is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    name = body.name.strip()
    if not name:
        raise ApiException(422, "validation_error", "Service name is required.", {"field": "name"})
    department = _resolve_department(
        db, office_id, department_id=body.department_id, department_name=body.department_name
    )
    code = (body.code or "").strip()
    if code and db.scalar(select(Service.id).where(func.lower(Service.code) == code.lower())):
        raise ApiException(409, "service_code_taken", "A service with this code already exists.", {"field": "code"})
    if not code:
        code = _unique_service_code(db, name)

    service = Service(
        department_id=department.id,
        code=code,
        name=name,
        description=body.description.strip(),
        average_service_min=body.average_service_min,
        is_active=body.is_active,
    )
    service.documents = [d for d in body.documents if d and d.strip()]
    try:
        with db.begin_nested():
            db.add(service)
            db.flush()
    except IntegrityError:
        raise ApiException(409, "service_code_taken", "A service with this code already exists.", {"field": "code"}) from None

    audit_service.record(
        db, action="catalog.service_created", actor_id=admin.id, actor_role=admin.role,
        entity_type="service", entity_id=service.id, office_id=office_id,
        detail={"code": code, "name": name, "department_id": department.id},
    )
    db.commit()
    catalog_service.invalidate_catalog()
    return _office_service_row(db, service)


@router.patch("/services/{service_id}")
def update_service(
    service_id: int, body: ServiceUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    service = db.get(Service, service_id)
    if service is None:
        raise ApiException(404, "service_not_found", "Service not found.")
    current_department = service.department or db.get(Department, service.department_id)
    office_id = current_department.office_id if current_department else None
    data = body.model_dump(exclude_unset=True)

    if "name" in data and data["name"] is not None:
        name = data["name"].strip()
        if len(name) < 2:
            raise ApiException(422, "validation_error", "Service name is too short.", {"field": "name"})
        service.name = name
    if "description" in data and data["description"] is not None:
        service.description = data["description"].strip()
    if "average_service_min" in data and data["average_service_min"] is not None:
        service.average_service_min = data["average_service_min"]
    if "documents" in data and data["documents"] is not None:
        service.documents = [d for d in data["documents"] if d and d.strip()]
    if "is_active" in data and data["is_active"] is not None:
        service.is_active = data["is_active"]
    if "department_id" in data and data["department_id"] is not None:
        department = db.get(Department, data["department_id"])
        if department is None:
            raise ApiException(404, "department_not_found", "Department not found.")
        if office_id is not None and department.office_id != office_id:
            raise ApiException(
                422, "department_not_in_office",
                "That department belongs to a different office.", {"field": "department_id"},
            )
        service.department_id = department.id

    audit_service.record(
        db, action="catalog.service_updated", actor_id=admin.id, actor_role=admin.role,
        entity_type="service", entity_id=service.id, office_id=office_id,
        detail={"fields": sorted(data.keys())},
    )
    db.commit()
    catalog_service.invalidate_catalog()
    if office_id is not None:
        _publish_queue(office_id, [service.id])
    return _office_service_row(db, service)


# ---------------------------------------------------------------------------
# Counter schemas / endpoints
# ---------------------------------------------------------------------------
class CounterIn(BaseModel):
    number: int = Field(ge=1, le=9999)
    name: str = Field(default="", max_length=80)
    code: str | None = Field(default=None, max_length=40)
    description: str = Field(default="", max_length=300)
    status: str = Field(default=CounterStatus.AVAILABLE.value)
    service_ids: list[int] = Field(default_factory=list)


class CounterUpdate(BaseModel):
    number: int | None = Field(default=None, ge=1, le=9999)
    name: str | None = Field(default=None, max_length=80)
    code: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=300)
    status: str | None = None
    service_ids: list[int] | None = None


def _office_service_ids(db: Session, office_id: int) -> set[int]:
    return set(db.scalars(
        select(Service.id)
        .join(Department, Service.department_id == Department.id)
        .where(Department.office_id == office_id)
    ).all())


def _validate_counter_services(db: Session, office_id: int, service_ids: list[int]) -> list[int]:
    wanted = list(dict.fromkeys(service_ids))
    if not wanted:
        return []
    offered = _office_service_ids(db, office_id)
    unknown = [sid for sid in wanted if sid not in offered]
    if unknown:
        raise ApiException(
            422, "service_not_in_office",
            "One or more selected services are not offered by this office.",
            {"service_ids": unknown},
        )
    return wanted


def _counter_services_by_counter(db: Session, counter_ids: list[int]) -> dict[int, list[int]]:
    if not counter_ids:
        return {}
    rows = db.execute(
        select(CounterService.counter_id, CounterService.service_id).where(
            CounterService.counter_id.in_(counter_ids)
        )
    ).all()
    out: dict[int, list[int]] = {}
    for counter_id, service_id in rows:
        out.setdefault(counter_id, []).append(service_id)
    return out


def _counter_staff_by_counter(db: Session, office_id: int) -> dict[int, list[dict]]:
    rows = db.execute(
        select(StaffAssignment.counter_id, StaffAssignment.user_id, User.email, User.full_name)
        .join(User, User.id == StaffAssignment.user_id)
        .where(StaffAssignment.office_id == office_id, StaffAssignment.is_active.is_(True))
    ).all()
    out: dict[int, list[dict]] = {}
    for counter_id, user_id, email, full_name in rows:
        if counter_id is None:
            continue
        out.setdefault(counter_id, []).append({"user_id": user_id, "email": email, "full_name": full_name})
    return out


def _counter_row(counter: Counter, services: list[int], staff: list[dict]) -> dict:
    return {
        "id": counter.id,
        "office_id": counter.office_id,
        "number": counter.number,
        "code": counter.code,
        "name": counter.name,
        "description": counter.description,
        "status": counter.status,
        "is_active": counter.status != CounterStatus.OFFLINE.value,
        "service_ids": sorted(services),
        "staff": staff,
        "updated_at": counter.updated_at.isoformat() if counter.updated_at else None,
    }


def _counters_payload(db: Session, office_id: int) -> list[dict]:
    counters = list(db.scalars(
        select(Counter).where(Counter.office_id == office_id).order_by(Counter.number, Counter.id)
    ).all())
    services = _counter_services_by_counter(db, [c.id for c in counters])
    staff = _counter_staff_by_counter(db, office_id)
    return [_counter_row(c, services.get(c.id, []), staff.get(c.id, [])) for c in counters]


@router.get("/offices/{office_id}/counters")
def list_office_counters(office_id: int, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Office, office_id) is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    return _counters_payload(db, office_id)


@router.post("/offices/{office_id}/counters", status_code=201)
def create_counter(
    office_id: int, body: CounterIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    office = db.get(Office, office_id)
    if office is None:
        raise ApiException(404, "office_not_found", "Office not found.")
    if body.status not in {s.value for s in CounterStatus}:
        raise ApiException(422, "invalid_status", "Unknown counter status.", {"field": "status"})
    service_ids = _validate_counter_services(db, office_id, body.service_ids)
    code = (body.code or "").strip() or None

    if db.scalar(select(Counter.id).where(Counter.office_id == office_id, Counter.number == body.number)):
        raise ApiException(409, "counter_number_taken", "A counter with this number already exists in this office.")
    if code and db.scalar(select(Counter.id).where(Counter.office_id == office_id, Counter.code == code)):
        raise ApiException(409, "counter_code_taken", "A counter with this code already exists in this office.")

    counter = Counter(
        office_id=office_id, number=body.number, code=code, name=body.name.strip(),
        description=body.description.strip(), status=body.status,
    )
    try:
        with db.begin_nested():
            db.add(counter)
            db.flush()
    except IntegrityError:
        raise ApiException(409, "counter_conflict", "A counter with this number or code already exists.") from None
    for service_id in service_ids:
        db.add(CounterService(counter_id=counter.id, service_id=service_id))

    audit_service.record(
        db, action="counter.created", actor_id=admin.id, actor_role=admin.role,
        entity_type="counter", entity_id=counter.id, office_id=office_id,
        detail={"number": counter.number, "code": code, "service_ids": service_ids},
    )
    db.commit()
    catalog_service.invalidate_catalog()
    _publish_queue(office_id, service_ids)
    return _counter_row(counter, service_ids, [])


@router.patch("/counters/{counter_id}")
def update_counter(
    counter_id: int, body: CounterUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    counter = db.get(Counter, counter_id)
    if counter is None:
        raise ApiException(404, "counter_not_found", "Counter not found.")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] is not None:
        if data["status"] not in {s.value for s in CounterStatus}:
            raise ApiException(422, "invalid_status", "Unknown counter status.", {"field": "status"})
        counter.status = data["status"]
    if "name" in data and data["name"] is not None:
        counter.name = data["name"].strip()
    if "description" in data and data["description"] is not None:
        counter.description = data["description"].strip()
    if "number" in data and data["number"] is not None and data["number"] != counter.number:
        if db.scalar(select(Counter.id).where(
            Counter.office_id == counter.office_id, Counter.number == data["number"], Counter.id != counter.id
        )):
            raise ApiException(409, "counter_number_taken", "A counter with this number already exists in this office.")
        counter.number = data["number"]
    if "code" in data:
        code = (data["code"] or "").strip() or None
        if code and code != counter.code and db.scalar(select(Counter.id).where(
            Counter.office_id == counter.office_id, Counter.code == code, Counter.id != counter.id
        )):
            raise ApiException(409, "counter_code_taken", "A counter with this code already exists in this office.")
        counter.code = code

    service_ids: list[int] | None = None
    if "service_ids" in data and data["service_ids"] is not None:
        service_ids = _validate_counter_services(db, counter.office_id, data["service_ids"])
        db.execute(CounterService.__table__.delete().where(CounterService.counter_id == counter.id))
        db.flush()
        for service_id in service_ids:
            db.add(CounterService(counter_id=counter.id, service_id=service_id))

    try:
        db.flush()
    except IntegrityError:
        raise ApiException(409, "counter_conflict", "A counter with this number or code already exists.") from None

    audit_service.record(
        db, action="counter.updated", actor_id=admin.id, actor_role=admin.role,
        entity_type="counter", entity_id=counter.id, office_id=counter.office_id,
        detail={"fields": sorted(data.keys())},
    )
    db.commit()
    catalog_service.invalidate_catalog()
    _publish_queue(counter.office_id, service_ids if service_ids is not None else _counter_services_by_counter(db, [counter.id]).get(counter.id, []))
    return _counter_row(counter, _counter_services_by_counter(db, [counter.id]).get(counter.id, []), _counter_staff_by_counter(db, counter.office_id).get(counter.id, []))


class CounterStatusIn(BaseModel):
    status: str


@router.post("/counters/{counter_id}/status")
def set_counter_status(
    counter_id: int, body: CounterStatusIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    counter = db.get(Counter, counter_id)
    if counter is None:
        raise ApiException(404, "counter_not_found", "Counter not found.")
    if body.status not in {s.value for s in CounterStatus}:
        raise ApiException(422, "invalid_status", "Unknown counter status.", {"field": "status"})
    counter.status = body.status
    audit_service.record(
        db, action="counter.status_changed", actor_id=admin.id, actor_role=admin.role,
        entity_type="counter", entity_id=counter.id, office_id=counter.office_id,
        detail={"status": body.status},
    )
    db.commit()
    catalog_service.invalidate_catalog()
    _publish_queue(counter.office_id, _counter_services_by_counter(db, [counter.id]).get(counter.id, []))
    return _counter_row(counter, _counter_services_by_counter(db, [counter.id]).get(counter.id, []), _counter_staff_by_counter(db, counter.office_id).get(counter.id, []))


# ---------------------------------------------------------------------------
# Office metrics (overview / queue / today)
# ---------------------------------------------------------------------------
def _office_metrics(db: Session, office: Office) -> dict:
    services = db.execute(
        select(Service.id, Service.name)
        .join(Department, Service.department_id == Department.id)
        .where(Department.office_id == office.id, Service.is_active.is_(True))
    ).all()
    total_waiting = 0
    active_counters = 0
    for service_id, _name in services:
        eta = queue_service.service_eta(db, office.id, service_id)
        total_waiting += eta.get("waiting", 0)
        active_counters += eta.get("active_counters", 0)

    start_of_day = datetime.combine(_now().date(), datetime.min.time(), tzinfo=timezone.utc)
    today_created = db.scalar(select(func.count(Token.id)).where(
        Token.office_id == office.id, Token.created_at >= start_of_day
    )) or 0
    today_completed = db.scalar(select(func.count(Token.id)).where(
        Token.office_id == office.id, Token.status == TokenStatus.COMPLETED.value, Token.completed_at >= start_of_day
    )) or 0
    today_cancelled = db.scalar(select(func.count(Token.id)).where(
        Token.office_id == office.id, Token.status == TokenStatus.CANCELLED.value, Token.created_at >= start_of_day
    )) or 0

    staff_count = db.scalar(
        select(func.count(func.distinct(StaffAssignment.user_id))).where(
            StaffAssignment.office_id == office.id, StaffAssignment.is_active.is_(True)
        )
    ) or 0
    counters_count = db.scalar(select(func.count(Counter.id)).where(Counter.office_id == office.id)) or 0

    return {
        "services_count": len(services),
        "counters_count": counters_count,
        "active_counters_count": active_counters,
        "staff_count": staff_count,
        "queue_length": total_waiting,
        "today": {
            "tokens_created": today_created,
            "tokens_completed": today_completed,
            "tokens_cancelled": today_cancelled,
        },
    }
