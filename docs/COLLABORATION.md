# Collaboration: this surface and the ember-lite engine operator

Two OpenHands agents work this ecosystem together:

- **Engine operator** — owns **ember-lite**, the engine (perception P1–P6, signed
  evidence chain, release gate, governance). It runs the "Ember-Lite Level-Up"
  plan, whose **#1 integration target is this repo**.
- **Surface operator (this repo)** — owns **ember-signal**, the web surface and
  the lumafoundry.live dashboard contract.

The two sandboxes are **separate** (different runtime hosts). Coordination
happens through GitHub (branches, PRs) and through the OpenHands Cloud API — not
a shared live filesystem. Before depending on an engine interface, check the
engine repo's `master`, not a stale local copy.

## The fusion contract

The engine operator's plan defines three integration points between the two
repos. This repo implements them:

| # | Plan item | This repo |
|---|---|---|
| 1 | Evidence API: `GET /api/evidence/chain` | `ember_signal/routes.py` |
| 2 | Perception as a service: `GET /api/perceive` | `ember_signal/routes.py` |
| 3 | Signed receipts (sign every response) | not yet — see below |

Plus `/api/gate`, `/api/govern`, `/api/verify`, and `/api/evidence/health`
(engine DB/chain/anchor/sensor probe) for completeness.

### Engine symbols consumed

Defined by the engine operator; do not reimplement here.

| Symbol | Module |
|---|---|
| `get_chain_summary()`, `verify_chain()` | `perception.evidence_chain` |
| `perceive(save=False)`, `perceive_summary()` | `perception.layer` |
| `evaluate_release()`, `format_gate_report()` | `perception.release_gate` |
| `get_governance_summary()` | `perception.governance` |
| `health_check()` | `perception.health` |

`cryptography` is a transitive dependency of the signing path
(`release_gate` -> `bridge_signatures`); the engine CI job here pins it so the
integration does not depend on ember-lite's requirements list.

## The bridge workflow

`.github/workflows/bridge-verify.yml` is the fusion gate. On a successful
deployment (or manually) it checks out ember-lite, runs its perception pass and
release gate against the deployed service, and publishes the verdict to the run
summary. It checks the engine out rather than `pip install`ing it, because the
engine is not on PyPI yet.

## Health-probe compatibility

ember-lite's `BackendObserver` probes `{url}/api/health` and treats HTTP `200`
as healthy, `2xx–4xx` as degraded, `5xx` as down. `GET /api/health` in this repo
returns `200` with `{"status": "healthy", ...}`, so the engine reads this service
as healthy. The observer's default URL points at the Railway backend; point it
at this service's URL to observe the web surface instead.

## Division of change

- Engine semantics (what "verified", "cleared", or a gate decision mean) belong
  to ember-lite. This repo transports and shapes them.
- The `/api/signals` shape belongs to this repo, because the lumafoundry.live
  bridge validates it (see [INTEGRATION.md](INTEGRATION.md)).
- Neither operator pushes to the other's repository.

## Honesty rule (both repos)

Unknown is never a default. The engine reports `UNKNOWN` for missing release-gate
dimensions; this repo returns `503` for an absent engine rather than a fabricated
payload. If a change would make either side invent data, it is the wrong change.

## Not done yet

- **Signed receipts** (plan integration point #3): signing every HTTP response
  with `perception.bridge_signatures.sign()`. It needs a key-management decision
  (whose key, rotated how) before it belongs in a public endpoint.
- **Per-block chain lookup** and **RFC 3161 timestamp anchoring** — engine-side
  gaps tracked by the engine operator.
