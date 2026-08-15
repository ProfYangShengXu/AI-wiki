"""可观测性单元测试 — trace 上下文 / TraceMiddleware / 日志脱敏 / 指标 / metrics 路由。

全部测试不依赖真实 LLM/网络;TraceMiddleware 与 /api/metrics 通过最小 FastAPI
app 验证, 不改 bobanana.app 本身。
"""

import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bobanana.observability import (
    KeyRedactFilter,
    MetricsRegistry,
    TraceMiddleware,
    _trace_id_var,
    get_trace_id,
    metrics,
    new_trace_id,
)


def _make_app(header_name: str | None = None):
    app = FastAPI()
    app.add_middleware(TraceMiddleware, header_name=header_name)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.get("/tid")
    def tid():
        return {"trace_id": get_trace_id()}

    return app


# ── trace 上下文 ─────────────────────────────────────────────

class TestTraceContext:
    def test_get_trace_id_defaults_to_none(self):
        token = _trace_id_var.set("none")
        try:
            assert get_trace_id() == "none"
        finally:
            _trace_id_var.reset(token)

    def test_get_trace_id_propagates_value(self):
        tid = "abc123def456"
        token = _trace_id_var.set(tid)
        try:
            assert get_trace_id() == tid
        finally:
            _trace_id_var.reset(token)

    def test_new_trace_id_is_12_hex(self):
        tid = new_trace_id()
        assert isinstance(tid, str)
        assert len(tid) == 12
        assert all(c in "0123456789abcdef" for c in tid)


# ── TraceMiddleware ──────────────────────────────────────────

class TestTraceMiddleware:
    def test_generates_and_echoes_trace_id(self):
        client = TestClient(_make_app())
        resp = client.get("/ping")
        assert resp.status_code == 200
        tid = resp.headers.get("X-Trace-Id")
        assert tid
        assert len(tid) == 12
        assert all(c in "0123456789abcdef" for c in tid)

    def test_reuses_valid_incoming_header(self):
        client = TestClient(_make_app())
        resp = client.get("/ping", headers={"X-Trace-Id": "my-trace-123"})
        assert resp.headers["X-Trace-Id"] == "my-trace-123"

    def test_rejects_invalid_incoming_header(self):
        client = TestClient(_make_app())
        resp = client.get("/ping", headers={"X-Trace-Id": "bad!value"})
        tid = resp.headers["X-Trace-Id"]
        assert tid != "bad!value"
        assert len(tid) == 12

    def test_context_propagates_into_handler(self):
        client = TestClient(_make_app())
        resp = client.get("/tid", headers={"X-Trace-Id": "abc-123"})
        assert resp.json()["trace_id"] == "abc-123"
        assert resp.headers["X-Trace-Id"] == "abc-123"

    def test_custom_header_name(self):
        client = TestClient(_make_app(header_name="X-Request-Id"))
        resp = client.get("/ping", headers={"X-Request-Id": "req-42"})
        assert resp.headers["X-Request-Id"] == "req-42"
        assert "X-Trace-Id" not in resp.headers

    def test_increments_requests_total(self):
        before = metrics.snapshot()["requests_total"]
        client = TestClient(_make_app())
        client.get("/ping")
        after = metrics.snapshot()["requests_total"]
        assert after == before + 1


# ── KeyRedactFilter ──────────────────────────────────────────

class TestKeyRedactFilter:
    def _record(self, msg):
        return logging.LogRecord("test", logging.INFO, __file__, 1, msg, None, None)

    def test_redacts_sk_key(self):
        f = KeyRedactFilter()
        secret = "sk-dummy1234567890abcdef123456"
        rec = self._record(f"api key: {secret}")
        f.filter(rec)
        assert secret not in rec.getMessage()
        assert "sk-***" in rec.getMessage()

    def test_redacts_bearer_token(self):
        f = KeyRedactFilter()
        token = "eyJhbGciOiJIUzI1NiJ9.abcdefghijklmnopqrstuvwxyz012345"
        rec = self._record(f"Authorization: Bearer {token}")
        f.filter(rec)
        assert token not in rec.getMessage()
        assert "Bearer ***" in rec.getMessage()

    def test_redacts_args_too(self):
        f = KeyRedactFilter()
        secret = "sk-dummy1234567890abcdef123456"
        rec = logging.LogRecord("test", logging.INFO, __file__, 1, "key=%s", (secret,), None)
        f.filter(rec)
        assert secret not in rec.getMessage()

    def test_leaves_normal_message_untouched(self):
        f = KeyRedactFilter()
        rec = self._record("普通日志消息")
        f.filter(rec)
        assert rec.getMessage() == "普通日志消息"


