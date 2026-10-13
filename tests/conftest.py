"""
Shared fixtures.

The engine integration tests run against a real ember-lite checkout (a real
subprocess), never a mock. If no checkout is reachable they skip, so the suite
still passes on a machine without the engine.
"""

import os

import pytest

from app import app as flask_app

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _detect_engine_dir():
    configured = os.environ.get("EMBER_LITE_DIR")
    if configured and os.path.isdir(os.path.join(configured, "perception")):
        return configured
    sibling = os.path.join(os.path.dirname(REPO_ROOT), "ember-lite")
    if os.path.isdir(os.path.join(sibling, "perception")):
        return sibling
    return None


@pytest.fixture(scope="session")
def engine_dir():
    """Path to a real ember-lite checkout, or skip the test."""
    found = _detect_engine_dir()
    if not found:
        pytest.skip("no ember-lite checkout available (set EMBER_LITE_DIR)")
    os.environ["EMBER_LITE_DIR"] = found
    return found


@pytest.fixture()
def client():
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()
