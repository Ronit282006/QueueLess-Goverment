"""Travel-time / routing abstraction for smart arrival.

This module isolates *how* a travel estimate is produced from the rest of the
application. Providers:

* ``mock``  — an offline, clearly-labelled estimator (road-distance detour
  factor applied to haversine distance at a mode-specific average speed). It
  never pretends to be a live route; every response is tagged ``provider=mock``.
* ``osrm``  — a self-hostable OpenStreetMap routing engine (also exposed as a
  public demo endpoint for local development). The provider URL is configurable
  and is *not* treated as an unlimited production service; failures simply
  degrade to an "unavailable" result.
* ``none``  — travel estimates disabled; the API reports them as unavailable.

Straight-line distance is never silently returned as a road travel time: when a
real provider cannot answer, callers get ``available=False`` and can tell the
citizen honestly.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from ..config import get_settings
from ..errors import ApiException
from .cache_service import cache_get, cache_set

logger = logging.getLogger("queueless.routing")

# Straight-line distance is multiplied by this factor to approximate road
# distance for the offline estimator. Documented so it is never mistaken for a
# surveyed route.
_MOCK_ROAD_DETOUR_FACTOR = 1.35
_MOCK_SPEED_KMH = {
    "driving": 30.0,
    "cycling": 14.0,
    "walking": 4.8,
}
_VALID_MODES = {"driving", "walking", "cycling"}

# Cache results briefly so repeated UI polling does not hammer the provider.
_CACHE_KEY_PREFIX = "ql:route:"
_MEM_TTL = 300.0
_MEM_LOCK = threading.Lock()
_MEM_CACHE: dict[str, tuple[float, "RouteEstimate"]] = {}


@dataclass
class RouteEstimate:
    available: bool
    provider: str
    mode: str
    status: str  # "ok" | "mock" | "unavailable"
    distance_km: float | None
    duration_min: float | None
    message: str
    calculated_at: datetime

    def as_dict(self) -> dict:
        data = asdict(self)
        data["calculated_at"] = self.calculated_at.isoformat()
        return data


def _now() -> datetime:
    return datetime.now(timezone.utc)


def valid_coords(latitude: float | None, longitude: float | None) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and -90.0 <= latitude <= 90.0
        and -180.0 <= longitude <= 180.0
        and not (latitude == 0.0 and longitude == 0.0)
    )


def require_coords(latitude: float | None, longitude: float | None) -> tuple[float, float]:
    if not valid_coords(latitude, longitude):
        raise ApiException(
            400,
            "invalid_location",
            "A valid latitude/longitude is required for travel estimates.",
        )
    return float(latitude), float(longitude)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def normalise_mode(mode: str | None) -> str:
    candidate = (mode or get_settings().default_travel_mode or "driving").lower()
    return candidate if candidate in _VALID_MODES else "driving"


def _cache_key(provider: str, mode: str, o: tuple[float, float], d: tuple[float, float]) -> str:
    return f"{_CACHE_KEY_PREFIX}{provider}:{mode}:{o[0]:.4f},{o[1]:.4f}:{d[0]:.4f},{d[1]:.4f}"


def _mem_get(key: str) -> RouteEstimate | None:
    with _MEM_LOCK:
        hit = _MEM_CACHE.get(key)
        if hit is None:
            return None
        expires, value = hit
        if expires < time.monotonic():
            _MEM_CACHE.pop(key, None)
            return None
        return value


def _mem_set(key: str, value: RouteEstimate, ttl: float) -> None:
    with _MEM_LOCK:
        # Opportunistic pruning keeps the fallback cache bounded.
        if len(_MEM_CACHE) > 2048:
            now = time.monotonic()
            for k in [k for k, (exp, _) in _MEM_CACHE.items() if exp < now]:
                _MEM_CACHE.pop(k, None)
        _MEM_CACHE[key] = (time.monotonic() + ttl, value)


def _unavailable(provider: str, mode: str, message: str) -> RouteEstimate:
    return RouteEstimate(
        available=False,
        provider=provider,
        mode=mode,
        status="unavailable",
        distance_km=None,
        duration_min=None,
        message=message,
        calculated_at=_now(),
    )


def _mock_estimate(mode: str, straight_km: float) -> RouteEstimate:
    distance = straight_km * _MOCK_ROAD_DETOUR_FACTOR
    speed = _MOCK_SPEED_KMH.get(mode, _MOCK_SPEED_KMH["driving"])
    duration = (distance / speed) * 60.0 if speed else 0.0
    return RouteEstimate(
        available=True,
        provider="mock",
        mode=mode,
        status="mock",
        distance_km=round(distance, 2),
        duration_min=round(max(1.0, duration), 1),
        message="Estimated travel time (offline estimator, not a live route).",
        calculated_at=_now(),
    )


def _osrm_estimate(base_url: str, mode: str, o: tuple[float, float], d: tuple[float, float]) -> RouteEstimate:
    import httpx

    timeout = get_settings().routing_timeout_sec
    # OSRM expects lon,lat order and is served under /route/v1/<profile>/.
    url = f"{base_url.rstrip('/')}/route/v1/{mode}/{o[1]},{o[0]};{d[1]},{d[0]}"
    try:
        response = httpx.get(
            url,
            params={"overview": "false", "alternatives": "false"},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # network error / timeout / bad status
        logger.info("OSRM route request failed: %s", exc)
        return _unavailable("osrm", mode, "Live travel estimate is temporarily unavailable.")

    routes = payload.get("routes") if isinstance(payload, dict) else None
    if not routes:
        return _unavailable("osrm", mode, "No route found for these locations.")
    first = routes[0]
    try:
        distance_km = float(first["distance"]) / 1000.0
        duration_min = float(first["duration"]) / 60.0
    except (KeyError, TypeError, ValueError):
        return _unavailable("osrm", mode, "Travel provider returned an unexpected response.")
    return RouteEstimate(
        available=True,
        provider="osrm",
        mode=mode,
        status="ok",
        distance_km=round(distance_km, 2),
        duration_min=round(max(1.0, duration_min), 1),
        message="Live travel estimate.",
        calculated_at=_now(),
    )


def estimate_route(
    origin: tuple[float, float],
    destination: tuple[float, float],
    *,
    mode: str | None = None,
    force_provider: str | None = None,
) -> RouteEstimate:
    """Return a travel estimate between two points, degrading safely.

    ``force_provider`` lets tests pin a provider (e.g. ``mock``) deterministically.
    """
    settings = get_settings()
    provider = (force_provider or settings.routing_provider or "mock").lower()
    resolved_mode = normalise_mode(mode)
    if not valid_coords(origin[0], origin[1]) or not valid_coords(destination[0], destination[1]):
        return _unavailable(provider, resolved_mode, "Valid coordinates are required for a travel estimate.")

    key = _cache_key(provider, resolved_mode, origin, destination)
    cached = cache_get(key)
    if cached:
        try:
            import json

            data = json.loads(cached)
            data["calculated_at"] = datetime.fromisoformat(data["calculated_at"])
            return RouteEstimate(**data)
        except Exception:
            pass
    mem = _mem_get(key)
    if mem is not None:
        return mem

    if provider == "none":
        estimate = _unavailable("none", resolved_mode, "Travel estimates are disabled.")
    elif provider == "osrm":
        estimate = _osrm_estimate(settings.routing_base_url, resolved_mode, origin, destination)
    else:
        straight = haversine_km(origin[0], origin[1], destination[0], destination[1])
        estimate = _mock_estimate(resolved_mode, straight)

    if estimate.available:
        import json

        cache_set(key, json.dumps(estimate.as_dict()), ttl=settings.routing_cache_ttl_sec)
        _mem_set(key, estimate, _MEM_TTL)
    return estimate


def provider_info() -> dict:
    settings = get_settings()
    provider = (settings.routing_provider or "mock").lower()
    return {
        "provider": provider,
        "mode": normalise_mode(None),
        "configured": provider in {"mock", "osrm", "none"},
        "live": provider == "osrm",
        "departure_buffer_min": settings.departure_buffer_min,
    }
