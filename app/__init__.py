"""Flask 应用工厂。"""
from __future__ import annotations

import os

from flask import Flask, jsonify, render_template, request

from .analyzer import HeaderParseError, analyze


def create_app() -> Flask:
    app = Flask(__name__)
    max_chars = int(os.environ.get("MAX_HEADER_CHARS", "262144"))
    app.config["MAX_HEADER_CHARS"] = max_chars

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/")
    def analyze_view():
        raw_text = request.form.get("headers", "")
        try:
            result = analyze(raw_text, max_chars=app.config["MAX_HEADER_CHARS"])
        except HeaderParseError as exc:
            return render_template("index.html", error=str(exc), raw_text=raw_text), 400
        return render_template("index.html", result=result, raw_text=raw_text)

    @app.post("/api/analyze")
    def analyze_api():
        if request.is_json:
            raw_text = request.get_json(silent=True) or {}
            raw_text = raw_text.get("headers", "")
        else:
            raw_text = request.form.get("headers", "")
        try:
            result = analyze(raw_text, max_chars=app.config["MAX_HEADER_CHARS"])
        except HeaderParseError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "result": result})

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    return app
