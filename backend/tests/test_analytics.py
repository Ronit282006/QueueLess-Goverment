"""Analytics tests (Phase 11): peak hours, demand, efficiency, SLA, feedback, accuracy."""
from __future__ import annotations

import uuid


def _staff_headers(client, office_id: int) -> dict:
    from app.db import SessionLocal
    from app.models import Counter, User
    from app.security import create_access_token, hash_password

    db = SessionLocal()
    try:
        user = User(
            email=f"analyst-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Analyst",
            password_hash=hash_password("Sup3r-secret"),
            role="STAFF",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return {"Authorization": f"Bearer {create_access_token(subject=user.id, role=user.role)}"}
    finally:
        db.close()


def _complete_one(client) -> tuple[str, int, int]:
    offices = client.get("/api/offices").json()
    office_id = offices[0]["id"]
    service_id = offices[0]["departments"][0]["services"][0]["id"]
    headers = _staff_headers(client, office_id)

    from app.db import SessionLocal
    from app.models import Token
    from app.services.token_service import ACTIVE_STATUSES

    db = SessionLocal()
    try:
        for token in db.query(Token).filter(Token.service_id == service_id).all():
            if token.status in ACTIVE_STATUSES:
                token.status = "CANCELLED"
        db.commit()
    finally:
        db.close()

    counters = client.get(f"/api/staff/counters?office_id={office_id}", headers=headers).json()
    counter_id = counters[0]["id"]
    created = client.post("/api/tokens", json={"service_id": service_id}).json()
    client.post(f"/api/staff/counters/{counter_id}/call-next", json={"service_id": service_id}, headers=headers)
    client.post(f"/api/staff/counters/{counter_id}/start", headers=headers)
    client.post(f"/api/staff/counters/{counter_id}/complete", headers=headers)
    return created["reference"], office_id, service_id


def test_analytics_requires_staff(client):
    assert client.get("/api/analytics/overview").status_code == 401


def test_analytics_reports_real_activity(client):
    reference, office_id, service_id = _complete_one(client)
    headers = _staff_headers(client, office_id)

    client.post(f"/api/tokens/{reference}/feedback", json={"rating": 5, "eta_accurate": True})

    overview = client.get(f"/api/analytics/overview?office_id={office_id}", headers=headers).json()
    assert overview["office_id"] == office_id
    assert overview["tokens_today"] >= 1
    assert overview["completed_today"] >= 1
    assert overview["satisfaction_avg"] == 5.0

    peak = client.get(f"/api/analytics/peak-hours?office_id={office_id}", headers=headers).json()
    assert isinstance(peak["hours"], list) and "busiest_hour" in peak

    demand = client.get(f"/api/analytics/demand?office_id={office_id}", headers=headers).json()
    assert demand["total"] >= 1 and demand["series"]

    efficiency = client.get(f"/api/analytics/efficiency?office_id={office_id}", headers=headers).json()
    assert any(s["service_id"] == service_id for s in efficiency["services"])

    sla = client.get(f"/api/analytics/sla?office_id={office_id}", headers=headers).json()
    assert sla["served"] >= 1

    feedback = client.get(f"/api/analytics/feedback?office_id={office_id}", headers=headers).json()
    assert feedback["distribution"]["5"] >= 1

    accuracy = client.get(f"/api/analytics/prediction-accuracy?office_id={office_id}", headers=headers).json()
    assert accuracy["scored_predictions"] >= 1