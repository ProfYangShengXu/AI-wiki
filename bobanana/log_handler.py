"""内存日志处理器 — 保存最近 N 条日志供前端查看。

Phase 2 契约 §5:
- 保留内存日志 ring buffer API(log_handler 单例 / get_recent), 行为不变;
- 新增 JSON 行格式输出 format_json_record(record, trace_id);
- 给现有 handler 挂 KeyRedactFilter 脱敏;
- config.LOG_JSON 为 true(默认)时用 JSON 行, 否则保持现有文本格式。
"""

import json
import logging
from collections import deque
from datetime import UTC, datetime

from bobanana.config import LOG_JSON
from bobanana.observability import KeyRedactFilter, get_trace_id


def format_json_record(record: logging.LogRecord, trace_id: str) -> str:
    """将 LogRecord 格式化为单行 JSON(字段 trace_id/level/time/logger/message)。"""
    ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="seconds")
    try:
        message = record.getMessage()
    except Exception:  # noqa: BLE001
        message = str(getattr(record, "msg", ""))
    payload = {
        "trace_id": trace_id,
        "level": record.levelname,
        "time": ts,
        "logger": record.name,
        "message": message,
    }
    return json.dumps(payload, ensure_ascii=False)


class MemoryLogHandler(logging.Handler):
    """环形缓冲区日志处理器，保留最近 maxlen 条日志。"""

    def __init__(self, maxlen: int = 200):
        super().__init__()
        self.buffer: deque[dict] = deque(maxlen=maxlen)
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        self.addFilter(KeyRedactFilter())

    def emit(self, record: logging.LogRecord):
        try:
            ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="seconds")
            if LOG_JSON:
                message = format_json_record(record, get_trace_id())
            else:
                message = self.format(record)
            self.buffer.append({
                "time": ts,
                "level": record.levelname,
                "module": record.name,
                "message": message,
            })
        except Exception:
            pass

    def get_recent(self, n: int = 100, level: str | None = None) -> list[dict]:
        """获取最近的 n 条日志，可选按级别过滤。"""
        entries = list(self.buffer)
        if level:
            entries = [e for e in entries if e["level"] == level.upper()]
        return entries[-n:]


# 全局单例
log_handler = MemoryLogHandler(maxlen=200)
