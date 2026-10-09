def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "request" in r.headers.get("X-Request-ID", "").lower() or r.headers.get("X-Request-ID")


def test_offices_catalog(client):
    r = client.get("/api/offices")
    assert r.status_code == 200
    assert r.json()[0]["name"]


def test_queue_snapshot_shape(client):
    r = client.get("/api/queue")
    assert r.status_code == 200
    body = r.json()
    for key in ("waiting", "active_counters", "average_service_min", "tokens", "prediction"):
        assert key in body


def test_structured_404(client):
    r = client.get("/api/tokens/does-not-exist")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "not_found"
    assert err["request_id"]
