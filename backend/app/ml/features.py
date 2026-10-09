"""Feature engineering for the prediction model (Phase 5).

Each completed service duration is paired with the queue conditions observed
just before it started, so the model learns how load and time-of-day change
service time — not merely a global average.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import QueueSnapshot, ServiceTimeRecord

FEATURE_NAMES = ["hour", "day_of_week", "queue_length", "active_counters", "is_peak"]
_PEAK_HOURS = set(range(10, 13)) | set(range(16, 19))  # 10-12 and 16-18


def _is_peak(hour: int) -> float:
    return 1.0 if hour in _PEAK_HOURS else 0.0


def _aware(value: datetime) -> datetime:
    from datetime import timezone

    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def build_training_frame(db: Session, service_id: int | None = None) -> tuple[np.ndarray, np.ndarray] | None:
    record_stmt = select(ServiceTimeRecord).order_by(ServiceTimeRecord.completed_at)
    snapshot_stmt = select(QueueSnapshot).order_by(QueueSnapshot.captured_at)
    if service_id is not None:
        record_stmt = record_stmt.where(ServiceTimeRecord.service_id == service_id)
        snapshot_stmt = snapshot_stmt.where(QueueSnapshot.service_id == service_id)
    records = list(db.scalars(record_stmt))
    if len(records) < 40:
        return None
    snapshots = list(db.scalars(snapshot_stmt))

    # Group snapshots per service for an as-of join (last observation before completion).
    grouped: dict[int, list[QueueSnapshot]] = {}
    for snap in snapshots:
        grouped.setdefault(snap.service_id, []).append(snap)
    times: dict[int, list[float]] = {
        sid: [_aware(s.captured_at).timestamp() for s in rows] for sid, rows in grouped.items()
    }

    rows: list[list[float]] = []
    targets: list[float] = []
    fallback = _service_fallback(db, service_id, records)
    for record in records:
        completed = _aware(record.completed_at)
        queue_length, counters = _conditions(grouped.get(record.service_id, []), times.get(record.service_id, []), completed)
        if counters == 0:
            counters = fallback.get(record.service_id, 3)
        rows.append(
            [
                float(completed.hour),
                float(completed.weekday()),
                float(queue_length),
                float(counters),
                _is_peak(completed.hour),
            ]
        )
        targets.append(float(record.duration_min))

    return np.asarray(rows, dtype=float), np.asarray(targets, dtype=float)


def _conditions(snaps: list[QueueSnapshot], ts: list[float], when: datetime) -> tuple[int, int]:
    if not snaps:
        return 0, 0
    idx = bisect_right(ts, when.timestamp()) - 1
    if idx < 0:
        idx = 0
    snap = snaps[idx]
    return int(snap.queue_length), int(snap.active_counters)


def _service_fallback(db: Session, service_id: int | None, records: list[ServiceTimeRecord]) -> dict[int, int]:
    if service_id is None:
        return {}
    from sqlalchemy import func

    from ..models import CounterService

    n = db.scalar(
        select(func.count()).select_from(CounterService).where(CounterService.service_id == service_id)
    )
    return {service_id: max(1, min(int(n or 3), 8))}


def inference_features(
    *, hour: int, day_of_week: int, queue_length: int, active_counters: int
) -> np.ndarray:
    return np.asarray(
        [[float(hour), float(day_of_week), float(queue_length), float(active_counters), _is_peak(hour)]],
        dtype=float,
    )