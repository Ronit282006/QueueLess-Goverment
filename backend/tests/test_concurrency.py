"""Concurrency and fairness tests for the token engine (Phase 4).

Run against PostgreSQL for the real row-locking guarantee:

    $env:TEST_DATABASE_URL="postgresql+psycopg://queueless:queueless_local@127.0.0.1:5432/queueless_test"
    python -m pytest tests/test_concurrency.py -v

On SQLite the test is skipped because SELECT ... FOR UPDATE is a no-op there.
"""
from __future__ import annotations

import threading

import pytest
from sqlalchemy import select

from app.config import get_settings


def _service_and_office(app):
    from app.db import SessionLocal
    from app.models import Service

    db = SessionLocal()
    try:
        service = db.scalar(select(Service).limit(1))
        return service.id, service.department.office_id
    finally:
        db.close()


@pytest.mark.skipif(get_settings().is_sqlite, reason="Row-level locking requires PostgreSQL")
def test_parallel_token_allocation_is_unique(app):
    from concurrent.futures import ThreadPoolExecutor

    from app.db import SessionLocal
    from app.services import token_service

    service_id, office_id = _service_and_office(app)
    workers = 24
    barrier = threading.Barrier(workers)

    def take(_: int) -> int:
        db = SessionLocal()
        try:
            barrier.wait(timeout=30)
            token = token_service.create_token(
                db, office_id=office_id, service_id=service_id, user_id=None
            )
            db.commit()
            return token.number
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        numbers = list(pool.map(take, range(workers)))

    assert len(numbers) == workers
    assert len(set(numbers)) == workers, f"duplicate token numbers: {sorted(numbers)}"
    assert max(numbers) - min(numbers) == workers - 1  # gap-free sequence


def test_priority_ordering_is_fair(app):
    from app.db import SessionLocal
    from app.services import queue_service, token_service

    service_id, office_id = _service_and_office(app)
    db = SessionLocal()
    try:
        normal = token_service.create_token(db, office_id=office_id, service_id=service_id, user_id=None, priority_rank=0)
        priority = token_service.create_token(db, office_id=office_id, service_id=service_id, user_id=None, priority_rank=2)
        db.commit()

        ordered = queue_service.queue_for_service(db, office_id, service_id)
        ranks = [t.priority_rank for t in ordered]
        assert ranks == sorted(ranks, reverse=True)
        assert priority.id in [t.id for t in ordered]
        assert normal.id in [t.id for t in ordered]
    finally:
        db.close()