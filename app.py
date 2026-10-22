import os
from flask import Flask, jsonify, render_template
import sqlite3
import json

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# Paths are relative to this file (root of repo)
DB_PATH = os.path.join(os.path.dirname(__file__), 'data.db')
EVIDENCE_PATH = os.path.join(os.path.dirname(__file__), 'ember-signal-evidence.json')

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
    except:
        return {"error": "Evidence file not found"}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/health')
def health():
    return jsonify({"status": "ok"}), 200

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
