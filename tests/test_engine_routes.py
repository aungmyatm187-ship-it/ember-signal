"""
Engine integration routes, exercised against a real ember-lite subprocess.

These tests assert the honesty contract: with an engine present the routes
return real data; with the engine absent they return 503/502, never a
fabricated payload.
"""

import pytest

from ember_signal import engine


@pytest.fixture()
def without_engine(monkeypatch):
    monkeypatch.setenv("EMBER_LITE_DIR", "/nonexistent/ember-lite")


def test_engine_status_reports_availability(engine_dir):
    status = engine.engine_status()
    assert status["available"] is True
    assert status["configured_dir"] == engine_dir


def test_chain_returns_real_summary_and_verification(engine_dir, client):
    resp = client.get("/api/evidence/chain")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert set(data) == {"summary", "verify"}
    assert data["summary"]["schema_version"] == "2.0"
    assert isinstance(data["verify"]["valid"], bool)


def test_gate_evaluates_and_never_fabricates(engine_dir, client):
    resp = client.get("/api/gate")
    assert resp.status_code == 200
    evaluation = resp.get_json()["data"]["evaluation"]
    assert evaluation["decision"] in {"SHIP", "REVIEW", "NO_SHIP"}
    # unknown gates are allowed; a silent default is not.
    assert "gates_unknown" in evaluation


def test_govern_returns_summary(engine_dir, client):
    resp = client.get("/api/govern")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert "active_policies" in data and "approval_gates" in data


def test_missing_engine_is_unavailable_not_fabricated(without_engine, client):
    for path in ("/api/evidence/chain", "/api/gate", "/api/govern", "/api/perceive"):
        resp = client.get(path)
        assert resp.status_code == 503, path
        assert resp.get_json()["error"] == "engine_unavailable"


def test_health_still_up_when_engine_down(without_engine, client):
    body = client.get("/api/health").get_json()
    assert body["status"] == "healthy"
    assert body["engine"]["available"] is False


def test_unknown_operation_is_engine_error():
    with pytest.raises(engine.EngineError):
        engine.run_operation("does-not-exist")
