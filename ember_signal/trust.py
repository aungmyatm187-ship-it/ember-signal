"""B5 Trust Bridge — Ed25519 request/response signatures for service-to-service calls.

WHY Ed25519 AND NOT "JUST AN API KEY"
-------------------------------------
A static bearer key shared between GitHub Actions, Render services and the
Cloudflare edge is a standing credential: any log leak replays it forever,
and rotation means touching every service at once. An Ed25519 signature
scheme gives:

  * PER-REQUEST PROOF — every call is individually signed over
    (timestamp, method, path, body-hash); nothing reusable is ever
    transmitted. Stealing one signature replays nothing (300 s window).
  * KEY-ID ROTATION — LUMA_TRUST_PUBLIC_KEYS is a {key-id: public-key} map,
    so you add "sync-2026-11" while "sync-main" still works, then remove the
    old one. Zero-downtime rotation.
  * ONE CRYPTO SYSTEM ECOSYSTEM-WIDE — ember-lite already signs evidence with
    Ed25519; packages/gateway already verifies Ed25519 webhooks. Service
    authentication uses the same primitive (see RESEARCH-DATA-POINTS.md
    DP-17/DP-21: C2PA-style "one trust list, many assertions").

This is the application-layer equivalent of mTLS. When the lumafoundry.live
zone activates on YOUR Cloudflare account, you can additionally switch on
true mTLS via API Shield (see MTLS-OPTIONS.md) — the code below keeps working
either way.

Canonical formats (byte-identical on every side)
------------------------------------------------
REQUEST  message = f"{timestamp}|{method}|{path}|".encode() + sha256(body).digest()
RESPONSE message = f"response|{timestamp}|{sha256hex(body)}".encode()
   (the worker's purge auth uses the REQUEST form; its upstream payload
    verification uses the RESPONSE form — see b1-edge-bridge/src/worker.ts)

Headers
-------
X-Luma-Timestamp   unix seconds as a string (replay window: +/-300 s)
X-Luma-Key-Id      which key signed (must exist in the public-key map)
X-Luma-Signature   base64 Ed25519 signature over the canonical message

Placement: ember_signal/trust.py in the ember-signal repo.
Dependencies: cryptography>=42 (add to requirements.txt).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from functools import wraps

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "B5 trust bridge needs the 'cryptography' package: "
        "pip install 'cryptography>=42' (and add it to requirements.txt)"
    ) from exc

DEFAULT_MAX_AGE_SECONDS = 300


class TrustError(Exception):
    """Raised when a request fails trust verification.

    `kind` is a stable machine-readable code the JSON error responses use:
      missing_headers | stale_timestamp | unknown_key | bad_signature
    """

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(detail or kind)
        self.kind = kind
        self.detail = detail or kind


# ---------------------------------------------------------------------------
# Canonical messages (keep byte-compatible with b1-edge-bridge worker.ts and
# b5-trust-bridge/trust.ts — the whole system only works if these match)
# ---------------------------------------------------------------------------


def canonical_message(timestamp: str, method: str, path: str, body: bytes) -> bytes:
    return f"{timestamp}|{method}|{path}|".encode("ascii") + hashlib.sha256(body).digest()


def response_canonical_message(timestamp: str, body: bytes) -> bytes:
    return f"response|{timestamp}|{hashlib.sha256(body).hexdigest()}".encode("ascii")


# ---------------------------------------------------------------------------
# Key handling
# ---------------------------------------------------------------------------


def load_public_keys(raw: str | dict) -> dict[str, Ed25519PublicKey]:
    """Parse LUMA_TRUST_PUBLIC_KEYS (JSON {"key-id": "base64"}) into key objects."""
    mapping = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("public key map must be a non-empty JSON object {key-id: base64}")
    keys: dict[str, Ed25519PublicKey] = {}
    for key_id, b64 in mapping.items():
        keys[str(key_id)] = Ed25519PublicKey.from_public_bytes(base64.b64decode(b64))
    return keys


def load_private_key(b64: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(b64))


# ---------------------------------------------------------------------------
# Verification (server side — Flask)
# ---------------------------------------------------------------------------


def verify_signed_request(request, public_keys: dict[str, Ed25519PublicKey], max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS) -> str:
    """Verify a Flask request's Ed25519 signature. Returns the key-id.

    Raises TrustError with a stable `kind` on any failure. The caller maps
    that to HTTP 401.
    """
    timestamp = request.headers.get("X-Luma-Timestamp", "")
    key_id = request.headers.get("X-Luma-Key-Id", "")
    signature = request.headers.get("X-Luma-Signature", "")

    if not timestamp or not key_id or not signature:
        raise TrustError("missing_headers", "X-Luma-Timestamp, X-Luma-Key-Id and X-Luma-Signature are all required")

    try:
        ts_value = float(timestamp)
    except ValueError:
        raise TrustError("stale_timestamp", "timestamp is not numeric") from None
    if abs(time.time() - ts_value) > max_age_seconds:
        raise TrustError("stale_timestamp", f"timestamp outside +/-{max_age_seconds}s replay window")

    if key_id not in public_keys:
        raise TrustError("unknown_key", f"key-id '{key_id}' is not in the trust list")

    body = request.get_data(cache=True) or b""
    message = canonical_message(timestamp, request.method, request.path, body)
    try:
        sig_bytes = base64.b64decode(signature, validate=True)
    except (ValueError, TypeError):
        raise TrustError("bad_signature", "signature is not valid base64") from None

    try:
        public_keys[key_id].verify(sig_bytes, message)
    except InvalidSignature:
        raise TrustError("bad_signature", "Ed25519 verification failed") from None

    return key_id


def require_trust(public_keys: dict[str, Ed25519PublicKey] | str, max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS):
    """Decorator protecting a Flask view with Ed25519 request verification.

    Usage:
        KEYS = load_public_keys(os.environ["LUMA_TRUST_PUBLIC_KEYS"])

        @bp.post("/api/internal/thing")
        @require_trust(KEYS)
        def internal_thing():
            ...
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            from flask import jsonify, request

            keys = load_public_keys(public_keys) if isinstance(public_keys, str) else public_keys
            try:
                verify_signed_request(request, keys, max_age_seconds)
            except TrustError as exc:
                return jsonify({"status": "error", "error": exc.kind, "detail": str(exc)}), 401
            return view(*args, **kwargs)

        return wrapped

    return decorator


