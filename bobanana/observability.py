"""可观测性基础设施 — trace 上下文 / TraceMiddleware / 内存指标 / 日志脱敏。

Phase 2 契约 §5 实现。仅依赖 stdlib 与 config、starlette,不 import app/路由,
避免循环依赖。TraceMiddleware 与 metrics 路由由主控在 app.py 接线。
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from bobanana.config import TRACE_HEADER_NAME

logger = logging.getLogger(__name__)

# ── trace 上下文 ─────────────────────────────────────────────
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="none")

_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def new_trace_id() -> str:
    """生成 12 位十六进制 trace_id。"""
    return uuid.uuid4().hex[:12]


def get_trace_id() -> str:
    """返回当前上下文的 trace_id;无上下文返回 "none"。"""
    return _trace_id_var.get()


def _valid_trace_id(value) -> bool:
    """trace_id 合法性: 非空字符串, 仅字母数字短横线, 长度 ≤64。"""
    return isinstance(value, str) and bool(_TRACE_ID_RE.match(value))


# ── 指标 ─────────────────────────────────────────────────────

# counter 类指标(无标签)
_COUNTER_METRICS = (
    "requests_total",
    "llm_calls_total",
    "llm_errors_total",
    "quiz_graded_total",
)
# histogram 类指标(求和 + 计数, snapshot 附均值)
_HISTOGRAM_METRICS = ("llm_call_seconds", "search_seconds")
# labeled 类指标: 指标名 -> 预置标签(保证 snapshot 字段齐全)
_LABELED_METRICS = {
    "import_tasks_total": ("done", "failed", "cancelled"),
    "approvals_total": ("approved", "denied"),
}


def _normalize_labels(labels) -> str | None:
    """将 labels 归一化为稳定的字符串标签键。

    - None → None(无标签)
    - str  → 原样
    - dict → 取各值(布尔 True 取键名, 布尔 False 跳过), 逗号连接
    """
    if labels is None:
        return None
    if isinstance(labels, str):
        return labels
    if isinstance(labels, dict):
        parts: list[str] = []
        for k, v in sorted(labels.items(), key=lambda kv: str(kv[0])):
            if v is True:
                parts.append(str(k))
            elif v is False:
                continue
            else:
                parts.append(str(v))
        return ",".join(parts) if parts else str(labels)
    return str(labels)


class MetricsRegistry:
    """线程安全的内存累积指标(进程内,不持久化)。

    - counter: ``inc(name)`` 累加计数;
    - labeled counter: ``inc(name, labels={"status": "done"})`` 按标签分桶;
    - histogram: ``observe(name, seconds)`` 记录求和 + 计数。
    ``snapshot()`` 返回 uptime_seconds 与各指标值/均值。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._start_monotonic = time.monotonic()
        self._counters: dict[str, int] = {}
        self._labeled: dict[str, dict[str, int]] = {}
        self._histograms: dict[str, tuple[float, int]] = {}  # name -> (sum, count)

    def inc(self, name: str, labels=None) -> None:
        """累加计数。labels 非空时按标签分桶。"""
        key = _normalize_labels(labels)
        with self._lock:
            if key is None:
                self._counters[name] = self._counters.get(name, 0) + 1
            else:
                bucket = self._labeled.setdefault(name, {})
                bucket[key] = bucket.get(key, 0) + 1

    def observe(self, name: str, seconds: float, labels=None) -> None:
        """记录一次观测值(求和 + 计数)。labels 参数保留, 当前不用于分桶。"""
        with self._lock:
            s, c = self._histograms.get(name, (0.0, 0))
            self._histograms[name] = (s + float(seconds), c + 1)

    def snapshot(self) -> dict:
        """返回内存指标快照(含 uptime_seconds 与各指标值/均值)。"""
        with self._lock:
            out: dict = {
                "uptime_seconds": round(time.monotonic() - self._start_monotonic, 3),
            }
            for n in _COUNTER_METRICS:
                out[n] = self._counters.get(n, 0)
            for n, default_labels in _LABELED_METRICS.items():
                bucket = dict(self._labeled.get(n, {}))
                for label in default_labels:
                    bucket.setdefault(label, 0)
                out[n] = bucket
            for n in _HISTOGRAM_METRICS:
                s, c = self._histograms.get(n, (0.0, 0))
                out[n] = {
                    "sum": round(s, 6),
                    "count": c,
                    "avg": round(s / c, 6) if c else None,
                }
            return out


# 进程级单例
metrics = MetricsRegistry()


# ── 日志脱敏 ─────────────────────────────────────────────────

class KeyRedactFilter(logging.Filter):
    """日志脱敏过滤器 — 替换 API Key 与 Bearer token。

    - ``sk-[A-Za-z0-9]{16,}`` → ``sk-***``
    - ``Bearer `` 后 ≥20 个非空白字符 → ``Bearer ***``
    脱敏作用于 record.msg 与 record.args(避免格式化后泄漏)。
    """

    _SK_RE = re.compile(r"sk-[A-Za-z0-9]{16,}")
    _BEARER_RE = re.compile(r"(Bearer\s+)\S{20,}")

    def _redact(self, text):
        if not isinstance(text, str):
            return text
        text = self._SK_RE.sub("sk-***", text)
        text = self._BEARER_RE.sub(r"\1***", text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = self._redact(record.msg)
            args = getattr(record, "args", None)
            if isinstance(args, (tuple, list)):
                record.args = tuple(self._redact(a) for a in args)
            elif isinstance(args, dict):
                record.args = {k: self._redact(v) for k, v in args.items()}
            exc_text = getattr(record, "exc_text", None)
            if exc_text:
                record.exc_text = self._redact(exc_text)
        except Exception:  # noqa: BLE001
            pass
        return True


# ── TraceMiddleware ──────────────────────────────────────────

def _record_request(request: Request, response) -> None:
    """请求完成后的埋点与访问日志;任何异常仅记 debug 日志,不影响请求。"""
    try:
        metrics.inc("requests_total")
    except Exception as e:  # noqa: BLE001
        logger.debug("requests_total 埋点失败: %s", e)
    try:
        logger.info("%s %s -> %d", request.method, request.url.path, response.status_code)
    except Exception:  # noqa: BLE001
        pass


class TraceMiddleware(BaseHTTPMiddleware):
    """HTTP 请求 trace 中间件。

    - 请求头存在合法 trace_id(字母数字短横线, ≤64)则沿用, 否则生成;
    - 写入 contextvar, 供日志/后台任务读取;
    - 响应头回传 trace_id;
    - 完成后累加 requests_total 并记录一条访问日志(由 log_handler 的 JSON
      格式负责序列化, trace_id 取自 contextvar)。
    与 CORS/auth 中间件的叠加顺序由主控接线时决定,本类自洽、可单测。
    """

    def __init__(self, app, header_name: str | None = None):
        super().__init__(app)
        self.header_name = header_name or TRACE_HEADER_NAME

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(self.header_name)
        trace_id = incoming if _valid_trace_id(incoming) else new_trace_id()

        token = _trace_id_var.set(trace_id)
        try:
            response = await call_next(request)
            response.headers[self.header_name] = trace_id
            _record_request(request, response)
            return response
        finally:
            _trace_id_var.reset(token)
