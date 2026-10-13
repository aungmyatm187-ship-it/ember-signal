import os
from flask import Flask, jsonify, send_from_directory
import sqlite3
import json

from ember_signal import build_blueprint, engine_status

# The dashboard lives at the repo root, not in templates/ or static/.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# Engine-backed routes: /api/evidence/chain, /api/perceive, /api/gate,
# /api/govern, /api/verify, /api/engine.
app.register_blueprint(build_blueprint())

# Paths are relative to this file (root of repo)
DB_PATH = os.path.join(BASE_DIR, 'data.db')
EVIDENCE_PATH = os.path.join(BASE_DIR, 'ember-signal-evidence.json')

def get_db_data():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, country, brand_value FROM brands WHERE brand_value IS NOT NULL ORDER BY brand_value DESC LIMIT 10;")
    data = c.fetchall()
    conn.close()
    return data

def get_json_evidence():
    try:
        with open(EVIDENCE_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"error": "evidence_file_missing", "path": EVIDENCE_PATH}
    except json.JSONDecodeError as e:
        return {"error": "evidence_file_invalid_json", "detail": str(e)}

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/api/health')
def health():
    # Probed by ember-lite's BackendObserver at /api/health. "status" stays
    # "healthy" (the service is up) even if the engine is not; the engine field
    # reports that separately rather than hiding it.
    return jsonify({
        "status": "healthy",
        "service": "ember-signal",
        "engine": engine_status(),
    })

@app.after_request
def add_cors_headers(response):
    # Off by default. Set EMBER_CORS_ORIGIN (e.g. https://lumafoundry.live) to
    # let a browser origin read these endpoints.
    origin = os.environ.get("EMBER_CORS_ORIGIN")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    return response


@app.route('/api/signals')
def get_signals():
    db_data = get_db_data()
    json_data = get_json_evidence()
    return jsonify({
        "top_brands": db_data,
        "evidence": json_data
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
