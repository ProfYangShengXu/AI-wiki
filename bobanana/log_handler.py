"""内存日志处理器 — 保存最近 N 条日志供前端查看。"""

import logging
from collections import deque
from datetime import datetime, timezone


class MemoryLogHandler(logging.Handler):
    """环形缓冲区日志处理器，保留最近 maxlen 条日志。"""

    def __init__(self, maxlen: int = 200):
        super().__init__()
        self.buffer: deque[dict] = deque(maxlen=maxlen)
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord):
        try:
            ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="seconds")
            self.buffer.append({
                "time": ts,
                "level": record.levelname,
                "module": record.name,
                "message": self.format(record),
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
