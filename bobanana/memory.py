"""会话记忆 — SQLite 持久化聊天历史与跨会话上下文 (Phase 2)。

所有操作失败只记日志, 绝不影响主流程。
"""

import json
import logging
import sqlite3
import threading
from datetime import UTC, datetime

from bobanana.config import DATA_DIR

logger = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "data" / "session_memory.db"
_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _connect() -> sqlite3.Connection:
    """建立连接(自动创建目录)。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)


def init_db() -> None:
    """初始化表结构(幂等)。"""
    try:
        conn = _connect()
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT,
                    context_json TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    created_at TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS contexts (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
        conn.close()
    except Exception as e:
        logger.warning("初始化会话记忆失败: %s", e)


def append_message(session_id: str, role: str, content: str) -> None:
    """追加一条消息。"""
    try:
        conn = _connect()
        with conn:
            conn.execute(
                "INSERT INTO messages(session_id, role, content, created_at) VALUES (?,?,?,?)",
                (session_id, role, content, _now_iso()),
            )
        conn.close()
    except Exception as e:
        logger.warning("追加消息失败: %s", e)


def get_history(session_id: str, limit: int = 20) -> list[dict]:
    """按时间正序返回最近 limit 条消息(仅同 session)。"""
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        conn.close()
        return [{"role": r, "content": c} for r, c in reversed(rows)]
    except Exception as e:
        logger.warning("读取历史失败: %s", e)
        return []


def save_context(key: str, value) -> None:
    """保存全局上下文键值(JSON 序列化)。"""
    try:
        conn = _connect()
        with conn:
            conn.execute(
                "INSERT INTO contexts(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(key), json.dumps(value, ensure_ascii=False)),
            )
        conn.close()
    except Exception as e:
        logger.warning("保存上下文失败: %s", e)


def get_context(key: str, default=None):
    """读取全局上下文键值。"""
    try:
        conn = _connect()
        row = conn.execute("SELECT value FROM contexts WHERE key=?", (str(key),)).fetchone()
        conn.close()
        if row is None:
            return default
        return json.loads(row[0])
    except Exception as e:
        logger.warning("读取上下文失败: %s", e)
        return default
