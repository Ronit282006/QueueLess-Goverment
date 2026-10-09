"""Test bootstrap: force a isolated database/redis config before importing the app."""
from __future__ import annotations

import os
import pathlib

# Unit/integration tests default to a throwaway SQLite file so they never touch
# the development database. Set TEST_DATABASE_URL to run against PostgreSQL.
TEST_DB_PATH = pathlib.Path(__file__).parent / f"_test_queueless_{os.getpid()}.db"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{TEST_DB_PATH}")
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:6399/0")
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["EMAIL_MODE"] = "log"
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ["BACKGROUND_WORKERS_ENABLED"] = "false"

# The developer's .env may already have been loaded by a plugin or an earlier
# import in the same test process. Clear cached settings after forcing test
# values so workers cannot inherit live SMTP configuration.
from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _clean_test_db():
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    yield
    from sqlalchemy.orm import close_all_sessions

    from app.db import engine

    close_all_sessions()
    engine.dispose()
    # Keep the file after failures for debugging; remove on clean runs.
    if TEST_DB_PATH.exists() and not os.environ.get("KEEP_TEST_DB"):
        TEST_DB_PATH.unlink()


@pytest.fixture(scope="session")
def app():
    from app.main import app as fastapi_app

    from app.db import Base, engine

    Base.metadata.create_all(engine)
    return fastapi_app


@pytest.fixture(scope="session", autouse=True)
def _seed_minimal_catalog(app):
    """Insert just enough catalog rows for API tests (no historical demo data)."""
    from app.db import SessionLocal
    from app.models import Counter, CounterService, Department, Office, Service

    db = SessionLocal()
    try:
        if db.query(Office).count():
            yield
            return
        office = Office(code="test-office", name="Test Government Office", address="Test City")
        db.add(office)
        db.flush()
        department = Department(office_id=office.id, name="Revenue Department")
        db.add(department)
        db.flush()
        service = Service(
            department_id=department.id,
            code="test-income",
            name="Income Certificate",
            description="Test service",
            average_service_min=6.0,
        )
        service.documents = ["Aadhaar", "Address proof", "Income proof"]
        db.add(service)
        db.flush()
        for number in (1, 2, 3, 4, 5):
            counter = Counter(office_id=office.id, number=number, name=f"Counter {number}")
            db.add(counter)
            db.flush()
            if number <= 4:
                db.add(CounterService(counter_id=counter.id, service_id=service.id))
        db.commit()
        yield
    finally:
        db.close()


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
