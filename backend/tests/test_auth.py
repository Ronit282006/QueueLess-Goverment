"""Authentication and RBAC tests (Phase 2)."""
from __future__ import annotations

import uuid
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select


def _email() -> str:
    return f"test-{uuid.uuid4().hex[:8]}@example.com"


def test_register_login_and_profile(client):
    email = _email()
    registered = client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "Asha Patel", "password": "Sup3r-secret", "tags": ["Senior Citizen"]},
    )
    assert registered.status_code == 202, registered.text
    assert client.post("/api/auth/login", json={"email": email, "password": "Sup3r-secret"}).status_code == 401
    from app.db import SessionLocal
    from app.models import Notification

    db = SessionLocal()
    try:
        email_row = db.scalar(select(Notification).where(Notification.recipient == email).order_by(Notification.id.desc()))
        otp = re.search(r"\b\d{6}\b", email_row.body).group(0)
    finally:
        db.close()
    verified = client.post("/api/auth/register/verify", json={"email": email, "otp": otp})
    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert body["message"] == "Welcome to QueueLess, Asha Patel! Your account has been created successfully."
    assert body["user"]["role"] == "CITIZEN"
    assert body["user"]["tags"] == ["senior citizen"]
    token = body["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    logged_in = client.post("/api/auth/login", json={"email": email, "password": "Sup3r-secret"})
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["full_name"] == "Asha Patel"


def test_duplicate_email_and_bad_password(client):
    email = _email()
    payload = {"email": email, "full_name": "Ravi Shah", "password": "Sup3r-secret"}
    assert client.post("/api/auth/register", json=payload).status_code == 202
    pending = client.post("/api/auth/register", json=payload)
    assert pending.status_code == 409
    assert pending.json()["error"]["code"] == "registration_pending"
    from app.db import SessionLocal
    from app.models import Notification

    db = SessionLocal()
    try:
        row = db.scalar(select(Notification).where(Notification.recipient == email).order_by(Notification.id.desc()))
        otp = re.search(r"\b\d{6}\b", row.body).group(0)
    finally:
        db.close()
    assert client.post("/api/auth/register/verify", json={"email": email, "otp": otp}).status_code == 200
    duplicate = client.post("/api/auth/register", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "email_taken"

    bad = client.post("/api/auth/login", json={"email": email, "password": "wrong-password"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_credentials"


def test_protected_endpoint_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    bogus = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert bogus.status_code == 401


def test_short_password_rejected(client):
    response = client.post(
        "/api/auth/register",
        json={"email": _email(), "full_name": "Too Short", "password": "short"},
    )
    assert response.status_code == 422


def test_otp_expiry_and_attempt_limit(client):
    from app.db import SessionLocal
    from app.models import EmailOTPChallenge, Notification, User

    expired_email = _email()
    client.post("/api/auth/register", json={"email": expired_email, "full_name": "Expired User", "password": "Sup3r-secret"})
    db = SessionLocal()
    try:
        challenge = db.scalar(select(EmailOTPChallenge).where(EmailOTPChallenge.email == expired_email))
        challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()
    assert client.post("/api/auth/register/verify", json={"email": expired_email, "otp": "123456"}).status_code == 400

    locked_email = _email()
    client.post("/api/auth/register", json={"email": locked_email, "full_name": "Locked User", "password": "Sup3r-secret"})
    for _ in range(5):
        assert client.post("/api/auth/register/verify", json={"email": locked_email, "otp": "000000"}).status_code == 400
    db = SessionLocal()
    try:
        assert db.scalar(select(EmailOTPChallenge).where(EmailOTPChallenge.email == locked_email)) is None
        assert db.scalar(select(User.id).where(User.email == locked_email)) is None
        otp_rows = db.scalars(select(Notification).where(Notification.recipient.in_([expired_email, locked_email]))).all()
        assert otp_rows and all(row.sensitive for row in otp_rows)
    finally:
        db.close()
