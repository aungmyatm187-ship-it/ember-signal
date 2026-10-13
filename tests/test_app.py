"""Routes that do not need the engine."""

import json
import os

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


def test_health_reports_service_and_engine(client):
    body = client.get("/api/health").get_json()
    assert body["status"] == "healthy"
    assert body["service"] == "ember-signal"
    assert "engine" in body and "available" in body["engine"]


def test_missing_evidence_is_reported_not_hidden(client, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "EVIDENCE_PATH", str(tmp_path / "nope.json"))
    body = app_module.get_json_evidence()
    assert body["error"] == "evidence_file_missing"


def test_malformed_evidence_is_reported(client, tmp_path, monkeypatch):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    monkeypatch.setattr(app_module, "EVIDENCE_PATH", str(bad))
    body = app_module.get_json_evidence()
    assert body["error"] == "evidence_file_invalid_json"
    assert "detail" in body
