"""Counter-level and office-level authorization for staff-facing operations."""
from __future__ import annotations

import uuid

from sqlalchemy import select


def _staff_with_assignment(db, counters: list) -> dict:
    """Create a STAFF user assigned only to the supplied counters, return headers."""
    from app.models import StaffAssignment, User
    from app.security import create_access_token, hash_password

    staff = User(
        email=f"authz-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Authorized Staff", password_hash=hash_password("Sup3r-secret"), role="STAFF",
    )
    db.add(staff)
    db.flush()
    for counter in counters:
        db.add(StaffAssignment(user_id=staff.id, office_id=counter.office_id, counter_id=counter.id, is_active=True))
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(subject=staff.id, role=staff.role)}"}


def test_staff_cannot_operate_unassigned_counter(client):
    from app.db import SessionLocal
    from app.models import Counter, Service

    db = SessionLocal()
    try:
        office_id = db.scalar(select(Counter.office_id).order_by(Counter.office_id))
        counters = db.scalars(select(Counter).where(Counter.office_id == office_id).order_by(Counter.number)).all()
        service_id = db.scalar(select(Service.id))
        headers = _staff_with_assignment(db, counters[:2])

        # The unassigned third counter is invisible and inoperable.
        invisible = client.get("/api/staff/counters", params={"office_id": office_id}, headers=headers).json()
        assert {c["id"] for c in invisible} == {counters[0].id, counters[1].id}

        third = counters[2]
        denied = client.post(f"/api/staff/counters/{third.id}/call-next", json={"service_id": service_id}, headers=headers)
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "counter_not_assigned"

        assert client.patch(f"/api/staff/counters/{third.id}", json={"status": "BREAK"}, headers=headers).status_code == 403
        assert client.post(f"/api/staff/counters/{third.id}/start", headers=headers).status_code == 403

        # The dashboard hides everything outside the member's assignments.
        dashboard = client.get("/api/staff/dashboard", params={"office_id": office_id}, headers=headers).json()
        assert {c["id"] for c in dashboard["counters"]} == {counters[0].id, counters[1].id}
    finally:
        db.close()


def test_staff_office_scope_is_enforced(client):
    from app.db import SessionLocal
    from app.models import Counter, Department, Office, Service

    db = SessionLocal()
    try:
        office_a = db.scalar(select(Office).order_by(Office.id))
        counter_a = db.scalar(select(Counter).where(Counter.office_id == office_a.id).order_by(Counter.number))

        office_b = Office(code="office-b", name="Branch Office", address="Elsewhere")
        db.add(office_b)
        db.flush()
        department_b = Department(office_id=office_b.id, name="Branch Department")
        db.add(department_b)
        db.flush()
        service_b = Service(department_id=department_b.id, code="branch-svc", name="Branch Service",
                            description="Branch", average_service_min=5.0)
        db.add(service_b)
        db.flush()
        counter_b = Counter(office_id=office_b.id, number=1, name="Branch Counter")
        db.add(counter_b)
        db.commit()

        # Member is assigned only to office A.
        headers = _staff_with_assignment(db, [counter_a])

        assert client.get("/api/staff/counters", params={"office_id": office_b.id}, headers=headers).status_code == 403
        assert client.get("/api/staff/queue", params={"office_id": office_b.id, "service_id": service_b.id}, headers=headers).status_code == 403
        dashboard = client.get("/api/staff/dashboard", params={"office_id": office_b.id}, headers=headers)
        assert dashboard.status_code == 403

        incident = client.post("/api/staff/incidents", headers=headers, json={
            "office_id": office_b.id,
            "incident_type": "DELAY",
            "description": "Long queue at the branch",
            "ends_at": "2030-01-01T12:00:00+00:00",
        })
        assert incident.status_code == 403
        assert incident.json()["error"]["code"] == "office_not_assigned"

        # Analytics outside the assignment scope is also refused for STAFF.
        assert client.get("/api/analytics/overview", params={"office_id": office_b.id}, headers=headers).status_code == 403
        # ...but the member can read their own office.
        assert client.get("/api/analytics/overview", params={"office_id": office_a.id}, headers=headers).status_code == 200
    finally:
        db.close()


def test_staff_dashboard_without_any_assignment(client):
    from app.db import SessionLocal
    from app.models import User
    from app.security import create_access_token, hash_password

    db = SessionLocal()
    try:
        staff = User(email=f"unassigned-{uuid.uuid4().hex[:8]}@example.com", full_name="Unassigned",
                     password_hash=hash_password("Sup3r-secret"), role="STAFF")
        db.add(staff)
        db.commit()
        headers = {"Authorization": f"Bearer {create_access_token(subject=staff.id, role=staff.role)}"}

        dashboard = client.get("/api/staff/dashboard", headers=headers)
        assert dashboard.status_code == 403
        assert dashboard.json()["error"]["code"] == "no_assigned_counters"

        # The scope endpoint still answers and is empty.
        scope = client.get("/api/staff/scope", headers=headers)
        assert scope.status_code == 200
        assert scope.json()["offices"] == []

        assert client.get("/api/analytics/overview", headers=headers).status_code == 403
    finally:
        db.close()