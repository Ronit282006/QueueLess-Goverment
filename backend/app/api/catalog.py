"""Office / department / service catalog endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiException
from ..services import catalog_service, prediction_service, queue_service

router = APIRouter(prefix="/api", tags=["Services"])


@router.get("/offices")
def list_offices(db: Session = Depends(get_db)) -> list[dict]:
    return catalog_service.list_offices(db)


@router.get("/services/{service_id}")
def service_detail(service_id: int, db: Session = Depends(get_db)) -> dict:
    context = catalog_service.service_with_context(db, service_id)
    if context is None or context["office"] is None:
        raise ApiException(404, "not_found", "Service not found.")
    office = context["office"]
    snap = queue_service.snapshot(db, office["id"], service_id, with_tokens=False)
    pred = snap["prediction"]
    return {
        **context,
        "current_queue": snap["waiting"],
        "active_counters": snap["active_counters"],
        "average_service_min": snap["average_service_min"],
        "estimated_wait_min": pred["minutes"],
        "estimated_wait_low_min": pred["minutes_low"],
        "estimated_wait_high_min": pred["minutes_high"],
        "confidence": pred["confidence"],
        "prediction": pred,
        "required_documents": context["service"]["documents"],
    }