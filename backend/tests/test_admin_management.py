"""Admin office, counter, staff and assignment management.

Isolation note: the module creates its own offices/services so it never mutates
the shared session-scoped test office that other modules depend on.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select


def _admin_headers(db) -> dict:
    from app.models import User
    from app.security import create_access_token, hash_password

    admin = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Mgmt Admin", password_hash=hash_password("Sup3r-secret"), role="ADMIN",
    )
    db.add(admin)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(subject=admin.id, role=admin.role)}"}


def _staff_headers(db, *, active: bool = True):
    from app.models import User
    from app.security import create_access_token, hash_password

    staff = User(
        email=f"staff-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Counter Staff", password_hash=hash_password("Sup3r-secret"), role="STAFF",
        is_active=active,
    )
    db.add(staff)
    db.commit()
    return staff, {"Authorization": f"Bearer {create_access_token(subject=staff.id, role=staff.role)}"}


def _test_office(client) -> dict:
    offices = client.get("/api/offices").json()
    office = next(o for o in offices if o["code"] == "test-office")
    service = office["departments"][0]["services"][0]
    return {"office_id": office["id"], "service_id": service["id"], "counters": office}


def _new_office_with_service(client, headers, *, name="New Office") -> tuple[int, int]:
    code = f"off-{uuid.uuid4().hex[:8]}"
    office = client.post("/api/admin/offices", headers=headers, json={
        "code": code,
        "name": name,
        "address": "1 Test Road",
        "city": "Rajkot",
        "state": "Gujarat",
        "pincode": "360001",
        "contact_email": f"{code}@example.com",
        "contact_phone": "+91 90000 00000",
        "open_time": "09:30",
        "close_time": "18:00",
        "working_days": ["mon", "tue", "wed", "thu", "fri"],
    })
    assert office.status_code == 201, office.text
    office_id = office.json()["id"]
    dept = client.post("/api/admin/departments", headers=headers, json={
        "office_id": office_id, "name": "Revenue Department",
    })
    assert dept.status_code == 201, dept.text
    svc = client.post("/api/admin/services", headers=headers, json={
        "department_id": dept.json()["id"],
        "code": f"svc-{uuid.uuid4().hex[:8]}",
        "name": f"Service {uuid.uuid4().hex[:6]}",
        "average_service_min": 6.0,
    })
    assert svc.status_code == 201, svc.text
    return office_id, svc.json()["id"]


# 1. Admin creates an office successfully.
def test_admin_creates_office(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
    finally:
        db.close()
    code = f"create-{uuid.uuid4().hex[:8]}"
    resp = client.post("/api/admin/offices", headers=headers, json={
        "code": code, "name": "City Revenue Office", "address": "MG Road", "city": "Rajkot",
        "state": "Gujarat", "pincode": "360001", "contact_email": "office@example.com",
        "contact_phone": "0281-123456", "open_time": "09:00", "close_time": "17:30",
        "working_days": ["mon", "tue", "wed", "thu", "fri", "sat"],
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == code
    assert body["working_hours"] == "09:00-17:30"
    assert body["is_active"] is True
    # Visible in the admin listing and searchable by city.
    listing = client.get("/api/admin/offices", headers=headers, params={"search": "Rajkot"}).json()
    assert any(o["id"] == body["id"] for o in listing)


# 2. Duplicate office codes are rejected.
def test_duplicate_office_code_rejected(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
    finally:
        db.close()
    payload = {"code": f"dup-{uuid.uuid4().hex[:8]}", "name": "Dup Office"}
    assert client.post("/api/admin/offices", headers=headers, json=payload).status_code == 201
    again = client.post("/api/admin/offices", headers=headers, json=payload)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "code_taken"


# 3. Invalid office information is rejected.
def test_invalid_office_information_rejected(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
    finally:
        db.close()

    bad_email = client.post("/api/admin/offices", headers=headers, json={
        "code": f"bad-{uuid.uuid4().hex[:8]}", "name": "Bad Email", "contact_email": "not-an-email",
    })
    assert bad_email.status_code == 422

    bad_hours = client.post("/api/admin/offices", headers=headers, json={
        "code": f"bad-{uuid.uuid4().hex[:8]}", "name": "Bad Hours",
        "open_time": "18:00", "close_time": "09:00",
    })
    assert bad_hours.status_code == 422

    bad_coords = client.post("/api/admin/offices", headers=headers, json={
        "code": f"bad-{uuid.uuid4().hex[:8]}", "name": "Bad Coords", "latitude": 123.0, "longitude": 200.0,
    })
    assert bad_coords.status_code == 422

    bad_pin = client.post("/api/admin/offices", headers=headers, json={
        "code": f"bad-{uuid.uuid4().hex[:8]}", "name": "Bad Pin", "pincode": "abc",
    })
    assert bad_pin.status_code == 422


# 4. Admin creates a counter under the correct office.
def test_create_counter_under_office(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
    finally:
        db.close()
    office_id, service_id = _new_office_with_service(client, headers)
    resp = client.post(f"/api/admin/offices/{office_id}/counters", headers=headers, json={
        "number": 1, "name": "Counter 1", "code": "C1", "service_ids": [service_id],
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["office_id"] == office_id
    assert body["service_ids"] == [service_id]
    # Duplicate number in same office is rejected.
    dup = client.post(f"/api/admin/offices/{office_id}/counters", headers=headers, json={"number": 1})
    assert dup.status_code == 409


# 5. A counter cannot reference a nonexistent office.
def test_counter_nonexistent_office(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
    finally:
        db.close()
    resp = client.post("/api/admin/offices/999999/counters", headers=headers, json={"number": 1})
    assert resp.status_code == 404


# 6. A counter cannot support a service unavailable at its office.
def test_counter_cannot_support_foreign_service(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
    finally:
        db.close()
    office_a, _service_a = _new_office_with_service(client, headers, name="Office A")
    _office_b, service_b = _new_office_with_service(client, headers, name="Office B")
    resp = client.post(f"/api/admin/offices/{office_a}/counters", headers=headers, json={
        "number": 5, "service_ids": [service_b],
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "service_not_in_office"


# 7. Staff creation follows OTP verification and secure password handling.
def test_staff_creation_requires_verified_otp(client):
    from app.db import SessionLocal
    from app.models import Notification, User

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        email = f"otp-{uuid.uuid4().hex[:8]}@example.com"
        password = "Str0ng-pass"
        # Creating before verification must fail.
        early = client.post("/api/admin/staff", headers=headers, json={"email": email})
        assert early.status_code == 409
        assert early.json()["error"]["code"] == "verification_required"

        assert client.post("/api/admin/staff/otp", headers=headers, json={
            "full_name": "OTP Staff", "email": email, "password": password, "confirm_password": password,
        }).status_code == 202
        row = db.scalar(select(Notification).where(Notification.recipient == email).order_by(Notification.id.desc()))
        code = re.search(r"\b\d{6}\b", row.body).group(0)
        assert client.post("/api/admin/staff/otp/verify", headers=headers, json={"email": email, "otp": code}).status_code == 200

        created = client.post("/api/admin/staff", headers=headers, json={"email": email})
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["role"] == "STAFF"
        # No secrets leak in the response.
        assert "password" not in body and "password_hash" not in body and "otp" not in body

        stored = db.scalar(select(User).where(User.email == email))
        assert stored.password_hash != password and stored.password_hash.startswith("$2")
    finally:
        db.close()


# 8. Duplicate staff accounts are rejected.
def test_duplicate_staff_email_rejected(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        _, _ = _new_office_with_service(client, headers)
        # Send OTP for an email that already exists as a user.
        existing_email = f"exists-{uuid.uuid4().hex[:8]}@example.com"
        password = "Str0ng-pass"
        assert client.post("/api/admin/staff/otp", headers=headers, json={
            "full_name": "Existing", "email": existing_email, "password": password, "confirm_password": password,
        }).status_code == 202
        from app.models import Notification
        row = db.scalar(select(Notification).where(Notification.recipient == existing_email).order_by(Notification.id.desc()))
        code = re.search(r"\b\d{6}\b", row.body).group(0)
        client.post("/api/admin/staff/otp/verify", headers=headers, json={"email": existing_email, "otp": code})
        assert client.post("/api/admin/staff", headers=headers, json={"email": existing_email}).status_code == 201
        # A second OTP send for the same (now existing) email is rejected.
        again = client.post("/api/admin/staff/otp", headers=headers, json={
            "full_name": "Existing", "email": existing_email, "password": password, "confirm_password": password,
        })
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "email_taken"
    finally:
        db.close()


# 9. Admin assigns multiple counters to one staff member.
def test_assign_multiple_counters(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        office_id, service_id = _new_office_with_service(client, headers)
        ids = []
        for n in (1, 2):
            resp = client.post(f"/api/admin/offices/{office_id}/counters", headers=headers, json={
                "number": n, "name": f"Counter {n}", "service_ids": [service_id],
            })
            ids.append(resp.json()["id"])
        staff, _ = _staff_headers(db)
        result = client.put(f"/api/admin/staff/{staff.id}/assignments", headers=headers, json={
            "office_id": office_id, "counter_ids": ids, "title": "Clerk",
        })
        assert result.status_code == 200, result.text
        assigned = {a["counter_id"] for a in result.json()["assignments"]}
        assert assigned == set(ids)
    finally:
        db.close()


# 10. Staff cannot access an unassigned counter.
def test_staff_cannot_access_unassigned_counter(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        office_id, service_id = _new_office_with_service(client, headers)
        c1 = client.post(f"/api/admin/offices/{office_id}/counters", headers=headers, json={"number": 1, "service_ids": [service_id]}).json()["id"]
        c2 = client.post(f"/api/admin/offices/{office_id}/counters", headers=headers, json={"number": 2, "service_ids": [service_id]}).json()["id"]
        staff, staff_auth = _staff_headers(db)
        client.put(f"/api/admin/staff/{staff.id}/assignments", headers=headers, json={
            "office_id": office_id, "counter_ids": [c1],
        })
        allowed = client.patch(f"/api/staff/counters/{c1}", headers=staff_auth, json={"status": "AVAILABLE"})
        assert allowed.status_code == 200, allowed.text
        denied = client.patch(f"/api/staff/counters/{c2}", headers=staff_auth, json={"status": "AVAILABLE"})
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "counter_not_assigned"
    finally:
        db.close()


# 11. Removing an assignment revokes access.
def test_removing_assignment_revokes_access(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        office_id, service_id = _new_office_with_service(client, headers)
        c1 = client.post(f"/api/admin/offices/{office_id}/counters", headers=headers, json={"number": 1, "service_ids": [service_id]}).json()["id"]
        staff, staff_auth = _staff_headers(db)
        client.put(f"/api/admin/staff/{staff.id}/assignments", headers=headers, json={"office_id": office_id, "counter_ids": [c1]})
        assert client.patch(f"/api/staff/counters/{c1}", headers=staff_auth, json={"status": "AVAILABLE"}).status_code == 200
        client.put(f"/api/admin/staff/{staff.id}/assignments", headers=headers, json={"office_id": office_id, "counter_ids": []})
        after = client.patch(f"/api/staff/counters/{c1}", headers=staff_auth, json={"status": "AVAILABLE"})
        assert after.status_code == 403
    finally:
        db.close()


# 12. Inactive staff cannot operate counters.
def test_inactive_staff_cannot_operate(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        office_id, service_id = _new_office_with_service(client, headers)
        c1 = client.post(f"/api/admin/offices/{office_id}/counters", headers=headers, json={"number": 1, "service_ids": [service_id]}).json()["id"]
        staff, staff_auth = _staff_headers(db)
        client.put(f"/api/admin/staff/{staff.id}/assignments", headers=headers, json={"office_id": office_id, "counter_ids": [c1]})
        # Deactivate the staff member.
        assert client.post(f"/api/admin/staff/{staff.id}/status", headers=headers, json={"is_active": False}).status_code == 200
        blocked = client.patch(f"/api/staff/counters/{c1}", headers=staff_auth, json={"status": "AVAILABLE"})
        assert blocked.status_code == 401
    finally:
        db.close()


# 13. Inactive offices cannot receive new bookings.
def test_inactive_office_cannot_book(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        office_id, service_id = _new_office_with_service(client, headers)
        assert client.post(f"/api/admin/offices/{office_id}/status", headers=headers, json={"is_active": False}).status_code == 200
        booking = client.post("/api/tokens", json={"service_id": service_id, "office_id": office_id, "documents_confirmed": []})
        assert booking.status_code == 409
        assert booking.json()["error"]["code"] == "office_inactive"
    finally:
        db.close()


# 14. Historical tokens and audit records remain available after deactivation.
def test_history_preserved_after_deactivation(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        office_id, service_id = _new_office_with_service(client, headers)
        client.post(f"/api/admin/offices/{office_id}/counters", headers=headers, json={"number": 1, "service_ids": [service_id]})
        booked = client.post("/api/tokens", json={"service_id": service_id, "office_id": office_id, "documents_confirmed": []})
        assert booked.status_code == 201, booked.text
        reference = booked.json()["reference"]

        client.post(f"/api/admin/offices/{office_id}/status", headers=headers, json={"is_active": False})
        still_there = client.get(f"/api/tokens/{reference}")
        assert still_there.status_code == 200
        assert still_there.json()["reference"] == reference

        audit = client.get("/api/admin/audit-logs", headers=headers, params={"limit": 200}).json()
        actions = {a["action"] for a in audit}
        assert "office.deactivated" in actions and "office.created" in actions
    finally:
        db.close()


# 15. Existing GPS recommendation + counter listing still integrate with new offices.
def test_new_office_integrates_with_recommendation(client):
    from app.db import SessionLocal
    from app.models import Office

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        office_id, service_id = _new_office_with_service(client, headers)
        office = db.get(Office, office_id)
        office.latitude, office.longitude = 22.3039, 70.8022
        db.commit()
        client.post(f"/api/admin/offices/{office_id}/counters", headers=headers, json={"number": 1, "service_ids": [service_id]})

        recs = client.get("/api/arrival/offices", params={"service_id": service_id, "lat": 22.30, "lng": 70.80})
        assert recs.status_code == 200
        body = recs.json()
        assert any(o["office_id"] == office_id for o in body["offices"])
        # The new counter participates in queue capacity.
        counters = client.get(f"/api/admin/offices/{office_id}/counters", headers=headers).json()
        assert len(counters) == 1 and counters[0]["status"] == "AVAILABLE"
    finally:
        db.close()


# 16. An admin-added office offering the same service joins GPS recommendations.
def test_admin_added_service_joins_gps_recommendation(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        seeded = _test_office(client)
        seeded_service_id = seeded["service_id"]

        code = f"gps-{uuid.uuid4().hex[:8]}"
        office = client.post("/api/admin/offices", headers=headers, json={
            "code": code, "name": "Nana Mova Service Kendra", "address": "Kalavad Road",
            "city": "Rajkot", "state": "Gujarat", "latitude": 22.2905, "longitude": 70.7710,
        })
        assert office.status_code == 201, office.text
        office_id = office.json()["id"]

        # Create the service through the new office-scoped endpoint, reusing the
        # seeded service's name (case/space differences must still match).
        created = client.post(f"/api/admin/offices/{office_id}/services", headers=headers, json={
            "name": "  income certificate ",
            "average_service_min": 5.0,
            "department_name": "Revenue Department",
        })
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["name"] == "income certificate"
        assert body["department_name"] == "Revenue Department"
        assert body["code"]  # auto-generated

        recs = client.get("/api/arrival/offices", params={
            "service_id": seeded_service_id, "lat": 22.30, "lng": 70.78,
        })
        assert recs.status_code == 200, recs.text
        offices = recs.json()["offices"]
        assert any(o["office_id"] == office_id for o in offices), offices
    finally:
        db.close()


# 17. Office service CRUD: create, edit, deactivate, and reject bad input.
def test_office_service_management(client):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        headers = _admin_headers(db)
        code = f"svc-{uuid.uuid4().hex[:8]}"
        office_id = client.post("/api/admin/offices", headers=headers, json={
            "code": code, "name": "Service Mgmt Office",
        }).json()["id"]

        created = client.post(f"/api/admin/offices/{office_id}/services", headers=headers, json={
            "name": "Trade License", "code": f"tl-{uuid.uuid4().hex[:6]}",
            "average_service_min": 8.0, "documents": ["PAN", "Shop photo"],
            "department_name": "Municipal Services",
        })
        assert created.status_code == 201, created.text
        service_id = created.json()["id"]
        assert created.json()["is_active"] is True

        listed = client.get(f"/api/admin/offices/{office_id}/services", headers=headers).json()
        assert any(s["id"] == service_id for s in listed)
        assert next(s for s in listed if s["id"] == service_id)["documents"] == ["PAN", "Shop photo"]

        # Edit and deactivate through PATCH.
        patched = client.patch(f"/api/admin/services/{service_id}", headers=headers, json={
            "name": "Trade License Renewal", "average_service_min": 9.5, "is_active": False,
        })
        assert patched.status_code == 200, patched.text
        assert patched.json()["name"] == "Trade License Renewal"
        assert patched.json()["is_active"] is False

        active_only = client.get(f"/api/admin/offices/{office_id}/services", headers=headers).json()
        assert all(s["id"] != service_id for s in active_only)
        with_inactive = client.get(
            f"/api/admin/offices/{office_id}/services", headers=headers, params={"include_inactive": "true"}
        ).json()
        assert any(s["id"] == service_id for s in with_inactive)

        # Duplicate service codes are rejected.
        dup_code = f"dup-{uuid.uuid4().hex[:6]}"
        assert client.post(f"/api/admin/offices/{office_id}/services", headers=headers, json={
            "name": "First", "code": dup_code,
        }).status_code == 201
        clash = client.post(f"/api/admin/offices/{office_id}/services", headers=headers, json={
            "name": "Second", "code": dup_code,
        })
        assert clash.status_code == 409
        assert clash.json()["error"]["code"] == "service_code_taken"

        # A department from another office cannot be used.
        other_office = client.post("/api/admin/offices", headers=headers, json={
            "code": f"other-{uuid.uuid4().hex[:8]}", "name": "Other Office",
        }).json()["id"]
        other_dept = client.post(f"/api/admin/offices/{other_office}/departments", headers=headers, json={
            "name": "Elsewhere",
        }).json()["id"]
        foreign = client.post(f"/api/admin/offices/{office_id}/services", headers=headers, json={
            "name": "Foreign Dept Service", "department_id": other_dept,
        })
        assert foreign.status_code == 422
        assert foreign.json()["error"]["code"] == "department_not_in_office"
    finally:
        db.close()
