"""Tests for the Ember Signal Flask app.

These exercise the real app and the real data.db / evidence file (no mocks).
"""

import json
import os
import sqlite3

import pytest

import app as ember


@pytest.fixture()
def client():
    ember.app.config.update(TESTING=True)
    return ember.app.test_client()


def test_index_renders_dashboard(client):
    resp = client.get('/')
    assert resp.status_code == 200
    assert b'Ember Signal' in resp.data


def test_signals_returns_expected_shape(client):
    resp = client.get('/api/signals')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert set(payload) == {'top_brands', 'evidence'}
    assert isinstance(payload['top_brands'], list)
    assert isinstance(payload['evidence'], dict)


def test_top_brands_excludes_null_values(client):
    brands = client.get('/api/signals').get_json()['top_brands']
    # Every returned row must have a non-null brand_value and 3 columns.
    assert all(len(row) == 3 for row in brands)
    assert all(row[2] is not None for row in brands)


def test_top_brands_sorted_descending(client):
    values = [row[2] for row in client.get('/api/signals').get_json()['top_brands']]
    assert values == sorted(values, reverse=True)


def test_top_brands_limited_to_ten(client):
    brands = client.get('/api/signals').get_json()['top_brands']
    assert len(brands) <= 10


def test_evidence_matches_source_file(client):
    with open(ember.EVIDENCE_PATH) as f:
        expected = json.load(f)
    assert client.get('/api/signals').get_json()['evidence'] == expected


def test_missing_evidence_degrades_gracefully(client, monkeypatch):
    monkeypatch.setattr(ember, 'EVIDENCE_PATH', '/nonexistent/evidence.json')
    payload = client.get('/api/signals').get_json()
    assert payload['evidence']['error'] == 'Evidence file not found'


def test_malformed_evidence_degrades_gracefully(client, tmp_path, monkeypatch):
    bad = tmp_path / 'evidence.json'
    bad.write_text('{not valid json')
    monkeypatch.setattr(ember, 'EVIDENCE_PATH', str(bad))
    payload = client.get('/api/signals').get_json()
    assert payload['evidence']['error'] == 'Evidence file not found'


def test_db_data_is_sorted_and_filtered():
    rows = ember.get_db_data()
    assert all(row[2] is not None for row in rows)
    assert [r[2] for r in rows] == sorted((r[2] for r in rows), reverse=True)
