"""Routes that do not need the engine, including the live consumer contract."""

import app as app_module


def test_index_serves_dashboard(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Ember Signal" in resp.data


def test_signals_returns_real_brands(client):
    resp = client.get("/api/signals")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["top_brands"], "expected brands from data.db"
    assert body["evidence"]["records"][0]["id"] == "real-record-001"


def test_signals_matches_live_consumer_contract(client):
    """The lumafoundry.live bridge (emberSignalSource.ts) parses this shape.

    It requires `evidence` as an array of records with these exact keys, and
    `top_brands` as [name, region, value] tuples with a numeric value.
    """
    body = client.get("/api/signals").get_json()

    assert isinstance(body["top_brands"], list)
    for row in body["top_brands"]:
        assert isinstance(row, list) and len(row) == 3
        assert isinstance(row[0], str) and row[0]
        assert isinstance(row[1], str) and row[1]
        assert isinstance(row[2], (int, float))

    records = body["evidence"]["records"]
    assert isinstance(records, list)
    for record in records:
        for key in ("id", "title", "source", "observedAt", "status", "summary"):
            assert key in record, key
        assert record["status"] in {"observed", "verified", "pending", "blocked"}


def test_top_brands_sorted_descending_and_non_null(client):
    brands = client.get("/api/signals").get_json()["top_brands"]
    values = [row[2] for row in brands]
    assert all(v is not None for v in values)
    assert values == sorted(values, reverse=True)
    assert len(brands) <= 10


def test_health_reports_service_and_engine(client):
    body = client.get("/api/health").get_json()
    assert body["status"] == "healthy"
    assert body["service"] == "ember-signal"
    assert "engine" in body and "available" in body["engine"]


def test_missing_evidence_is_reported_not_hidden(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "EVIDENCE_PATH", str(tmp_path / "nope.json"))
    body = app_module.get_json_evidence()
    assert body["error"] == "evidence_file_missing"


def test_malformed_evidence_is_reported(tmp_path, monkeypatch):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    monkeypatch.setattr(app_module, "EVIDENCE_PATH", str(bad))
    body = app_module.get_json_evidence()
    assert body["error"] == "evidence_file_invalid_json"
    assert "detail" in body


def test_cors_off_by_default(client):
    resp = client.get("/api/signals")
    assert "Access-Control-Allow-Origin" not in resp.headers


def test_cors_enabled_when_configured(client, monkeypatch):
    monkeypatch.setenv("EMBER_CORS_ORIGIN", "https://lumafoundry.live")
    resp = client.get("/api/signals")
    assert resp.headers["Access-Control-Allow-Origin"] == "https://lumafoundry.live"
    assert resp.headers["Vary"] == "Origin"
