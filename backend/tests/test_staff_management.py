"""Admin staff management: OTP-verified staff creation and counter assignments."""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select


def _admin_headers(db) -> dict:
    from app.models import User
    from app.security import create_access_token, hash_password

    admin = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Test Admin", password_hash=hash_password("Sup3r-secret"), role="ADMIN",
    )
    db.add(admin)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(subject=admin.id, role=admin.role)}"}


def _send_staff_otp(client, db, headers, email=None) -> tuple[str, str]:
    """Send a staff-creation OTP and return (email, code) by reading the log."""
    from app.models import Notification

    password = "Str0ng-pass"
    email = email or f"staff-new-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/admin/staff/otp", headers=headers,
        json={"full_name": "New Staff", "email": email, "password": password, "confirm_password": password},
    )
    assert resp.status_code == 202, resp.text
    row = db.scalar(select(Notification).where(Notification.recipient == email).order_by(Notification.id.desc()))
    assert row is not None, "OTP email should be queued"
    return email, re.search(r"\b\d{6}\b", row.body).group(0)


def test_staff_management_requires_admin(client):
    from app.db import SessionLocal
    from app.models import User
    from app.security import create_access_token, hash_password

    db = SessionLocal()
    try:
        staff = User(email=f"staff-nonauth-{uuid.uuid4().hex[:8]}@example.com", full_name="Staff",
                     password_hash=hash_password("Sup3r-secret"), role="STAFF")
        citizen = User(email=f"citizen-nonauth-{uuid.uuid4().hex[:8]}@example.com", full_name="Citizen",
                       password_hash=hash_password("Sup3r-secret"), role="CITIZEN")
        db.add_all([staff, citizen])
        db.commit()
        staff_headers = {"Authorization": f"Bearer {create_access_token(subject=staff.id, role=staff.role)}"}
        citizen_headers = {"Authorization": f"Bearer {create_access_token(subject=citizen.id, role=citizen.role)}"}
    finally:
        db.close()

    for url in ("/api/admin/staff", "/api/admin/staff/1/assignments"):
        assert client.get(url, headers=staff_headers).status_code == 403
        assert client.get(url, headers=citizen_headers).status_code == 403
    assert client.post("/api/admin/staff/otp", headers=staff_headers, json={
        "full_name": "X", "email": "x@example.com", "password": "password", "confirm_password": "password",
    }).status_code == 403
    assert client.get("/api/admin/staff").status_code == 401


def test_admin_creates_staff_only_after_email_otp_verification(client):
    from app.db import SessionLocal
    from app.models import Notification, StaffOTPChallenge, User

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        db.commit()

        # Not verified yet -> the account must NOT be created.
        email = f"staff-flow-{uuid.uuid4().hex[:8]}@example.com"
        blocked = client.post("/api/admin/staff", headers=headers, json={"email": email})
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "verification_required"
        assert db.scalar(select(User.id).where(User.email == email)) is None

        email, otp = _send_staff_otp(client, db, headers, email)
        # A wrong code must not verify (and it burns an attempt).
        assert client.post("/api/admin/staff/otp/verify", headers=headers, json={"email": email, "otp": "000000"}).status_code == 400

        verified = client.post("/api/admin/staff/otp/verify", headers=headers, json={"email": email, "otp": otp})
        assert verified.status_code == 200
        assert verified.json()["verified"] is True

        created = client.post("/api/admin/staff", headers=headers, json={"email": email})
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["role"] == "STAFF"
        assert body["email"] == email

        # The one-time challenge is spent, the account exists and is listed.
        assert db.scalar(select(StaffOTPChallenge).where(StaffOTPChallenge.email == email)) is None
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None and user.role == "STAFF"
        assert db.scalar(select(Notification.id).where(Notification.dedupe_key == f"staff-welcome:{user.id}"))
        assert any(m["email"] == email for m in client.get("/api/admin/staff", headers=headers).json())

        # The challenge cannot be spent twice.
        again = client.post("/api/admin/staff", headers=headers, json={"email": email})
        assert again.status_code in (409, 404)
    finally:
        db.close()


