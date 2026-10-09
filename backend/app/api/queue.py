"""Public queue status endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiException
from ..services import catalog_service, queue_service

router = APIRouter(prefix="/api", tags=["Queue"])


@router.get("/queue")
def queue_snapshot(
    office_id: int | None = Query(default=None),
    service_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    if service_id is None:
        service = catalog_service.first_service(db)
        if service is None:
            raise ApiException(404, "not_found", "No services configured. Run the seed script.")
        service_id = service.id
    context = catalog_service.service_with_context(db, service_id)
    if context is None or context["office"] is None:
        raise ApiException(404, "not_found", "Service not found.")
    resolved_office = office_id or context["office"]["id"]
    return queue_service.snapshot(db, resolved_office, service_id)