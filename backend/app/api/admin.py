"""Administration: catalog management, priority rules, recommendations, audit, health."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiException
from ..ml import model as ml_model
from ..models import (
    AuditLog,
    Counter,
    CounterRecommendation,
    CounterService,
    Department,
    Notification,
    Office,
    PriorityRule,
    Service,
    Token,
    TokenStatus,
    User,
)
from ..models.enums import NotificationStatus, RecommendationStatus
from ..security import require_admin
from ..services import audit_service, catalog_service, queue_service
from ..services.cache_service import get_redis
from ..services.token_service import ACTIVE_STATUSES

router = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


# ---------------------------------------------------------------------------
# Health & observability
# ---------------------------------------------------------------------------
@router.get("/health")
def admin_health(admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    active_queues = db.scalar(
        select(func.count(func.distinct(Token.service_id))).where(Token.status.in_(ACTIVE_STATUSES))
    )
    pending_recommendations = db.scalar(
        select(func.count()).select_from(CounterRecommendation).where(
            CounterRecommendation.status == RecommendationStatus.PENDING.value
        )
    )
    queued_notifications = db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.status == NotificationStatus.QUEUED.value
        )
    )
    return {
        "status": "ok",
        "database": "up",
        "redis": "up" if get_redis() is not None else "unavailable (degraded mode)",
        "active_queues": int(active_queues or 0),
        "pending_recommendations": int(pending_recommendations or 0),
        "queued_notifications": int(queued_notifications or 0),
        "models": ml_model.loaded_models(),
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/audit-logs")
def audit_logs(
    office_id: int | None = None,
    action: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if office_id is not None:
        stmt = stmt.where(AuditLog.office_id == office_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return [
        {
            "id": row.id,
            "action": row.action,
            "actor_id": row.actor_id,
            "actor_role": row.actor_role,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "office_id": row.office_id,
            "detail": row.detail,
            "request_id": row.request_id,
            "at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in db.scalars(stmt).all()
    ]


# ---------------------------------------------------------------------------
# Priority rules
# ---------------------------------------------------------------------------
class PriorityRuleIn(BaseModel):
    office_id: int | None = None
    name: str = Field(min_length=2, max_length=120)
    tags: list[str] = Field(default_factory=list)
    boost: int = Field(default=10, ge=1, le=100)
    is_active: bool = True


@router.get("/priority-rules")
def list_priority_rules(office_id: int | None = None, db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(PriorityRule).order_by(PriorityRule.id)
    if office_id is not None:
        stmt = stmt.where((PriorityRule.office_id == office_id) | (PriorityRule.office_id.is_(None)))
    return [_rule_row(r) for r in db.scalars(stmt).all()]


@router.post("/priority-rules", status_code=201)
def create_priority_rule(body: PriorityRuleIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    rule = PriorityRule(
        office_id=body.office_id,
        name=body.name,
        required_tags=",".join(sorted({t.strip().lower() for t in body.tags if t.strip()})),
        boost=body.boost,
        is_active=body.is_active,
    )
    db.add(rule)
    db.flush()
    audit_service.record(db, action="priority_rule.created", actor_id=admin.id, actor_role=admin.role,
                         entity_type="priority_rule", entity_id=rule.id, office_id=body.office_id,
                         detail={"name": body.name, "boost": body.boost})
    db.commit()
    return _rule_row(rule)


@router.patch("/priority-rules/{rule_id}")
def update_priority_rule(rule_id: int, body: PriorityRuleIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    rule = db.get(PriorityRule, rule_id)
    if rule is None:
        raise ApiException(404, "not_found", "Priority rule not found.")
    rule.name = body.name
    rule.office_id = body.office_id
    rule.required_tags = ",".join(sorted({t.strip().lower() for t in body.tags if t.strip()}))
    rule.boost = body.boost
    rule.is_active = body.is_active
    audit_service.record(db, action="priority_rule.updated", actor_id=admin.id, actor_role=admin.role,
                         entity_type="priority_rule", entity_id=rule.id, office_id=rule.office_id)
    db.commit()
    return _rule_row(rule)


# ---------------------------------------------------------------------------
# Counter recommendations
# ---------------------------------------------------------------------------
@router.get("/recommendations")
def recommendations(
    office_id: int | None = None,
    refresh: bool = False,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    resolved = office_id or admin.office_id or db.scalar(select(Office.id).order_by(Office.id))
    if resolved is None:
        raise ApiException(404, "not_found", "No office found.")
    created = generate_recommendations(db, resolved, admin) if refresh else []
    rows = db.scalars(
        select(CounterRecommendation)
        .where(
            CounterRecommendation.office_id == resolved,
            CounterRecommendation.status == RecommendationStatus.PENDING.value,
        )
        .order_by(CounterRecommendation.created_at.desc())
    ).all()
    return {"generated": len(created), "items": [_recommendation_row(r) for r in rows]}


@router.post("/recommendations/{recommendation_id}/decide")
def decide_recommendation(
    recommendation_id: int,
    status: str = Query(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        decision = RecommendationStatus(status)
    except ValueError as exc:
        raise ApiException(400, "invalid_status", "Status must be ACCEPTED or REJECTED.") from exc
    if decision is RecommendationStatus.PENDING:
        raise ApiException(400, "invalid_status", "Status must be ACCEPTED or REJECTED.")
    rec = db.get(CounterRecommendation, recommendation_id)
    if rec is None:
        raise ApiException(404, "not_found", "Recommendation not found.")
    rec.status = decision.value
    rec.decided_at = datetime.now(timezone.utc)
    rec.decided_by = admin.id
    audit_service.record(db, action=f"recommendation.{decision.value.lower()}", actor_id=admin.id,
                         actor_role=admin.role, entity_type="recommendation", entity_id=rec.id,
                         office_id=rec.office_id, detail={"title": rec.title})
    db.commit()
    return _recommendation_row(rec)


def generate_recommendations(db: Session, office_id: int, admin: User) -> list[CounterRecommendation]:
    """Suggest counter reallocations from idle services to overloaded ones."""
    services = db.scalars(
        select(Service).join(Service.department).where(Service.department.has(office_id=office_id))
    ).all()
    stats = [_service_stats(db, office_id, service) for service in services]
    if not stats:
        return []
    return _generate_clean(db, office_id, admin, stats)


def _generate_clean(db: Session, office_id: int, admin: User, stats: list[dict]) -> list[CounterRecommendation]:
    hot = sorted([s for s in stats if s["load"] >= 3 and s["waiting"] >= 6], key=lambda s: s["load"], reverse=True)
    cold = sorted(stats, key=lambda s: s["load"])
    created: list[CounterRecommendation] = []
    for target in hot[:3]:
        pending = db.scalar(
            select(CounterRecommendation).where(
                CounterRecommendation.to_service_id == target["service"].id,
                CounterRecommendation.status == RecommendationStatus.PENDING.value,
            )
        )
        if pending is not None:
            continue
        donor = next(
            (s for s in cold if s["service"].id != target["service"].id and s["load"] < 1.0 and s["counters"] >= 2),
            None,
        )
        title = (
            f"Move one counter to {target['service'].name}"
            if donor is not None
            else f"Assign another counter to {target['service'].name}"
        )
        rec = CounterRecommendation(
            office_id=office_id,
            from_service_id=donor["service"].id if donor else None,
            to_service_id=target["service"].id,
            title=title,
            detail_json=json.dumps(
                {
                    "waiting": target["waiting"],
                    "counters": target["counters"],
                    "load_ratio": round(target["load"], 2),
                    "donor": donor["service"].name if donor else None,
                }
            ),
            expected_reduction_min=round(
                expected_reduction_minutes(db, target["service"].id, target["waiting"], target["counters"]), 1
            ),
            status=RecommendationStatus.PENDING.value,
        )
        db.add(rec)
        created.append(rec)
        audit_service.record(
            db, action="recommendation.generated", actor_id=admin.id, actor_role=admin.role,
            entity_type="recommendation", office_id=office_id, detail={"title": title},
        )
    db.commit()
    return created


def _service_stats(db: Session, office_id: int, service: Service) -> dict:
    waiting = db.scalar(
        select(func.count()).select_from(Token).where(
            Token.service_id == service.id,
            Token.office_id == office_id,
            Token.status.in_(ACTIVE_STATUSES),
        )
    ) or 0
    counters = db.scalar(
        select(func.count(func.distinct(CounterService.counter_id))).where(
            CounterService.service_id == service.id
        )
    ) or 0
    if not counters:
        counters = db.scalar(select(func.count()).select_from(Counter).where(Counter.office_id == office_id)) or 1
    return {
        "service": service,
        "waiting": int(waiting),
        "counters": int(counters),
        "load": waiting / max(1, counters),
    }


def service_avg(db: Session, service_id: int) -> float:
    from ..services import prediction_service

    measured, _ = prediction_service.observed_service_minutes(db, service_id)
    if measured:
        return measured
    service = db.get(Service, service_id)
    return service.average_service_min if service else 6.2


def expected_reduction_minutes(db: Session, service_id: int, waiting: int, counters: int) -> float:
    avg = service_avg(db, service_id)
    before = waiting / max(1, counters) * avg
    after = waiting / max(1, counters + 1) * avg
    return max(0.0, before - after)


# ---------------------------------------------------------------------------
# Catalog management
# ---------------------------------------------------------------------------
class OfficeIn(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    address: str = ""


class DepartmentIn(BaseModel):
    office_id: int
    name: str = Field(min_length=2, max_length=120)


class ServiceIn(BaseModel):
    department_id: int
    code: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=2, max_length=120)
    description: str = ""
    average_service_min: float = Field(default=6.2, gt=0, le=120)
    documents: list[str] = Field(default_factory=list)


class ServicePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    average_service_min: float | None = Field(default=None, gt=0, le=120)
    documents: list[str] | None = None
    is_active: bool | None = None


@router.post("/offices", status_code=201)
def create_office(body: OfficeIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(Office).where(Office.code == body.code)):
        raise ApiException(409, "code_taken", "An office with this code already exists.")
    office = Office(code=body.code, name=body.name, address=body.address)
    db.add(office)
    db.flush()
    audit_service.record(db, action="catalog.office_created", actor_id=admin.id, actor_role=admin.role,
                         entity_type="office", entity_id=office.id, detail={"code": body.code})
    db.commit()
    catalog_service.invalidate_catalog()
    return {"id": office.id, "code": office.code, "name": office.name}


@router.post("/departments", status_code=201)
def create_department(body: DepartmentIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    if db.get(Office, body.office_id) is None:
        raise ApiException(404, "not_found", "Office not found.")
    department = Department(office_id=body.office_id, name=body.name)
    db.add(department)
    db.flush()
    audit_service.record(db, action="catalog.department_created", actor_id=admin.id, actor_role=admin.role,
                         entity_type="department", entity_id=department.id, office_id=body.office_id)
    db.commit()
    catalog_service.invalidate_catalog()
    return {"id": department.id, "office_id": department.office_id, "name": department.name}


@router.post("/services", status_code=201)
def create_service(body: ServiceIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    if db.get(Department, body.department_id) is None:
        raise ApiException(404, "not_found", "Department not found.")
    service = Service(
        department_id=body.department_id,
        code=body.code,
        name=body.name,
        description=body.description,
        average_service_min=body.average_service_min,
    )
    service.documents = body.documents
    db.add(service)
    db.flush()
    audit_service.record(db, action="catalog.service_created", actor_id=admin.id, actor_role=admin.role,
                         entity_type="service", entity_id=service.id)
    db.commit()
    catalog_service.invalidate_catalog()
    return {"id": service.id, "code": service.code, "name": service.name}


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
@router.get("/notifications")
def list_notifications(limit: int = Query(50, ge=1, le=200), office_id: int | None = None, db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(Notification).order_by(Notification.created_at.desc()).limit(limit)
    if office_id is not None:
        stmt = stmt.where(Notification.office_id == office_id)
    return [
        {
            "id": n.id,
            "kind": n.kind,
            "subject": n.subject,
            "recipient": n.recipient,
            "status": n.status,
            "attempts": n.attempts,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "sent_at": n.sent_at.isoformat() if n.sent_at else None,
        }
        for n in db.scalars(stmt).all()
    ]


@router.post("/models/retrain")
def retrain_models(admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    from ..ml.train import train_all

    results = train_all()
    audit_service.record(db, action="models.retrained", actor_id=admin.id, actor_role=admin.role,
                         entity_type="model", detail={"count": len(results)})
    db.commit()
    return {"trained": len([r for r in results if r["status"] == "trained"]), "results": results}


# ---------------------------------------------------------------------------
# Row serialisers
# ---------------------------------------------------------------------------
def _rule_row(rule: PriorityRule) -> dict:
    return {
        "id": rule.id,
        "office_id": rule.office_id,
        "name": rule.name,
        "tags": rule.tags,
        "boost": rule.boost,
        "is_active": rule.is_active,
    }


def _recommendation_row(rec: CounterRecommendation) -> dict:
    return {
        "id": rec.id,
        "office_id": rec.office_id,
        "to_service_id": rec.to_service_id,
        "from_service_id": rec.from_service_id,
        "title": rec.title,
        "detail": rec.detail,
        "expected_reduction_min": rec.expected_reduction_min,
        "status": rec.status,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }