"""
ember-signal <-> ember-lite integration.

ember-lite is a local-first CLI, not a pip package, so ember-signal reaches it
through short-lived Python subprocesses that import the engine and print a JSON
envelope. When the engine is not configured or not reachable, callers get an
explicit error instead of fabricated data.
"""

from .engine import EngineError, EngineUnavailable, engine_status, run_operation
from .routes import build_blueprint

__all__ = [
    "EngineError",
    "EngineUnavailable",
    "engine_status",
    "run_operation",
    "build_blueprint",
]
