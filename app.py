import os
from flask import Flask, jsonify, send_from_directory
import sqlite3
import json

# The dashboard lives at the repo root, not in templates/ or static/.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

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
    # Probed by ember-lite's BackendObserver at /api/health.
    return jsonify({"status": "healthy", "service": "ember-signal"})

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
