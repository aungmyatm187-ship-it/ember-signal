"""B4 sync service — Flask blueprint mounting the runtime sync on ember-signal-web.

Endpoints
---------
POST /api/sync/run     Ed25519-signed trigger (B5 trust bridge). Clones the
                       backend repo (depth 1) into a temp dir, runs the
                       deterministic transform, atomically swaps data.db +
                       ember-signal-evidence.json, writes sync-state.json.
                       Optionally asks the B1 edge bridge to purge its cache so
                       shoppers see the new evidence within seconds instead of
                       waiting out the edge TTL.

GET  /api/sync/status  Public, read-only: the last sync report verbatim (counts,
                       hash, timestamp). No auth — it leaks nothing sensitive
                       and is exactly what an observer dashboard wants.

Wiring (in app.py)
------------------
    from sync_service import build_sync_blueprint
    app.register_blueprint(build_sync_blueprint())

Configuration (environment)
---------------------------
SYNC_SOURCE_REPO       git URL of ember-signal-backend
                       (default: the public GitHub repo)
SYNC_CLONE_TIMEOUT_S   git clone timeout, default 120
SYNC_PURGE_URL         optional B1 purge endpoint,
                       e.g. https://luma-bridge.<subdomain>.workers.dev/api/signals/purge
SYNC_PURGE_KEY         optional base64 Ed25519 PRIVATE key authorised to purge
                       (must correspond to the worker's ADMIN_PUBLIC_KEY)
LUMA_TRUST_PUBLIC_KEYS JSON {"key-id": "base64 Ed25519 public key", ...}
                       (also used by b5-trust-bridge/trust.py)

Failure honesty
---------------
This service never fabricates a successful sync: any failure returns a JSON
error with the exact stage that failed, and the previous data files stay
untouched (atomic swap + change detection guarantee).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

import sync_core
# B5 lives as ember_signal/trust.py in the deployed repo; keep the direct
# import working when running from this folder during development.
try:
    from ember_signal.trust import TrustError, load_public_keys, verify_signed_request  # type: ignore
except ImportError:  # pragma: no cover - development layout
    from trust import TrustError, load_public_keys, verify_signed_request  # type: ignore

DEFAULT_SOURCE_REPO = "https://github.com/highfive251677-wq/ember-signal-backend.git"


def _env(key: str, default: str | None = None) -> str | None:
    # Flask config first (TESTING friendly), env second.
    value = current_app.config.get(key)
    if value is not None:
        return str(value)
    return os.environ.get(key, default)


def _clone_source(dest: str) -> str:
    """Clone the backend repo (depth 1) and return the path of its db."""
    repo = _env("SYNC_SOURCE_REPO", DEFAULT_SOURCE_REPO)
    timeout = float(_env("SYNC_CLONE_TIMEOUT_S", "120"))
    proc = subprocess.run(
        ["git", "clone", "--depth", "1", repo, dest],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise sync_core.SyncError(f"git clone failed: {proc.stderr.strip()[:400]}")
    db_path = os.path.join(dest, "ember_signal.db")
    if not os.path.isfile(db_path):
        raise sync_core.SyncError("cloned repo does not contain ember_signal.db")
    return db_path


def _purge_edge_cache() -> dict:
    """Ask the B1 worker to drop its cached payload (best-effort, signed)."""
    purge_url = _env("SYNC_PURGE_URL")
    purge_key = _env("SYNC_PURGE_KEY")
    if not purge_url or not purge_key:
        return {"attempted": False, "reason": "not_configured"}
    try:
        import base64

        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key_bytes = base64.b64decode(purge_key)
        private_key = Ed25519PrivateKey.from_private_bytes(key_bytes)
        # sign with b5-trust-bridge/trust.py so the canonical format matches
        try:
            from ember_signal.trust import sign_request_headers  # type: ignore
        except ImportError:
            from trust import sign_request_headers  # type: ignore
        headers = sign_request_headers(private_key, "sync-bot", "POST", "/api/signals/purge", b"")
        import urllib.request

        req = urllib.request.Request(purge_url, data=b"", method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as res:
            body = json.loads(res.read().decode("utf-8"))
        return {"attempted": True, "result": body}
    except Exception as exc:  # best-effort: purge failure must not fail the sync
        return {"attempted": True, "error": str(exc)[:200]}


def build_sync_blueprint() -> Blueprint:
    bp = Blueprint("luma_sync", __name__)

    @bp.post("/api/sync/run")
    def run_sync():
        # ---- B5: verify the Ed25519 request signature -----------------------
        keys_json = _env("LUMA_TRUST_PUBLIC_KEYS")
        if not keys_json:
            # Trust bridge not configured: refuse rather than run unsigned.
            return (
                jsonify({"status": "error", "error": "trust_not_configured",
                         "detail": "set LUMA_TRUST_PUBLIC_KEYS to enable signed sync"}),
                503,
            )
        try:
            public_keys = load_public_keys(keys_json)
        except (json.JSONDecodeError, ValueError, TypeError):
            return jsonify({"status": "error", "error": "trust_misconfigured"}), 500
        try:
            verify_signed_request(request, public_keys)
        except TrustError as exc:
            return jsonify({"status": "error", "error": exc.kind, "detail": str(exc)}), 401

        # ---- B4: clone + transform + atomic swap ----------------------------
        target_dir = Path(current_app.root_path)
        tmp = tempfile.mkdtemp(prefix="luma-sync-")
        try:
            try:
                source_db = _clone_source(tmp)
                report = sync_core.sync(source_db, str(target_dir))
            except sync_core.SyncBusyError:
                return jsonify({"status": "busy", "error": "sync_already_running"}), 409
            except sync_core.SyncError as exc:
                return jsonify({"status": "error", "error": "sync_failed", "detail": str(exc)}), 502
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        # ---- B1: fresh data should be visible immediately --------------------
        report["edgePurge"] = _purge_edge_cache()
        return jsonify({"status": "ok", "sync": report}), 200

    @bp.get("/api/sync/status")
    def sync_status():
        state_path = Path(current_app.root_path) / sync_core.STATE_FILE
        if not state_path.exists():
            return jsonify({"status": "never_synced"}), 200
        try:
            report = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return jsonify({"status": "error", "error": "state_unreadable", "detail": str(exc)}), 500
        return jsonify({"status": "ok", "sync": report}), 200

    return bp
