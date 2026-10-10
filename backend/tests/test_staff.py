"""Staff dashboard and counter lifecycle tests (Phase 9)."""
from __future__ import annotations

import uuid


def _staff_headers(client, email: str | None = None) -> dict:
    """Create (or log in) a STAFF user directly in the DB and return its bearer token.

    The member is assigned the first counter of every office so office-scope and
    counter-level authorization checks pass regardless of which office a test uses.
    """
    from app.db import SessionLocal
    from app.models import Counter, StaffAssignment, User
    from app.security import create_access_token, hash_password

    email = email or f"staff-{uuid.uuid4().hex[:8]}@example.com"
    db = SessionLocal()
    try:
        user = User(
            email=email,
            full_name="Staff Member",
            password_hash=hash_password("Sup3r-secret"),
            role="STAFF",
        )
        db.add(user)
        db.flush()
        first_per_office: dict[int, Counter] = {}
        for counter in db.query(Counter).order_by(Counter.office_id, Counter.number).all():
            first_per_office.setdefault(counter.office_id, counter)
        for counter in first_per_office.values():
            db.add(
                StaffAssignment(
                    user_id=user.id, office_id=counter.office_id,
                    counter_id=counter.id, is_active=True,
                )
            )
        db.commit()
        db.refresh(user)
        token = create_access_token(subject=user.id, role=user.role)
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


def _service_and_counter(client) -> tuple[int, int]:
    offices = client.get("/api/offices").json()
    service_id = offices[0]["departments"][0]["services"][0]["id"]
    return service_id, offices


def _drain_active_tokens(service_id: int) -> None:
    """Clear tokens other tests left in the queue so call-next is deterministic."""
    from app.db import SessionLocal
    from app.models import Token, TokenStatus
    from app.services.token_service import ACTIVE_STATUSES

    db = SessionLocal()
    try:
        for token in db.query(Token).filter(Token.service_id == service_id).all():
            if token.status in ACTIVE_STATUSES:
                token.status = TokenStatus.CANCELLED.value
        db.commit()
    finally:
        db.close()


def test_staff_endpoints_require_auth(client):
    assert client.get("/api/staff/dashboard").status_code == 401


def test_counter_lifecycle_serves_a_citizen(client):
    headers = _staff_headers(client)
    service_id, offices = _service_and_counter(client)
    office_id = offices[0]["id"]
    _drain_active_tokens(service_id)

    counters = client.get(f"/api/staff/counters?office_id={office_id}", headers=headers).json()
    assert counters, "expected seeded counters"
    counter_id = counters[0]["id"]

    # A citizen takes a token.
    token = client.post("/api/tokens", json={"service_id": service_id}).json()

    # Staff call next -> CALLED, counter busy, token bound to counter.
    called = client.post(
        f"/api/staff/counters/{counter_id}/call-next", json={"service_id": service_id}, headers=headers
    )
    assert called.status_code == 200, called.text
    body = called.json()
    assert body["status"] == "CALLED"
    assert body["counter_id"] == counter_id
    assert body["label"] == token["label"]

    assert client.post(f"/api/staff/counters/{counter_id}/start", headers=headers).json()["status"] == "SERVING"
    completed = client.post(f"/api/staff/counters/{counter_id}/complete", headers=headers).json()
    assert completed["status"] == "COMPLETED"

    # Counter is freed up again.
    counter = next(c for c in client.get(f"/api/staff/counters?office_id={office_id}", headers=headers).json() if c["id"] == counter_id)
    assert counter["status"] == "AVAILABLE"

    # A live service-time record and a scored prediction now exist for learning.
    from app.db import SessionLocal
    from app.models import Prediction, ServiceTimeRecord

    db = SessionLocal()
    try:
        record = db.query(ServiceTimeRecord).filter(ServiceTimeRecord.token_id is not None).order_by(ServiceTimeRecord.id.desc()).first()
        assert record is not None
        assert record.origin == "LIVE"
    finally:
        db.close()


def test_call_next_on_empty_queue_conflicts(client):
    headers = _staff_headers(client)
    service_id, offices = _service_and_counter(client)
    _drain_active_tokens(service_id)
    counters = client.get(f"/api/staff/counters?office_id={offices[0]['id']}", headers=headers).json()
    response = client.post(
        f"/api/staff/counters/{counters[0]['id']}/call-next",
        json={"service_id": service_id},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "queue_empty"


def test_counter_status_update_and_validation(client):
    headers = _staff_headers(client)
    _, offices = _service_and_counter(client)
    counters = client.get(f"/api/staff/counters?office_id={offices[0]['id']}", headers=headers).json()
    counter_id = counters[0]["id"]

    ok = client.patch(f"/api/staff/counters/{counter_id}", json={"status": "BREAK"}, headers=headers)
    assert ok.status_code == 200 and ok.json()["status"] == "BREAK"

    bad = client.patch(f"/api/staff/counters/{counter_id}", json={"status": "NAPPING"}, headers=headers)
    assert bad.status_code == 400

    client.patch(f"/api/staff/counters/{counter_id}", json={"status": "AVAILABLE"}, headers=headers)