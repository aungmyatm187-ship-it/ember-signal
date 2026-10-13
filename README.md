# Ember Signal

Web surface for the Ember governance layer. **Signals to Evidence.**

A small Flask app that serves a live market-pulse dashboard, exposes the signal
data as JSON, and — when an [ember-lite](https://github.com/aungmyatm187-ship-it/ember-lite)
checkout is configured — surfaces the engine over read-only HTTP routes.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /` | Dashboard (`index.html`) |
| `GET /api/signals` | `{ top_brands, evidence }` — brands from `data.db` + the evidence JSON |
| `GET /api/health` | Liveness probe (`status`, `service`, `engine`) |
| `GET /api/evidence/chain` | ember-lite signed chain summary + verification |
| `GET /api/perceive` | Fresh perception pass |
| `GET /api/gate` | P5 release gate (unknown dimensions stay `UNKNOWN`) |
| `GET /api/govern` | P6 governance summary |
| `GET /api/verify` | Whole-chain integrity check |
| `GET /api/engine` | Is the engine configured and reachable |

The engine routes return `503` when no engine is present — they never fabricate a
payload. See [docs/INTEGRATION.md](docs/INTEGRATION.md).

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py            # http://localhost:5000
```

Production (the Render start command):

```bash
gunicorn --bind 0.0.0.0:$PORT app:app
```

`GET /api/health` is the Render `healthCheckPath`.

## Test

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

With an ember-lite checkout present the engine routes are exercised against a
real subprocess; without one those tests skip and the engine routes return 503.

```bash
EMBER_LITE_DIR=/path/to/ember-lite python -m pytest -q
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `5000` | Dev-server port |
| `SECRET_KEY` | `dev-secret-change-me` | Flask secret key |
| `EMBER_CORS_ORIGIN` | unset | If set, allows that browser origin to read the API |
| `EMBER_LITE_DIR` | `/opt/ember-lite` | Path to an ember-lite checkout |
| `EMBER_LITE_PYTHON` | current interpreter | Interpreter with ember-lite's deps |
| `EMBER_ENGINE_TIMEOUT` | `30` | Seconds before an engine call is abandoned |

## Project layout

```
app.py                        Flask app: /, /api/signals, /api/health
index.html                    dashboard (served from the repo root)
ember_signal/                 optional HTTP surface over the ember-lite engine
data.db                       SQLite seed data (brands table)
ember-signal-evidence.json    evidence records
tests/                        pytest suite (no mocks)
docs/INTEGRATION.md           ember-signal ↔ ember-lite wiring
```

## License

No license file is present in this repository. Add one before distributing or
reusing the project.
