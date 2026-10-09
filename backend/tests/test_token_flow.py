"""Token lifecycle and queue integration tests (Phase 1/4)."""
from __future__ import annotations

import re
import uuid


def _service_id(client) -> int:
    offices = client.get("/api/offices").json()
    return offices[0]["departments"][0]["services"][0]["id"]


def test_take_token_and_read_queue(client):
    service_id = _service_id(client)
    response = client.post("/api/tokens", json={"service_id": service_id, "documents_confirmed": []})
    assert response.status_code == 201, response.text
    token = response.json()
    assert token["status"] == "WAITING"
    assert token["label"].startswith("Q-")
    assert token["qr_data_url"].startswith("data:image/png;base64,")

    queue = client.get(f"/api/queue?service_id={service_id}").json()
    assert any(row["reference"] == token["reference"] for row in queue["tokens"])

    fetched = client.get(f"/api/tokens/{token['reference']}").json()
    assert fetched["label"] == token["label"]


def test_authenticated_citizen_can_create_token_and_get_email_queued(client):
    email = f"token-{uuid.uuid4().hex[:10]}@example.com"
    password = "Sup3r-secret"
    started = client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "Token Citizen", "password": password},
    )
    assert started.status_code == 202, started.text

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Notification

    db = SessionLocal()
    try:
        otp_email = db.scalar(
            select(Notification)
            .where(Notification.recipient == email, Notification.kind == "ACCOUNT_OTP")
            .order_by(Notification.id.desc())
        )
        otp = re.search(r"\b\d{6}\b", otp_email.body).group(0)
    finally:
        db.close()

    verified = client.post("/api/auth/register/verify", json={"email": email, "otp": otp})
    assert verified.status_code == 200, verified.text
    headers = {"Authorization": f"Bearer {verified.json()['access_token']}"}
    created = client.post("/api/tokens", json={"service_id": _service_id(client)}, headers=headers)
    assert created.status_code == 201, created.text

    db = SessionLocal()
    try:
        confirmation = db.scalar(
            select(Notification).where(
                Notification.recipient == email,
                Notification.kind == "TOKEN_CREATED",
                Notification.token_id == created.json()["id"],
            )
        )
        assert confirmation is not None
        assert confirmation.status == "QUEUED"
    finally:
        db.close()


def test_transitions_follow_state_machine(client):
    service_id = _service_id(client)
    token = client.post("/api/tokens", json={"service_id": service_id}).json()
    ref = token["reference"]

    assert client.post("/api/tokens/check-in", json={"reference": ref}).json()["status"] == "ARRIVED"
    # Possessing a token reference must not grant staff state transitions.
    denied = client.post(f"/api/tokens/{ref}/transition", json={"status": "COMPLETED"})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"

    cancelled = client.post(f"/api/tokens/{ref}/transition", json={"status": "CANCELLED"})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    events = client.get(f"/api/tokens/{ref}/events").json()
    assert [e["to_status"] for e in events] == [
        "CREATED",
        "WAITING",
        "ARRIVED",
        "CANCELLED",
    ]


def test_service_detail_exposes_documents_and_prediction(client):
    service_id = _service_id(client)
    detail = client.get(f"/api/services/{service_id}").json()
    assert detail["required_documents"]
    assert detail["prediction"]["method"]
    assert 0 <= detail["confidence"] <= 1


def test_feedback_and_priority_validation(client):
    service_id = _service_id(client)
    token = client.post("/api/tokens", json={"service_id": service_id}).json()
    ref = token["reference"]
    # Feedback before completion is rejected.
    early = client.post(f"/api/tokens/{ref}/feedback", json={"rating": 5})
    assert early.status_code == 409
    from test_staff import _staff_headers

    headers = _staff_headers(client)
    for status in ("ARRIVED", "CALLED", "SERVING", "COMPLETED"):
        client.post(f"/api/tokens/{ref}/transition", json={"status": status}, headers=headers)
    ok = client.post(f"/api/tokens/{ref}/feedback", json={"rating": 4, "eta_accurate": True})
    assert ok.status_code == 201
    duplicate = client.post(f"/api/tokens/{ref}/feedback", json={"rating": 1})
    assert duplicate.status_code == 409
