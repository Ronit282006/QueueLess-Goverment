"""QR token and check-in tests (Phase 8)."""
from __future__ import annotations


def _service_id(client) -> int:
    offices = client.get("/api/offices").json()
    return offices[0]["departments"][0]["services"][0]["id"]


def test_qr_payload_roundtrip():
    from app.services import qr_service

    payload = qr_service.qr_payload("abc123")
    assert payload == "queueless://token/abc123"
    assert qr_service.reference_from_payload(payload) == "abc123"
    assert qr_service.reference_from_payload("abc123") == "abc123"
    assert qr_service.reference_from_payload("http://evil/x") is None
    assert qr_service.reference_from_payload("") is None


def test_token_exposes_scannable_qr(client):
    token = client.post("/api/tokens", json={"service_id": _service_id(client)}).json()
    assert token["qr_data_url"].startswith("data:image/png;base64,")


def test_check_in_by_qr_payload(client):
    from app.services import qr_service

    token = client.post("/api/tokens", json={"service_id": _service_id(client)}).json()
    response = client.post(
        "/api/tokens/check-in",
        json={"qr_payload": qr_service.qr_payload(token["reference"])},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ARRIVED"

    # Re-scanning is idempotent rather than an error.
    again = client.post("/api/tokens/check-in", json={"reference": token["reference"]})
    assert again.status_code == 200
    assert again.json()["status"] == "ARRIVED"


def test_check_in_rejects_bad_payload(client):
    # A non-QueueLess URL is not a valid QR payload.
    bad = client.post("/api/tokens/check-in", json={"qr_payload": "http://evil/x"})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_qr"

    # A well-formed but unknown reference is simply not found.
    unknown = client.post("/api/tokens/check-in", json={"qr_payload": "queueless://token/does-not-exist"})
    assert unknown.status_code == 404