def test_staff_otp_validation(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        db.commit()

        # Password mismatch is rejected before any email is sent.
        resp = client.post("/api/admin/staff/otp", headers=headers, json={
            "full_name": "New Staff", "email": "mismatch@example.com",
            "password": "Str0ng-pass", "confirm_password": "D1fferent",
        })
        assert resp.status_code == 422 and resp.json()["error"]["code"] == "password_mismatch"

        # Emails that already own an account are refused.
        from app.models import User
        from app.security import hash_password

        existing = User(email="already-taken@example.com", full_name="Taken",
                        password_hash=hash_password("Str0ng-pass"), role="CITIZEN")
        db.add(existing)
        db.commit()
        resp = client.post("/api/admin/staff/otp", headers=headers, json={
            "full_name": "New Staff", "email": "ALREADY-TAKEN@example.com",
            "password": "Str0ng-pass", "confirm_password": "Str0ng-pass",
        })
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "email_taken"

        # Immediate resend is blocked by the cooldown window.
        email, _otp = _send_staff_otp(client, db, headers)
        resp = client.post("/api/admin/staff/otp", headers=headers, json={
            "full_name": "New Staff", "email": email,
            "password": "Str0ng-pass", "confirm_password": "Str0ng-pass",
        })
        assert resp.status_code == 429 and resp.json()["error"]["code"] == "otp_resend_limited"

        # Verification against a code issued to another email fails.
        other = client.post("/api/admin/staff/otp/verify", headers=headers, json={"email": "nobody@example.com", "otp": "123456"})
        assert other.status_code == 400 and other.json()["error"]["code"] == "invalid_otp"
    finally:
        db.close()


def test_counter_assignment_lifecycle(client):
    from app.db import SessionLocal
    from app.models import Counter, Office

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        email = f"staff-assign-{uuid.uuid4().hex[:8]}@example.com"
        email, otp = _send_staff_otp(client, db, headers, email)
        client.post("/api/admin/staff/otp/verify", headers=headers, json={"email": email, "otp": otp})
        staff_id = client.post("/api/admin/staff", headers=headers, json={"email": email}).json()["id"]
        db.commit()

        office = db.scalar(select(Office).order_by(Office.id))
        counters = db.scalars(select(Counter).where(Counter.office_id == office.id).order_by(Counter.number)).all()
        c1, c2, c3 = counters[0], counters[1], counters[2]

        put = client.put(f"/api/admin/staff/{staff_id}/assignments", headers=headers, json={
            "office_id": office.id, "counter_ids": [c1.id, c2.id],
            "title": "Service Officer", "shift_start": "09:30", "shift_end": "18:00",
        })
        assert put.status_code == 200, put.text

        # Staff sees exactly the assigned counters in its own scope + console.
        from app.security import create_access_token
        from app.models import User

        staff = db.get(User, staff_id)
        staff_headers = {"Authorization": f"Bearer {create_access_token(subject=staff.id, role=staff.role)}"}
        scope = client.get("/api/staff/scope", headers=staff_headers).json()
        assert scope["offices"] == [office.id]
        assert sorted(scope["counters"]) == sorted([c1.id, c2.id])

        listed = client.get(f"/api/staff/counters?office_id={office.id}", headers=staff_headers).json()
        assert {c["id"] for c in listed} == {c1.id, c2.id}

        # Counter-level authorization: assigned counters work, unassigned do not.
        assert client.patch(f"/api/staff/counters/{c1.id}", json={"status": "BREAK"}, headers=staff_headers).status_code == 200
        denied = client.patch(f"/api/staff/counters/{c3.id}", json={"status": "BREAK"}, headers=staff_headers)
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "counter_not_assigned"
        assert client.post(f"/api/staff/counters/{c3.id}/call-next", json={"service_id": counters[0].id}, headers=staff_headers).status_code == 403

        # Re-assign: remove c1, add c3; title shifts apply to kept rows.
        put2 = client.put(f"/api/admin/staff/{staff_id}/assignments", headers=headers, json={
            "office_id": office.id, "counter_ids": [c2.id, c3.id],
            "title": "Senior Service Officer", "shift_start": "08:00", "shift_end": "17:00",
        })
        assert put2.status_code == 200
        assignments = client.get(f"/api/admin/staff/{staff_id}/assignments", headers=headers).json()
        assert {a["counter_id"] for a in assignments} == {c2.id, c3.id}
        assert all(a["title"] == "Senior Service Officer" for a in assignments)

        # Re-running the same set is idempotent (unique user/counter row).
        put3 = client.put(f"/api/admin/staff/{staff_id}/assignments", headers=headers, json={
            "office_id": office.id, "counter_ids": [c2.id, c3.id],
            "title": "Senior Service Officer", "shift_start": "08:00", "shift_end": "17:00",
        })
        assert put3.status_code == 200
        assert len(client.get(f"/api/admin/staff/{staff_id}/assignments", headers=headers).json()) == 2

        # /api/admin/counters lists each counter with its assigned staff.
        directory = client.get(f"/api/admin/counters?office_id={office.id}", headers=headers).json()
        c3_entry = next(c for c in directory if c["id"] == c3.id)
        assert any(s["user_id"] == staff.id for s in c3_entry["staff"])
    finally:
        db.close()


def test_assignment_validations(client):
    from app.db import SessionLocal
    from app.models import Counter, Department, Office

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        email = f"staff-valid-{uuid.uuid4().hex[:8]}@example.com"
        email, otp = _send_staff_otp(client, db, headers, email)
        client.post("/api/admin/staff/otp/verify", headers=headers, json={"email": email, "otp": otp})
        staff_id = client.post("/api/admin/staff", headers=headers, json={"email": email}).json()["id"]
        db.commit()

        office = db.scalar(select(Office).order_by(Office.id))
        counter = db.scalar(select(Counter).where(Counter.office_id == office.id).order_by(Counter.number))

        # A counter that does not exist is rejected.
        resp = client.put(f"/api/admin/staff/{staff_id}/assignments", headers=headers, json={
            "office_id": office.id, "counter_ids": [999_999],
        })
        assert resp.status_code == 400 and resp.json()["error"]["code"] == "invalid_counter"

        # Assigning a counter from another office is rejected.
        other_office = Office(code="other-office", name="Other Office", address="Elsewhere")
        db.add(other_office)
        db.flush()
        other_counter = Counter(office_id=other_office.id, number=1, name="Other Counter")
        db.add(other_counter)
        db.commit()
        resp = client.put(f"/api/admin/staff/{staff_id}/assignments", headers=headers, json={
            "office_id": office.id, "counter_ids": [other_counter.id],
        })
        assert resp.status_code == 400 and resp.json()["error"]["code"] == "cross_office_assignment"

        # Anonymous/citizen access to the admin counter directory is denied.
        assert client.get(f"/api/admin/counters?office_id={office.id}").status_code == 401

        # Staff cannot view or change another member's assignments.
        from app.models import User
        from app.security import create_access_token

        other_staff = User(email=f"other-staff-{uuid.uuid4().hex[:8]}@example.com", full_name="Other",
                           password_hash="x", role="STAFF")
        db.add(other_staff)
        db.commit()
        other_headers = {"Authorization": f"Bearer {create_access_token(subject=other_staff.id, role=other_staff.role)}"}
        assert client.put(f"/api/admin/staff/{staff_id}/assignments", headers=other_headers, json={
            "office_id": office.id, "counter_ids": [counter.id],
        }).status_code == 403
    finally:
        db.close()


def test_counter_assignment_service_scope(client):
    from app.db import SessionLocal
    from app.models import Counter, CounterService, Department, Office, Service, User
    from app.security import create_access_token, hash_password

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        office = db.scalar(select(Office).order_by(Office.id))
        services = db.scalars(
            select(Service)
            .join(Department, Service.department_id == Department.id)
            .where(Department.office_id == office.id)
            .order_by(Service.id)
        ).all()
        while len(services) < 3:
            department = db.scalar(select(Department).where(Department.office_id == office.id))
            if department is None:
                department = Department(office_id=office.id, name="Scope Dept")
                db.add(department)
                db.flush()
            extra = Service(department_id=department.id, name=f"Scoped Service {len(services)}", code=f"scoped-{uuid.uuid4().hex[:6]}")
            db.add(extra)
            db.commit()
            services = db.scalars(
                select(Service)
                .join(Department, Service.department_id == Department.id)
                .where(Department.office_id == office.id)
                .order_by(Service.id)
            ).all()
        svc_a, svc_b, svc_c = services[0], services[1], services[2]

        counter = Counter(office_id=office.id, number=900, name="Scoped Counter")
        db.add(counter)
        db.flush()
        db.add_all([
            CounterService(counter_id=counter.id, service_id=svc_a.id),
            CounterService(counter_id=counter.id, service_id=svc_b.id),
        ])
        staff = User(email=f"staff-scope-{uuid.uuid4().hex[:8]}@example.com", full_name="Scoped",
                     password_hash=hash_password("Str0ng-pass"), role="STAFF")
        db.add(staff)
        db.commit()
        staff_id = staff.id
        staff_headers = {"Authorization": f"Bearer {create_access_token(subject=staff.id, role=staff.role)}"}

        # Scoped assignment: only svc_a may be served at this counter.
        put = client.put(f"/api/admin/staff/{staff_id}/assignments", headers=headers, json={
            "office_id": office.id, "counter_ids": [counter.id],
            "services_by_counter": {str(counter.id): [svc_a.id]},
        })
        assert put.status_code == 200, put.text
        row = next(a for a in client.get(f"/api/admin/staff/{staff_id}/assignments", headers=headers).json()
                   if a["counter_id"] == counter.id)
        assert row["service_ids"] == [svc_a.id]

        # The staff scope exposes exactly the assigned service (so the console
        # can offer the service the member must serve, even if the public
        # catalog hides it).
        scope = client.get("/api/staff/scope", headers=staff_headers)
        assert scope.status_code == 200
        scope_service_ids = {s["id"] for s in scope.json()["services"]}
        assert svc_a.id in scope_service_ids
        assert svc_b.id not in scope_service_ids
        assert svc_c.id not in scope_service_ids

        # In-scope service clears the scope gate (empty queue -> queue_empty, not 403).
        allowed = client.post(f"/api/staff/counters/{counter.id}/call-next",
                              json={"service_id": svc_a.id}, headers=staff_headers)
        assert allowed.status_code != 403, allowed.text

        # Out-of-scope service (served by the counter but not assigned) is refused.
        denied = client.post(f"/api/staff/counters/{counter.id}/call-next",
                             json={"service_id": svc_b.id}, headers=staff_headers)
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "service_not_assigned"

        # A service the counter does not serve cannot be scoped to it.
        bad = client.put(f"/api/admin/staff/{staff_id}/assignments", headers=headers, json={
            "office_id": office.id, "counter_ids": [counter.id],
            "services_by_counter": {str(counter.id): [svc_c.id]},
        })
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "service_not_served_by_counter"

        # Omitting the scope leaves the assignment unrestricted (backward compatible).
        plain = client.put(f"/api/admin/staff/{staff_id}/assignments", headers=headers, json={
            "office_id": office.id, "counter_ids": [counter.id],
        })
        assert plain.status_code == 200, plain.text
        row = next(a for a in client.get(f"/api/admin/staff/{staff_id}/assignments", headers=headers).json()
                   if a["counter_id"] == counter.id)
        assert row["service_ids"] == []
        now_allowed = client.post(f"/api/staff/counters/{counter.id}/call-next",
                                  json={"service_id": svc_b.id}, headers=staff_headers)
        assert now_allowed.status_code != 403, now_allowed.text
    finally:
        db.close()