# ---------------------------------------------------------------------------
# Signing (client side — used by sync_service for the B1 purge call, and by
# the GitHub Actions workflow / any TS caller via trust.ts)
# ---------------------------------------------------------------------------


def sign_request_headers(private_key: Ed25519PrivateKey, key_id: str, method: str, path: str, body: bytes, timestamp: str | None = None) -> dict[str, str]:
    ts = timestamp or str(int(time.time()))
    message = canonical_message(ts, method.upper(), path, body)
    signature = base64.b64encode(private_key.sign(message)).decode("ascii")
    return {
        "X-Luma-Timestamp": ts,
        "X-Luma-Key-Id": key_id,
        "X-Luma-Signature": signature,
    }


def sign_response_body(body: bytes, private_key: Ed25519PrivateKey, timestamp: str | None = None) -> dict[str, str]:
    """Headers the ember-signal Flask app attaches to /api/signals responses so
    the B1 edge worker can verify payload integrity (response form)."""
    ts = timestamp or str(int(time.time()))
    message = response_canonical_message(ts, body)
    signature = base64.b64encode(private_key.sign(message)).decode("ascii")
    return {
        "X-Luma-Timestamp": ts,
        "X-Luma-Signature": signature,
    }


def after_request_response_signing(app, path: str = "/api/signals", private_key_env: str = "LUMA_RESPONSE_SIGNING_KEY"):
    """Attach response signing to a Flask app for one path.

    Usage in app.py (optional premium upgrade for B1 verification):

        from ember_signal.trust import after_request_response_signing
        after_request_response_signing(app)

    When LUMA_RESPONSE_SIGNING_KEY (base64 private key) is unset this is a
    no-op — the B1 worker treats unsigned responses as 'skipped' unless
    REQUIRE_SIGNATURE=true.
    """
    b64 = os.environ.get(private_key_env)
    if not b64:
        return
    private_key = load_private_key(b64)

    @app.after_request
    def _sign(response):
        if request_path_matches(response) and response.status_code == 200 and response.is_json:
            body = response.get_data()
            response.headers.update(sign_response_body(body, private_key))
        return response

    def request_path_matches(response):  # closes over nothing; reads the request context
        from flask import request

        return request.path == path

    return app
