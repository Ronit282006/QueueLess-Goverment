"""Admin API tests (Phase 10): catalog, priority rules, recommendations, audit, health."""
from __future__ import annotations

import uuid


def _headers(client, role: str) -> dict:
    from app.db import SessionLocal
    from app.models import User
    from app.security import create_access_token, hash_password

    db = SessionLocal()
    try:
        user = User(
            email=f"{role.lower()}-{uuid.uuid4().hex[:8]}@example.com",
            full_name=f"{role} User",
            password_hash=hash_password("Sup3r-secret"),
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return {"Authorization": f"Bearer {create_access_token(subject=user.id, role=user.role)}"}
    finally:
        db.close()


def test_admin_endpoints_are_rbac_guarded(client):
    citizen = _headers(client, "CITIZEN")
    assert client.get("/api/admin/health", headers=citizen).status_code == 403
    assert client.get("/api/admin/health").status_code == 401


def test_admin_health_reports_models_and_counts(client):
    admin = _headers(client, "ADMIN")
    body = client.get("/api/admin/health", headers=admin).json()
    assert body["database"] == "up"
    assert "models" in body
    assert "pending_recommendations" in body


def test_catalog_creation_invalidates_cache(client):
    admin = _headers(client, "ADMIN")
    code = f"OFF-{uuid.uuid4().hex[:6]}"
    office = client.post("/api/admin/offices", json={"code": code, "name": "New Office"}, headers=admin)
    assert office.status_code == 201, office.text
    office_id = office.json()["id"]

    department = client.post(
        "/api/admin/departments", json={"office_id": office_id, "name": "Revenue"}, headers=admin
    ).json()
    service = client.post(
        "/api/admin/services",
        json={
            "department_id": department["id"],
            "code": f"SVC-{uuid.uuid4().hex[:6]}",
            "name": "Passport",
            "documents": ["Aadhaar", "Photo"],
        },
        headers=admin,
    )
    assert service.status_code == 201

    # The public catalog (which is cached) immediately reflects the new office.
    offices = client.get("/api/offices").json()
    assert any(o["id"] == office_id for o in offices)


def test_priority_rule_lifecycle(client):
    admin = _headers(client, "ADMIN")
    created = client.post(
        "/api/admin/priority-rules",
        json={"name": "Senior citizens", "tags": ["Senior Citizen"], "boost": 25},
        headers=admin,
    )
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["tags"] == ["senior citizen"]

    listed = client.get("/api/admin/priority-rules", headers=admin).json()
    assert any(r["id"] == rule["id"] for r in listed)

    updated = client.patch(
        f"/api/admin/priority-rules/{rule['id']}",
        json={"name": "Seniors", "tags": ["senior citizen"], "boost": 30, "is_active": False},
        headers=admin,
    ).json()
    assert updated["boost"] == 30 and updated["is_active"] is False


def test_recommendations_and_audit(client):
    admin = _headers(client, "ADMIN")
    offices = client.get("/api/offices").json()
    office_id = offices[0]["id"]
    service_id = offices[0]["departments"][0]["services"][0]["id"]

    # Overload the first service so a recommendation is warranted.
    for _ in range(12):
        client.post("/api/tokens", json={"service_id": service_id})

    result = client.get(f"/api/admin/recommendations?office_id={office_id}&refresh=true", headers=admin).json()
    assert "items" in result

    logs = client.get("/api/admin/audit-logs?limit=10", headers=admin).json()
    assert isinstance(logs, list)
    assert logs and {"action", "at"} <= set(logs[0])