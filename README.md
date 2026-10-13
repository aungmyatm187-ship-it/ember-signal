# Ember Signal

A lightweight Flask application that displays a "live market pulse" dashboard using data from a SQLite database and a JSON evidence file.

## Overview

Ember Signal loads brand-value information from a SQLite database and combines it with structured evidence records to power a browser-based dashboard. The app exposes a small JSON API and renders a single-page report in the browser.

This repository is a minimal example of:

- serving a web dashboard with Flask
- querying a SQLite database
- exposing a lightweight API
- displaying evidence and ranked brand data in one interface

## Features

- Ranks the top brands by value from the `brands` table in `data.db`
- Loads evidence records from `ember-signal-evidence.json`
- Serves a dashboard at `/`
- Exposes combined data at `/api/signals`
- Runs locally with Flask and can be served with Gunicorn in production

## Project Structure

- `app.py` — Flask app and API routes
- `templates/index.html` — browser dashboard UI
- `data.db` — SQLite database containing brand data
- `ember-signal-evidence.json` — evidence metadata loaded by the app
- `requirements.txt` — Python runtime dependencies
- `requirements-dev.txt` — extra dependencies for running tests
- `tests/test_app.py` — pytest suite for the app and API

## Tech Stack

- Python 3
- Flask 3.1.3
- SQLite
- Gunicorn 23.0.0

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/highfive251677-wq/ember-signal.git
cd ember-signal
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the app

```bash
python app.py
```

The app runs on port `5000` by default and is available at:

```text
http://localhost:5000/
```

## Configuration

The app reads a few environment variables:

- `PORT` — sets the port used by the Flask dev server (default: `5000`)
- `SECRET_KEY` — Flask secret key (default: `dev-secret-change-me`)

Example:

```bash
export PORT=8000
export SECRET_KEY=my-secret-key
python app.py
```

## API

### GET /api/signals

Returns a JSON response containing:

- `top_brands`: the top-ranked brand values from the SQLite database
- `evidence`: the JSON evidence payload loaded from `ember-signal-evidence.json`

Example response:

```json
{
  "top_brands": [
    ["Apple", "USA", 470.9],
    ["Microsoft", "USA", 388.5]
  ],
  "evidence": {
    "updatedAt": "2026-09-05T00:00:00Z",
    "records": [
      {
        "id": "real-record-001",
        "title": "My First Evidence",
        "status": "observed"
      }
    ]
  }
}
```

## Testing

Install the dev dependencies and run pytest from the repository root:

```bash
pip install -r requirements-dev.txt
pytest
```

The suite exercises the real app and the committed `data.db` / evidence file; it uses no mocks.

## Production Deployment

This app is compatible with a standard WSGI server such as Gunicorn:

```bash
gunicorn app:app
```

## Notes

- The dashboard escapes all values before rendering, so database or evidence content is never
  interpreted as HTML.
- If the evidence file is missing or malformed, `/api/signals` still returns `200` with an
  `evidence.error` field rather than failing.
- `data.db` is committed as sample seed data. If you regenerate it, keep the `brands` table
  schema (`id`, `name`, `country`, `brand_value`) intact.

## License

No explicit license file was found in this repository. If you plan to distribute or reuse this project, consider adding an appropriate open-source license.
