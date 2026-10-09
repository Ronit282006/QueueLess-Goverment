"""Realtime WebSocket tests (Phase 6).

Redis is intentionally unreachable in the test environment so the hub exercises
its local fan-out fallback deterministically. Multi-instance relay is verified
separately by scripts/load_test.py against live servers.
"""
from __future__ import annotations


def _service_id(client) -> int:
    offices = client.get("/api/offices").json()
    return offices[0]["departments"][0]["services"][0]["id"]


def test_websocket_pushes_queue_updates(client):
    service_id = _service_id(client)
    with client.websocket_connect(f"/ws/queue?service_id={service_id}") as ws:
        initial = ws.receive_json()
        assert initial["type"] == "queue.updated"

        client.post("/api/tokens", json={"service_id": service_id})

        update = ws.receive_json()
        assert update["type"] == "queue.updated"
        assert update["service_id"] == service_id


def test_websocket_pushes_token_updates(client):
    service_id = _service_id(client)
    token = client.post("/api/tokens", json={"service_id": service_id}).json()
    reference = token["reference"]

    with client.websocket_connect(f"/ws/tokens/{reference}") as ws:
        assert ws.receive_json()["type"] == "token.updated"
        client.post("/api/tokens/check-in", json={"reference": reference})
        update = ws.receive_json()
        assert update["type"] == "token.updated"
        assert update["token"]["status"] == "ARRIVED"
