"""Audit logging for staff/admin actions (spec section 41)."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from ..models import AuditLog


def record(
    db: Session,
    *,
    action: str,
    actor_id: int | None = None,
    actor_role: str = "SYSTEM",
    entity_type: str = "",
    entity_id: str | int = "",
    office_id: int | None = None,
    detail: dict | None = None,
    request_id: str = "",
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        office_id=office_id,
        detail_json=json.dumps(detail or {}, ensure_ascii=False),
        request_id=request_id,
    )
    db.add(entry)
    db.flush()
    return entry