# ── MetricsRegistry ──────────────────────────────────────────

class TestMetricsRegistry:
    def test_inc_observe_snapshot(self):
        m = MetricsRegistry()
        m.inc("requests_total")
        m.inc("requests_total")
        m.inc("llm_calls_total")
        m.inc("llm_errors_total")
        m.observe("llm_call_seconds", 0.5)
        m.observe("llm_call_seconds", 1.5)
        m.inc("import_tasks_total", labels={"status": "done"})

        snap = m.snapshot()
        assert snap["uptime_seconds"] >= 0
        assert snap["requests_total"] == 2
        assert snap["llm_calls_total"] == 1
        assert snap["llm_errors_total"] == 1
        assert snap["llm_call_seconds"]["count"] == 2
        assert snap["llm_call_seconds"]["sum"] == 2.0
        assert snap["llm_call_seconds"]["avg"] == 1.0
        assert snap["import_tasks_total"]["done"] == 1
        assert snap["import_tasks_total"]["failed"] == 0
        assert snap["import_tasks_total"]["cancelled"] == 0

    def test_snapshot_has_all_fields(self):
        snap = MetricsRegistry().snapshot()
        for field in (
            "uptime_seconds",
            "requests_total",
            "llm_calls_total",
            "llm_call_seconds",
            "llm_errors_total",
            "import_tasks_total",
            "quiz_graded_total",
            "search_seconds",
            "approvals_total",
        ):
            assert field in snap, field

    def test_histogram_avg_none_when_empty(self):
        snap = MetricsRegistry().snapshot()
        assert snap["search_seconds"]["count"] == 0
        assert snap["search_seconds"]["avg"] is None

    def test_approvals_labeling(self):
        m = MetricsRegistry()
        m.inc("approvals_total", labels={"approved": True})
        m.inc("approvals_total", labels={"approved": True})
        m.inc("approvals_total", labels={"denied": True})
        snap = m.snapshot()
        assert snap["approvals_total"]["approved"] == 2
        assert snap["approvals_total"]["denied"] == 1


# ── GET /api/metrics ─────────────────────────────────────────

class TestMetricsEndpoint:
    def _make_metrics_app(self):
        from bobanana.routes.metrics import router

        app = FastAPI()
        app.add_middleware(TraceMiddleware)
        app.include_router(router)
        return app

    def test_metrics_returns_200_with_uptime(self):
        client = TestClient(self._make_metrics_app())
        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert "uptime_seconds" in body["data"]
        assert body["data"]["uptime_seconds"] >= 0
        assert "requests_total" in body["data"]

    def test_metrics_disabled(self, monkeypatch):
        import bobanana.config as config

        monkeypatch.setattr(config, "METRICS_ENABLED", False)
        client = TestClient(self._make_metrics_app())
        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["data"] == {"enabled": False}


# ── 日志 JSON 行格式 ─────────────────────────────────────────

class TestLogHandlerJson:
    def test_format_json_record_fields(self):
        from bobanana.log_handler import format_json_record

        rec = logging.LogRecord("my.logger", logging.WARNING, __file__, 7, "hello %s", ("world",), None)
        line = format_json_record(rec, "trace-1")
        obj = json.loads(line)
        assert obj["trace_id"] == "trace-1"
        assert obj["level"] == "WARNING"
        assert obj["logger"] == "my.logger"
        assert obj["message"] == "hello world"
        assert "time" in obj
