"""Smart-arrival endpoints: travel estimates, office recommendations, guidance.

These endpoints only ever receive a citizen's coordinates for the duration of a
single request (or a single reminder calculation). Coordinates are never stored
on the token and are never exposed to staff dashboards.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiException
from ..models import Office, Token
from ..services import arrival_service, routing_service

router = APIRouter(prefix="/api/arrival", tags=["Smart arrival"])


@router.get("/config")
def arrival_config() -> dict:
    """Expose non-secret routing configuration to the frontend."""
    return routing_service.provider_info()


@router.get("/offices")
def recommend_offices(
    service_id: int = Query(...),
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    mode: str | None = Query(default=None),
    selected_office_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    origin = routing_service.require_coords(lat, lng)
    result = arrival_service.recommend_offices(
        db, service_id, origin, mode=mode, selected_office_id=selected_office_id
    )
    result["origin"] = {"latitude": lat, "longitude": lng}
    return result


@router.get("/route")
def route_estimate(
    office_id: int = Query(...),
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    mode: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    office = db.get(Office, office_id)
    if office is None:
        raise ApiException(404, "not_found", "Office not found.")
    origin = routing_service.require_coords(lat, lng)
    if not routing_service.valid_coords(office.latitude, office.longitude):
        return {
            "available": False,
            "office_id": office.id,
            "message": "This office has no location set yet.",
            "travel": None,
        }
    route = routing_service.estimate_route(origin, (office.latitude, office.longitude), mode=mode)
    return {"available": route.available, "office_id": office.id, "office_name": office.name, "travel": route.as_dict()}


@router.get("/tokens/{reference}")
def token_guidance(
    reference: str,
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    mode: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    token = db.scalar(select(Token).where(Token.reference == reference))
    if token is None:
        raise ApiException(404, "not_found", "Token not found.")
    origin = routing_service.require_coords(lat, lng)
    return arrival_service.departure_guidance(db, token, origin, mode=mode)


@router.post("/tokens/{reference}/reminder")
def schedule_reminder(
    reference: str,
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    mode: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """(Re)schedule the "time to leave" reminder and store travel metadata."""
    token = db.scalar(select(Token).where(Token.reference == reference))
    if token is None:
        raise ApiException(404, "not_found", "Token not found.")
    origin = routing_service.require_coords(lat, lng)
    guidance = arrival_service.departure_guidance(db, token, origin, mode=mode)
    travel = guidance.get("travel") or {}
    if travel.get("available"):
        token.travel_min = travel.get("duration_min")
        token.travel_distance_km = travel.get("distance_km")
        token.travel_mode = guidance.get("mode", "")
        token.travel_provider = travel.get("provider", "")
        from datetime import datetime, timezone

        token.travel_calculated_at = datetime.now(timezone.utc)
    reminder = arrival_service.schedule_departure_reminder(db, token, origin, mode=mode)
    db.commit()
    return {
        "guidance": guidance,
        "reminder": {
            "scheduled": reminder is not None,
            "due_at": reminder.due_at.isoformat() if reminder and reminder.due_at else None,
            "status": reminder.status if reminder else None,
        },
    }
