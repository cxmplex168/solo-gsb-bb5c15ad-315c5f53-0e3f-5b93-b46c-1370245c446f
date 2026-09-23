"""邮件投递路径检查 Flask 应用。"""

from __future__ import annotations

import os

from flask import Flask, jsonify, render_template, request

from mailtrace.parsing import analyze_headers
from mailtrace.parsing.sample import SAMPLE_HEADERS


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def create_app() -> Flask:
    app = Flask(__name__)
    max_input_kb = _env_int("MAX_INPUT_KB", 256)
    app.config["MAX_INPUT_BYTES"] = max_input_kb * 1024
    app.config["SAMPLE_HEADERS"] = SAMPLE_HEADERS

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            sample=SAMPLE_HEADERS,
            max_input_kb=max_input_kb,
        )

    def _do_analyze(raw_headers: str) -> dict:
        max_bytes = app.config["MAX_INPUT_BYTES"]
        if len(raw_headers.encode("utf-8", errors="ignore")) > max_bytes:
            return {
                "error": f"输入超过 {max_input_kb} KB 上限，请截取头部后重试",
                "hop_count": 0,
                "path": [],
            }
        if not raw_headers.strip():
            return {
                "error": "请先粘贴邮件原始头部（包含至少一个 Received 字段）",
                "hop_count": 0,
                "path": [],
            }
        return analyze_headers(raw_headers)

    @app.post("/analyze")
    def analyze_form():
        raw_headers = request.form.get("headers", "")
        result = _do_analyze(raw_headers)
        return render_template(
            "index.html",
            sample=SAMPLE_HEADERS,
            max_input_kb=max_input_kb,
            raw_headers=raw_headers,
            result=result,
        )

    @app.post("/api/analyze")
    def analyze_api():
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            raw_headers = payload.get("headers", "")
        else:
            raw_headers = request.form.get("headers", "")
        if not isinstance(raw_headers, str):
            return jsonify({"error": "headers 必须是字符串"}), 400
        result = _do_analyze(raw_headers)
        status = 400 if result.get("error") else 200
        return jsonify(result), status

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    return app
