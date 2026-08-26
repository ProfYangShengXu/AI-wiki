"""Quiz 卡片存储 — SQLite 持久化。

Quiz 卡片 = 用户/Agent 生成的测验, 作为 Quiz 页的永久条目保存:
- 题目 + 参考答案 + 用户答案 + 评分(提交后)
- 是否提交(submitted) / 用户编辑状态(user_edited) / 生命周期 status
- 创建/更新时间
- 关联的知识卡片 id 列表(card_ids)

并发安全: 与 memory.py 相同的模式, 模块级 threading.Lock 串行写。
"""

import json
import logging
import sqlite3
import threading
import uuid
from datetime import UTC, datetime

from bobanana.config import DATA_DIR

logger = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "data" / "quiz_cards.db"
_LOCK = threading.Lock()

# 生命周期: draft(未提交) → submitted(已提交待评/已答) → graded(已评分)
STATUS_DRAFT = "draft"
STATUS_SUBMITTED = "submitted"
STATUS_GRADED = "graded"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)


def init_db() -> None:
    """初始化表结构(幂等)。"""
    try:
        conn = _connect()
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quiz_cards (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    card_ids TEXT NOT NULL DEFAULT '[]',
                    questions TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'draft',
                    submitted INTEGER NOT NULL DEFAULT 0,
                    user_edited INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT 'agent',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_quiz_cards_created ON quiz_cards(created_at)"
            )
        conn.close()
    except Exception as e:  # noqa: BLE001
        logger.error("quiz_cards 初始化失败: %s", e)


def _row_to_dict(row: sqlite3.Row) -> dict:
    def _loads(raw: str, default):
        try:
            return json.loads(raw) if raw else default
        except Exception:
            return default

    return {
        "id": row["id"],
        "title": row["title"],
        "card_ids": _loads(row["card_ids"], []),
        "questions": _loads(row["questions"], []),
        "status": row["status"],
        "submitted": bool(row["submitted"]),
        "user_edited": bool(row["user_edited"]),
        "source": row["source"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_quiz_card(
    *,
    title: str,
    card_ids: list[str],
    questions: list,
    source: str = "agent",
    status: str = STATUS_DRAFT,
) -> dict:
    """新建 quiz 卡片, 返回完整记录。"""
    now = _now_iso()
    quiz_id = uuid.uuid4().hex
    with _LOCK:
        conn = _connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO quiz_cards
                        (id, title, card_ids, questions, status, submitted,
                         user_edited, source, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        quiz_id,
                        title,
                        json.dumps(card_ids, ensure_ascii=False),
                        json.dumps(questions, ensure_ascii=False),
                        status,
                        1 if status != STATUS_DRAFT else 0,
                        0,
                        source,
                        now,
                        now,
                    ),
                )
        finally:
            conn.close()
    return {
        "id": quiz_id,
        "title": title,
        "card_ids": card_ids,
        "questions": questions,
        "status": status,
        "submitted": status != STATUS_DRAFT,
        "user_edited": False,
        "source": source,
        "created_at": now,
        "updated_at": now,
    }


def get_quiz_card(quiz_id: str) -> dict | None:
    with _LOCK:
        conn = _connect()
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM quiz_cards WHERE id = ?", (quiz_id,)
            )
            row = cur.fetchone()
            return _row_to_dict(row) if row else None
        finally:
            conn.close()


def list_quiz_cards(card_id: str | None = None, limit: int = 200) -> list[dict]:
    """列出 quiz 卡片; card_id 非空时仅返回关联该卡的条目。"""
    with _LOCK:
        conn = _connect()
        try:
            conn.row_factory = sqlite3.Row
            if card_id:
                cur = conn.execute(
                    "SELECT * FROM quiz_cards ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
                rows = cur.fetchall()
                out = []
                for r in rows:
                    d = _row_to_dict(r)
                    if card_id in d["card_ids"]:
                        out.append(d)
                return out
            cur = conn.execute(
                "SELECT * FROM quiz_cards ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            return [_row_to_dict(r) for r in cur.fetchall()]
        finally:
            conn.close()


def update_quiz_card(quiz_id: str, **fields) -> dict | None:
    """局部更新; 自动刷新 updated_at。支持字段:
    title / card_ids / questions / status / submitted / user_edited / source。
    返回更新后的记录, 不存在返回 None。
    """
    allowed = {"title", "card_ids", "questions", "status", "submitted",
               "user_edited", "source"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_quiz_card(quiz_id)

    if "card_ids" in updates:
        updates["card_ids"] = json.dumps(updates["card_ids"], ensure_ascii=False)
    if "questions" in updates:
        updates["questions"] = json.dumps(updates["questions"], ensure_ascii=False)
    if "submitted" in updates:
        updates["submitted"] = 1 if updates["submitted"] else 0
    if "user_edited" in updates:
        updates["user_edited"] = 1 if updates["user_edited"] else 0
    updates["updated_at"] = _now_iso()

    cols = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [quiz_id]

    with _LOCK:
        conn = _connect()
        try:
            with conn:
                cur = conn.execute(
                    f"UPDATE quiz_cards SET {cols} WHERE id = ?", values
                )
                if cur.rowcount == 0:
                    return None
        finally:
            conn.close()
    return get_quiz_card(quiz_id)


def delete_quiz_card(quiz_id: str) -> bool:
    with _LOCK:
        conn = _connect()
        try:
            with conn:
                cur = conn.execute("DELETE FROM quiz_cards WHERE id = ?", (quiz_id,))
                return cur.rowcount > 0
        finally:
            conn.close()
