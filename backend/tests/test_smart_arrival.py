"""Smart arrival (routing/recommendations/reminders) and no-show grace tests.

All time-dependent behaviour is driven by an explicit ``now`` value so tests
never sleep for real minutes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.errors import ApiException


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _user(db, tag: str = "arrival") -> object:
    from app.models import User
    from app.security import hash_password

    user = User(
        email=f"{tag}-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Arrival Test",
        password_hash=hash_password("Sup3r-secret"),
        role="CITIZEN",
    )
    db.add(user)
    db.flush()
    return user


def _service(db):
    from app.models import Service

    return db.scalar(select(Service).limit(1))


def _fresh_service(db):
    """A brand-new office+service so its queue is fully isolated.

    The new office is appended after the seeded one, so catalog tests that read
    the *first* office keep seeing the original fixture data.
    """
    from app.models import Counter, Department, Office, Service

    suffix = uuid.uuid4().hex[:8]
    office = Office(code=f"arr-office-{suffix}", name=f"Arrival Office {suffix}", address="Arrival Test")
    db.add(office)
    db.flush()
    department = Department(office_id=office.id, name="Arrival Department")
    db.add(department)
    db.flush()
    service = Service(
        department_id=department.id,
        code=f"arr-{suffix}",
        name=f"Arrival Service {suffix}",
        average_service_min=6.0,
    )
    db.add(service)
    db.flush()
    db.add(Counter(office_id=office.id, number=1, name="Counter 1"))
    db.flush()
    return service


def _advance_to_serving(db, token):
    from app.models.enums import TokenStatus
    from app.services import token_service

    token_service.apply_transition(db, token, TokenStatus.ARRIVED.value)
    token_service.apply_transition(db, token, TokenStatus.CALLED.value)
    token_service.apply_transition(db, token, TokenStatus.SERVING.value)


def test_grace_cancels_unchecked_in_next_token(app):
    from app.db import SessionLocal
    from app.models import Token, TokenStatus
    from app.models.enums import GraceState
    from app.services import grace_service, token_service

    db = SessionLocal()
    try:
        service = _fresh_service(db)
        office_id = service.department.office_id
        user = _user(db)
        first = token_service.create_token(db, office_id=office_id, service_id=service.id, user_id=user.id)
        _advance_to_serving(db, first)
        token_service.apply_transition(db, first, TokenStatus.COMPLETED.value)
        second = token_service.create_token(db, office_id=office_id, service_id=service.id, user_id=user.id)
        db.commit()

        t0 = utcnow()
        started = grace_service.start_grace_for_next(db, first, now=t0)
        assert started is not None and started.id == second.id
        assert second.grace_state == GraceState.ACTIVE.value
        assert second.grace_deadline is not None

        # Before the deadline: nothing happens.
        assert grace_service.expire_due_grace(db, now=t0 + timedelta(seconds=10)) == []

        # After the deadline: the token is auto-cancelled.
        cancelled = grace_service.expire_due_grace(db, now=t0 + timedelta(seconds=301))
        assert any(item["id"] == second.id for item in cancelled)

        db.refresh(second)
        assert second.status == TokenStatus.CANCELLED.value
        assert second.grace_state == GraceState.EXPIRED.value
        assert second.cancellation_reason == grace_service.CANCELLATION_REASON
        assert second.cancelled_at is not None
    finally:
        db.close()


def test_check_in_during_grace_stops_the_timer(app):
    from app.db import SessionLocal
    from app.models import TokenStatus
    from app.models.enums import GraceState
    from app.services import grace_service, token_service

    db = SessionLocal()
    try:
        service = _fresh_service(db)
        office_id = service.department.office_id
        user = _user(db, "grace-arrive")
        first = token_service.create_token(db, office_id=office_id, service_id=service.id, user_id=user.id)
        _advance_to_serving(db, first)
        token_service.apply_transition(db, first, TokenStatus.COMPLETED.value)
        second = token_service.create_token(db, office_id=office_id, service_id=service.id, user_id=user.id)
        db.commit()

        t0 = utcnow()
        grace_service.start_grace_for_next(db, first, now=t0)
        token_service.apply_transition(db, second, TokenStatus.ARRIVED.value)
        db.commit()
        assert second.grace_state == GraceState.ARRIVED.value

        assert grace_service.expire_due_grace(db, now=t0 + timedelta(seconds=999)) == []
        db.refresh(second)
        assert second.status == TokenStatus.ARRIVED.value
    finally:
        db.close()


def test_no_grace_when_next_token_already_arrived(app):
    from app.db import SessionLocal
    from app.models import TokenStatus
    from app.services import grace_service, token_service

    db = SessionLocal()
    try:
        service = _fresh_service(db)
        office_id = service.department.office_id
        user = _user(db, "grace-present")
        first = token_service.create_token(db, office_id=office_id, service_id=service.id, user_id=user.id)
        _advance_to_serving(db, first)
        token_service.apply_transition(db, first, TokenStatus.COMPLETED.value)
        second = token_service.create_token(db, office_id=office_id, service_id=service.id, user_id=user.id)
        token_service.apply_transition(db, second, TokenStatus.ARRIVED.value)
        db.commit()

        assert grace_service.start_grace_for_next(db, first, now=utcnow()) is None
    finally:
        db.close()


def test_no_show_sweeper_defers_tokens_in_active_grace(app):
    from app.db import SessionLocal
    from app.models import Token, TokenStatus
    from app.models.enums import GraceState
    from app.services import token_service
    from app.worker import sweep_no_shows

    db = SessionLocal()
    try:
        service = _fresh_service(db)
        office_id = service.department.office_id
        user = _user(db, "defer")
        token = token_service.create_token(db, office_id=office_id, service_id=service.id, user_id=user.id)
        token_service.apply_transition(db, token, TokenStatus.ARRIVED.value)
        token_service.apply_transition(db, token, TokenStatus.CALLED.value)
        token.called_at = utcnow() - timedelta(minutes=30)
        token.grace_state = GraceState.ACTIVE.value
        db.commit()

        sweep_no_shows(db)
        db.commit()
        db.refresh(token)
        # Owned by grace_service, so the legacy called-no-show sweep leaves it.
        assert token.status == TokenStatus.CALLED.value
    finally:
        db.close()


def test_routing_mock_estimates_and_validation(app):
    from app.services import routing_service

    estimate = routing_service.estimate_route((23.2231, 72.6500), (23.0366, 72.5616), force_provider="mock")
    assert estimate.available is True
    assert estimate.provider == "mock"
    assert estimate.status == "mock"
    assert estimate.duration_min and estimate.duration_min > 0
    assert estimate.distance_km and estimate.distance_km > 0

    try:
        routing_service.require_coords(0.0, 0.0)
        raise AssertionError("expected invalid coordinate rejection")
    except ApiException as exc:
        assert exc.status_code == 400


def test_recommend_offices_ranks_by_total_time(app):
    from app.db import SessionLocal
    from app.models import Counter, Department, Office, Service
    from app.services import arrival_service

    db = SessionLocal()
    try:
        reference = _service(db)
        base_office = db.get(Office, reference.department.office_id)
        base_office.latitude = 23.2231
        base_office.longitude = 72.6500

        far = Office(code=f"far-{uuid.uuid4().hex[:6]}", name="Far Office", address="Far")
        db.add(far)
        db.flush()
        far_dept = Department(office_id=far.id, name="Revenue Department")
        db.add(far_dept)
        db.flush()
        far_service = Service(
            department_id=far_dept.id,
            code=f"income-far-{uuid.uuid4().hex[:6]}",
            name=reference.name,
            average_service_min=6.0,
        )
        db.add(far_service)
        far.latitude = 28.6139  # Delhi — much farther
        far.longitude = 77.2090
        db.flush()
        db.add(Counter(office_id=far.id, number=1, name="Counter 1"))
        db.commit()

        result = arrival_service.recommend_offices(db, reference.id, (23.22, 72.65))
        offices = {row["office_id"]: row for row in result["offices"]}
        assert base_office.id in offices and far.id in offices
        assert offices[base_office.id]["total_min"] is not None
        assert offices[base_office.id]["total_min"] < offices[far.id]["total_min"]
        assert result["best_office_id"] == base_office.id
    finally:
        db.close()


def test_recommend_offices_assesses_a_chosen_office(app):
    from app.db import SessionLocal
    from app.models import Counter, Department, Office, Service
    from app.services import arrival_service

    db = SessionLocal()
    try:
        reference = _service(db)
        base_office = db.get(Office, reference.department.office_id)
        base_office.latitude = 23.2231
        base_office.longitude = 72.6500

        far = Office(code=f"far-{uuid.uuid4().hex[:6]}", name="Far Office", address="Far")
        db.add(far)
        db.flush()
        far_dept = Department(office_id=far.id, name="Revenue Department")
        db.add(far_dept)
        db.flush()
        far_service = Service(
            department_id=far_dept.id,
            code=f"income-far-{uuid.uuid4().hex[:6]}",
            name=reference.name,
            average_service_min=6.0,
        )
        db.add(far_service)
        far.latitude = 28.6139  # Delhi — much farther
        far.longitude = 77.2090
        db.flush()
        db.add(Counter(office_id=far.id, number=1, name="Counter 1"))
        db.commit()

        origin = (23.22, 72.65)

        # Choosing the nearest office is reported as the best choice.
        best = arrival_service.recommend_offices(
            db, reference.id, origin, selected_office_id=base_office.id
        )
        assert best["assessment"]["is_best"] is True
        assert best["assessment"]["offers_service"] is True
        assert best["selected"]["office_id"] == base_office.id

        # Choosing the far office is flagged as not best, with a positive penalty.
        picked_far = arrival_service.recommend_offices(
            db, reference.id, origin, selected_office_id=far.id
        )
        assert picked_far["assessment"]["is_best"] is False
        assert picked_far["assessment"]["extra_min"] and picked_far["assessment"]["extra_min"] > 0

        # Choosing an office that does not offer the service is explained plainly.
        unrelated = _fresh_service(db)
        db.commit()
        not_offered = arrival_service.recommend_offices(
            db, reference.id, origin, selected_office_id=unrelated.department.office_id
        )
        assert not_offered["assessment"]["offers_service"] is False
        assert not_offered["assessment"]["is_best"] is False
        assert not_offered["selected"] is None
    finally:
        db.close()


def test_departure_reminder_is_scheduled_and_sent(app):
    from app.db import SessionLocal
    from app.models import Notification, Office, ScheduledReminder
    from app.models.enums import NotificationKind, ReminderStatus
    from app.services import arrival_service, token_service

    db = SessionLocal()
    try:
        service = _fresh_service(db)
        office = db.get(Office, service.department.office_id)
        office.latitude = 23.2231
        office.longitude = 72.6500
        user = _user(db, "reminder")
        token = token_service.create_token(db, office_id=office.id, service_id=service.id, user_id=user.id)
        db.commit()

        t0 = utcnow()
        reminder = arrival_service.schedule_departure_reminder(db, token, (23.22, 72.65), now=t0)
        db.commit()
        assert reminder is not None
        assert reminder.status == ReminderStatus.PENDING.value

        sent = arrival_service.process_due_reminders(db, now=t0 + timedelta(hours=2))
        assert sent >= 1
        db.refresh(reminder)
        assert reminder.status == ReminderStatus.SENT.value

        notes = db.scalars(
            select(Notification).where(
                Notification.token_id == token.id,
                Notification.kind == NotificationKind.ARRIVAL_REMINDER.value,
            )
        ).all()
        assert notes
    finally:
        db.close()


def test_reminder_cancelled_when_citizen_checks_in(app):
    from app.db import SessionLocal
    from app.models import Office, ScheduledReminder
    from app.models.enums import ReminderStatus
    from app.models import TokenStatus
    from app.services import arrival_service, token_service

    db = SessionLocal()
    try:
        service = _fresh_service(db)
        office = db.get(Office, service.department.office_id)
        office.latitude = 23.2231
        office.longitude = 72.6500
        user = _user(db, "reminder-cancel")
        token = token_service.create_token(db, office_id=office.id, service_id=service.id, user_id=user.id)
        db.commit()

        t0 = utcnow()
        arrival_service.schedule_departure_reminder(db, token, (23.22, 72.65), now=t0)
        db.commit()

        token_service.apply_transition(db, token, TokenStatus.ARRIVED.value)
        arrival_service.cancel_reminders(db, token.id)
        db.commit()

        sent = arrival_service.process_due_reminders(db, now=t0 + timedelta(hours=2))
        assert sent == 0
        rows = db.scalars(
            select(ScheduledReminder).where(ScheduledReminder.token_id == token.id)
        ).all()
        assert rows and all(row.status == ReminderStatus.CANCELLED.value for row in rows)
    finally:
        db.close()


def test_arrival_endpoints_are_wired(app, client):
    from app.db import SessionLocal
    from app.models import Office

    config = client.get("/api/arrival/config")
    assert config.status_code == 200
    assert config.json()["provider"] in {"mock", "osrm", "none"}

    db = SessionLocal()
    try:
        service = _service(db)
        office = db.get(Office, service.department.office_id)
        office.latitude = 23.2231
        office.longitude = 72.6500
        db.commit()
        service_id = service.id
        office_id = office.id
    finally:
        db.close()

    response = client.get("/api/arrival/offices", params={"service_id": service_id, "lat": 23.22, "lng": 72.65})
    assert response.status_code == 200
    body = response.json()
    assert "offices" in body and "explanation" in body

    # Passing selected_office_id returns the "best for you" assessment.
    assessed = client.get(
        "/api/arrival/offices",
        params={"service_id": service_id, "lat": 23.22, "lng": 72.65, "selected_office_id": office_id},
    )
    assert assessed.status_code == 200
    assert assessed.json()["assessment"]["office_id"] == office_id

    bad = client.get("/api/arrival/offices", params={"service_id": service_id, "lat": 999, "lng": 72.65})
    assert bad.status_code == 422
