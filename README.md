# Ember Signal

Web surface for the Ember governance layer. Signals to Evidence.

A small Flask app that shows a live market-pulse dashboard and exposes the
[ember-lite](https://github.com/aungmyatm187-ship-it/ember-lite) engine over HTTP.

## Run

```bash
pip install -r requirements.txt
python app.py            # http://localhost:5000
```

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /` | Dashboard (`index.html`) |
| `GET /api/health` | Service + engine health (probed by ember-lite's BackendObserver) |
| `GET /api/signals` | Top brands (SQLite) + evidence JSON |
| `GET /api/evidence/chain` | Signed evidence chain summary + verification |
| `GET /api/perceive` | Fresh perception pass |
| `GET /api/gate` | P5 release-gate evaluation |
| `GET /api/govern` | P6 governance summary |
| `GET /api/verify` | Whole-chain integrity check |
| `GET /api/engine` | Engine configuration status |

Engine routes need `EMBER_LITE_DIR` pointing at an ember-lite checkout. Without
it they return `503 engine_unavailable` rather than fabricated data. See
[docs/INTEGRATION.md](docs/INTEGRATION.md).

## Test

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

## Deploy

`Procfile` runs `gunicorn app:app`. Set `EMBER_LITE_DIR` (and `SECRET_KEY`) in
the environment.
