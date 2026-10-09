"""Distributed rate limiting backed by Redis (fails open when Redis is down)."""
from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import Request

from ..config import get_settings
from ..errors import ApiException
from .cache_service import get_redis


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str, limit: int, window_seconds: int = 60) -> Callable:
    """Dependency enforcing `limit` requests per `window_seconds` per client IP."""

    async def dependency(request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return
        redis = get_redis()
        if redis is None:
            # Fail open: never take the portal down because Redis is unavailable.
            return
        key = f"ql:rl:{scope}:{client_ip(request)}"
        try:
            count = redis.incr(key)
            if count == 1:
                redis.expire(key, window_seconds)
            if count > limit:
                ttl = redis.ttl(key)
                retry_after = ttl if isinstance(ttl, int) and ttl > 0 else window_seconds
                raise ApiException(
                    429,
                    "rate_limited",
                    "Too many requests. Please slow down and try again shortly.",
                    {"limit": limit, "window_seconds": window_seconds, "retry_after": retry_after},
                    headers={"Retry-After": str(retry_after)},
                )
        except ApiException:
            raise
        except Exception:
            return

    return dependency


def record_request_metric(path: str) -> None:
    """Lightweight per-minute request counter used by the health dashboard."""
    redis = get_redis()
    if redis is None:
        return
    minute = int(time.time() // 60)
    try:
        key = f"ql:metrics:rpm:{minute}:{path}"
        redis.incr(key)
        redis.expire(key, 120)
    except Exception:
        pass