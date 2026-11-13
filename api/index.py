"""Entry point Flask untuk Vercel Serverless Functions (dan dev lokal)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # agar `simulation.engine` bisa di-import (juga oleh joblib.load)

import joblib
from flask import Flask, jsonify, render_template, request

from simulation.engine import BengkelDESEngine

MODEL_PATH = ROOT / "models" / "bengkel_des_model.joblib"

app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static"),
    static_url_path="/static",
)


def load_engine():
    """Muat engine dari .joblib; fallback ke class di simulation/engine.py."""
    if MODEL_PATH.exists():
        try:
            engine = joblib.load(MODEL_PATH)
            if hasattr(engine, "run") and hasattr(engine, "get_defaults"):
                return engine, "joblib"
        except Exception as exc:  # file rusak / versi tidak cocok
            print(f"[WARN] Gagal memuat {MODEL_PATH.name}: {exc}")
    return BengkelDESEngine(), "fallback"


ENGINE, ENGINE_SOURCE = load_engine()


@app.route("/")
def index():
    return render_template("index.html", defaults=ENGINE.get_defaults(), source=ENGINE_SOURCE)


@app.route("/api/defaults")
def defaults():
    return jsonify({"defaults": ENGINE.get_defaults(), "source": ENGINE_SOURCE})


@app.route("/api/simulate", methods=["POST"])
def simulate():
    try:
        result = ENGINE.run(request.get_json(silent=True) or {})
        result["engine_source"] = ENGINE_SOURCE
        return jsonify(result)
    except (ValueError, KeyError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400


if __name__ == "__main__":
    app.run(debug=True, port=5000)
