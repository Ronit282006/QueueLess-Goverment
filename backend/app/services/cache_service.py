"""Redis client used for caching, pub/sub, rate limiting and the email queue.

Redis is treated as an optimisation, not a hard dependency: every call site
degrades gracefully when it is unavailable (the app still works on PostgreSQL).
"""
from __future__ import annotations

import logging
from functools import lru_cache

from ..config import get_settings

logger = logging.getLogger("queueless.cache")


@lru_cache
def get_redis():  # noqa: ANN201
    """Return a Redis client or None when Redis is not reachable."""
    try:
        import redis

        client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=1)
        client.ping()
        return client
    except Exception as exc:  # pragma: no cover - depends on environment
        logger.warning("Redis unavailable (%s); continuing without cache/pubsub", exc)
        return None


def cache_get(key: str) -> str | None:
    client = get_redis()
    if client is None:
        return None
    try:
        return client.get(key)
    except Exception:
        return None


def cache_set(key: str, value: str, ttl: int = 5) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.setex(key, ttl, value)
    except Exception:
        pass


def cache_delete(*keys: str) -> None:
    client = get_redis()
    if client is None or not keys:
        return
    try:
        client.delete(*keys)
    except Exception:
        pass


def publish(channel: str, payload: str) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.publish(channel, payload)
    except Exception:
        pass