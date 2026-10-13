# Collaboration: the engine operator and this surface

Two agents work this ecosystem in parallel, on the same `/workspace/project`
filesystem:

- **Engine operator** — owns **ember-lite** (`/workspace/project/ember-lite`).
  Runs the "Ember-Lite Level-Up" plan (workflows, integrations, positioning).
  Its crypto work (evidence chain, Merkle, release gate) is the source of truth
  for anything the engine routes return.
- **Surface operator (this repo)** — owns **ember-signal**. Builds and maintains
  the web surface that exposes the engine and the signal data, and keeps the
  lumafoundry.live dashboard contract intact.

## Shared working tree

Since both operators share `/workspace/project`, edits in one are visible to the
other immediately. Re-read the sibling checkout before depending on its
interfaces.

## Contract we share

`ember_signal/engine.py` shells out to ember-lite and consumes these symbols.
They are defined by the engine operator; do not reimplement them here.

| Engine symbol | Module | Used by |
|---|---|---|
| `get_chain_summary()`, `verify_chain()` | `perception.evidence_chain` | `/api/evidence/chain`, `/api/verify` |
| `perceive(save=False)`, `perceive_summary()` | `perception.layer` | `/api/perceive` |
| `evaluate_release()`, `format_gate_report()` | `perception.release_gate` | `/api/gate` |
| `get_governance_summary()` | `perception.governance` | `/api/govern` |

`cryptography` is a transitive dependency of the signing path
(`release_gate` -> `bridge_signatures`); it is pinned in this repo's engine CI
job so the integration does not depend on ember-lite's requirements list.

## Division of change

- Engine semantics (what "cleared", "verified", or a gate decision means) belong
  to ember-lite. This repo only transports and shapes them.
- The `/api/signals` shape belongs to this repo, because the lumafoundry.live
  bridge validates it. See [INTEGRATION.md](INTEGRATION.md) for the exact zod
  contract and the test that pins it.
- Neither operator pushes to the other's repository. Each pushes to its own.

## Honesty rule (both repos)

Unknown is never a default. The engine reports `UNKNOWN` for missing release-gate
dimensions; this repo returns `503` for an absent engine rather than a fabricated
payload. If a change would make either side invent data, it is the wrong change.
