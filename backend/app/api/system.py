"""System health endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..services.cache_service import get_redis

router = APIRouter(prefix="/api", tags=["System"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        database = "up"
    except Exception:
        database = "down"
    redis = "up" if get_redis() is not None else "unavailable (degraded mode)"
    return {
        "status": "ok" if database == "up" else "degraded",
        "database": database,
        "redis": redis,
        "worker": "unknown",
        "email_mode": settings.email_mode,
        "version": "1.0.0",
        "time": datetime.now(timezone.utc).isoformat(),
    }