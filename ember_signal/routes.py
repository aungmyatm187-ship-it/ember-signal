"""
HTTP surface exposing the ember-lite engine.

Every route returns one of three honest states:
  status "ok"          — the engine answered; data is real
  status "unavailable" — the engine could not be reached (503)
  status "error"       — the engine ran but the operation failed (502)

No route invents a payload when the engine is absent.
"""

from flask import Blueprint, jsonify

from .engine import EngineError, EngineUnavailable, engine_status, run_operation


def _respond(operation: str):
    try:
        data = run_operation(operation)
    except EngineUnavailable as exc:
        return (
            jsonify({"status": "unavailable", "error": "engine_unavailable", "detail": exc.detail}),
            503,
        )
    except EngineError as exc:
        return (
            jsonify({"status": "error", "error": exc.kind, "detail": exc.detail}),
            502,
        )
    return jsonify({"status": "ok", "data": data}), 200


def build_blueprint() -> Blueprint:
    bp = Blueprint("ember_engine", __name__)

    @bp.get("/api/evidence/chain")
    def evidence_chain():
        """Signed evidence chain summary + integrity verification."""
        return _respond("chain")

    @bp.get("/api/perceive")
    def perceive():
        """Run a fresh perception pass (reaches the network; may be slow)."""
        return _respond("perceive")

    @bp.get("/api/gate")
    def gate():
        """P5 release-gate evaluation. Missing dimensions report UNKNOWN."""
        return _respond("gate")

    @bp.get("/api/govern")
    def govern():
        """P6 governance summary: policies, capabilities, approval gates."""
        return _respond("govern")

    @bp.get("/api/verify")
    def verify():
        """Whole-chain integrity check (per-block lookup is not exposed yet)."""
        return _respond("chain")

    @bp.get("/api/engine")
    def engine():
        """Report whether the engine is configured and reachable."""
        status = engine_status()
        return jsonify({"status": "ok", "data": status}), 200

    return bp
