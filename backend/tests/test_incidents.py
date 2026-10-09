"""Incident approvals, transparent rebooking and deadline handling."""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def _staff_headers(db):
    from app.models import User
    from app.security import create_access_token, hash_password

    staff = User(
        email=f"incident-staff-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Incident Staff", password_hash=hash_password("Sup3r-secret"), role="STAFF",
    )
    db.add(staff)
    db.flush()
    return {"Authorization": f"Bearer {create_access_token(subject=staff.id, role=staff.role)}"}


def _citizen_and_token(db):
    from app.models import Service, User
    from app.security import hash_password
    from app.services import token_service

    user = User(
        email=f"incident-citizen-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Incident Citizen", password_hash=hash_password("Sup3r-secret"), role="CITIZEN",
    )
    db.add(user)
    db.flush()
    service = db.scalar(select(Service).limit(1))
    token = token_service.create_token(db, office_id=service.department.office_id, service_id=service.id, user_id=user.id)
    db.commit()
    return user, service, token


def _create_incident(client, headers, office_id, service_id):
    now = datetime.now(timezone.utc)
    return client.post("/api/staff/incidents", headers=headers, json={
        "office_id": office_id,
        "service_id": service_id,
        "incident_type": "CLOSURE",
        "description": "Unexpected service closure",
        "location_instructions": "Use the side entrance",
        "starts_at": now.isoformat(),
        "ends_at": (now + timedelta(hours=2)).isoformat(),
    })


def _incident_action_token(db, reference):
    from app.models import Notification, Token

    token = db.scalar(select(Token).where(Token.reference == reference))
    email = db.scalar(select(Notification).where(Notification.dedupe_key == f"incident-action:{token.incident_id}:{token.id}"))
    return re.search(r"incident_action=([A-Za-z0-9_-]+)", email.body).group(1)


def test_incident_requires_explicit_transfer_and_preserves_history(client):
    from app.db import SessionLocal
    from app.models import Token, TokenStatus

    db = SessionLocal()
    try:
        user, service, token = _citizen_and_token(db)
        headers = _staff_headers(db)
        db.commit()
        incident_response = _create_incident(client, headers, service.department.office_id, service.id)
        assert incident_response.status_code == 201, incident_response.text
        db.refresh(token)
        assert token.status == TokenStatus.WAITING.value
        assert token.incident_response_status == "PENDING"
        action_token = _incident_action_token(db, token.reference)

        response = client.post(f"/api/tokens/{token.reference}/incident-response", json={
            "action": "TRANSFER", "action_token": action_token,
        }, headers={"Authorization": f"Bearer {__import__('app.security', fromlist=['create_access_token']).create_access_token(subject=user.id, role=user.role)}"})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["action"] == "TRANSFERRED"
        assert result["scheduled_for"] > datetime.now(timezone.utc).date().isoformat()
        db.refresh(token)
        assert token.status == TokenStatus.RESCHEDULED.value
        replacement = db.scalar(select(Token).where(Token.rescheduled_from_id == token.id))
        assert replacement is not None
        assert replacement.scheduled_for.isoformat() == result["scheduled_for"]
        assert replacement.status == TokenStatus.WAITING.value
        assert db.scalar(select(Token.id).where(Token.rescheduled_from_id == token.id)) == replacement.id
    finally:
        db.close()


def test_holiday_skips_to_next_working_day(client):
    from app.db import SessionLocal
    from app.models import Office, OfficeHoliday
    from app.security import create_access_token

    db = SessionLocal()
    try:
        user, service, token = _citizen_and_token(db)
        office = db.get(Office, service.department.office_id)
        office.working_days = "mon,tue,wed,thu,fri,sat,sun"
        holiday = date.today() + timedelta(days=1)
        db.add(OfficeHoliday(office_id=office.id, holiday_date=holiday, name="Observed holiday"))
        headers = _staff_headers(db)
        db.commit()
        response = _create_incident(client, headers, office.id, service.id)
        assert response.status_code == 201, response.text
        action_token = _incident_action_token(db, token.reference)
        auth = {"Authorization": f"Bearer {create_access_token(subject=user.id, role=user.role)}"}
        moved = client.post(f"/api/tokens/{token.reference}/incident-response", json={"action": "TRANSFER", "action_token": action_token}, headers=auth)
        assert moved.status_code == 200, moved.text
        assert moved.json()["scheduled_for"] == (holiday + timedelta(days=1)).isoformat()
    finally:
        db.close()


def test_incident_cancel_and_deadline_cancel(client):
    from app.db import SessionLocal
    from app.models import Notification, Token, TokenStatus
    from app.security import create_access_token
    from app.worker import sweep_incident_deadlines

    db = SessionLocal()
    try:
        user, service, cancelled = _citizen_and_token(db)
        headers = _staff_headers(db)
        db.commit()
        assert _create_incident(client, headers, service.department.office_id, service.id).status_code == 201
        action_token = _incident_action_token(db, cancelled.reference)
        auth = {"Authorization": f"Bearer {create_access_token(subject=user.id, role=user.role)}"}
        result = client.post(f"/api/tokens/{cancelled.reference}/incident-response", json={"action": "CANCEL", "action_token": action_token}, headers=auth)
        assert result.status_code == 200
        db.refresh(cancelled)
        assert cancelled.status == TokenStatus.CANCELLED.value

        timeout_user, timeout_service, pending = _citizen_and_token(db)
        headers = _staff_headers(db)
        db.commit()
        assert _create_incident(client, headers, timeout_service.department.office_id, timeout_service.id).status_code == 201
        pending.incident_response_due = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        outcome = sweep_incident_deadlines(db)
        db.commit()
        db.refresh(pending)
        assert outcome["cancelled"] >= 1
        assert pending.status == TokenStatus.CANCELLED.value
        assert db.scalar(select(Notification.id).where(Notification.dedupe_key == f"incident-timeout-cancel:{pending.incident_id}:{pending.id}"))
    finally:
        db.close()


def test_arrived_citizen_is_held_for_staff_instead_of_silently_cancelled(client):
    from app.db import SessionLocal
    from app.models import TokenStatus
    from app.services import token_service
    from app.worker import sweep_incident_deadlines

    db = SessionLocal()
    try:
        _, service, token = _citizen_and_token(db)
        headers = _staff_headers(db)
        token_service.apply_transition(db, token, TokenStatus.ARRIVED.value)
        db.commit()
        _create_incident(client, headers, service.department.office_id, service.id)
        db.refresh(token)
        token.incident_response_due = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        sweep_incident_deadlines(db)
        db.commit()
        db.refresh(token)
        assert token.status == TokenStatus.ARRIVED.value
        assert token.incident_response_status == "STAFF_REVIEW"
    finally:
        db.close()


def test_rescheduled_parent_unique_constraint_prevents_duplicate_active_transfers(app):
    from app.db import SessionLocal
    from app.models import Service, Token
    from app.services import token_service

    db = SessionLocal()
    try:
        service = db.scalar(select(Service).limit(1))
        parent = token_service.create_token(db, office_id=service.department.office_id, service_id=service.id, user_id=None)
        db.commit()
        first = token_service.create_token(db, office_id=service.department.office_id, service_id=service.id, user_id=None)
        first.rescheduled_from_id = parent.id
        db.commit()
        second = token_service.create_token(db, office_id=service.department.office_id, service_id=service.id, user_id=None)
        second.rescheduled_from_id = parent.id
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(select(Token.id).where(Token.rescheduled_from_id == parent.id)) == first.id
    finally:
        db.close()
