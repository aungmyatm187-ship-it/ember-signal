# ember-signal ↔ ember-lite integration

ember-signal is the web surface; ember-lite is the engine. This document covers
how they connect, what is exposed, and what is deliberately left out.

## Why a subprocess

ember-lite has no `pyproject.toml` or `setup.py`, so it cannot be `pip install`ed
or imported as a library. It also owns SQLite databases and Ed25519 keys that
must stay single-writer.

ember-signal therefore calls the engine through one short-lived Python
interpreter per request (`ember_signal/engine.py`). The engine's databases and
keys never leave the engine host, and ember-signal stays stateless.

The alternative the brief suggested — `pip install git+https://github.com/...`
— is not possible until ember-lite is packaged. That is the real prerequisite
for a pip-based integration.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `EMBER_LITE_DIR` | `/opt/ember-lite` | Path to an ember-lite checkout |
| `EMBER_LITE_PYTHON` | current interpreter | Interpreter that has ember-lite's deps |
| `EMBER_ENGINE_TIMEOUT` | `30` | Seconds before a call is abandoned |
| `EMBER_CORS_ORIGIN` | unset | If set, adds `Access-Control-Allow-Origin` |

## Endpoints

| Endpoint | Engine call | Notes |
|---|---|---|
| `GET /api/evidence/chain` | `get_chain_summary()` + `verify_chain()` | Real signed/verified/anchored counts |
| `GET /api/perceive` | `perceive(save=False)` | Reaches the network; may be slow |
| `GET /api/gate` | `evaluate_release()` | Missing dimensions report `UNKNOWN` |
| `GET /api/govern` | `get_governance_summary()` | Policies, capabilities, approval gates |
| `GET /api/verify` | `verify_chain()` | Whole-chain integrity |
| `GET /api/engine` | `engine_status()` | Is the engine configured and reachable |

Plus the original `GET /` (dashboard), `GET /api/signals` (SQLite + evidence
JSON), and `GET /api/health` (service health, now including engine status).

## Honesty contract

Every engine route returns one of three states:

- `200 {"status": "ok", "data": ...}` — engine answered, data is real
- `503 {"status": "unavailable", "error": "engine_unavailable", ...}` — engine not reachable
- `502 {"status": "error", "error": "engine_error", ...}` — engine ran, operation failed

No route invents a payload when the engine is absent. This mirrors ember-lite's
own rule: **unknown is not a default**.

## What is not done yet

- **Per-block chain lookup** (`/api/verify/<index>`) — ember-lite exposes only a
  whole-chain check, not an inclusion proof for one block.
- **RFC 3161 timestamp anchoring** — ember-lite's chain has no anchor yet.
- **Signed HTTP receipts** — every response is not individually signed. The
  evidence chain itself is signed; the transport is not.
- **pip packaging of ember-lite** — the blocker for a library-style import.

These are candidates for Phase C, in that order.

## Running locally

```bash
pip install -r requirements-dev.txt
EMBER_LITE_DIR=/path/to/ember-lite python -m pytest -q
EMBER_LITE_DIR=/path/to/ember-lite python app.py
```

Without `EMBER_LITE_DIR` (and no sibling `../ember-lite`), the engine tests
skip and the engine routes return 503 — both are expected.
