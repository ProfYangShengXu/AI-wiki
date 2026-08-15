"""会话记忆 (Phase 2 §1.5) 测试。"""

import pytest

from bobanana import memory


@pytest.fixture
def isolated_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "memory" / "test.db")
    memory.init_db()
    return memory


def test_init_idempotent(isolated_memory):
    isolated_memory.init_db()
    isolated_memory.init_db()


def test_append_and_get_history(isolated_memory):
    sid = "sess-1"
    isolated_memory.append_message(sid, "user", "你好")
    isolated_memory.append_message(sid, "assistant", "你好,有什么可以帮你?")
    hist = isolated_memory.get_history(sid)
    assert len(hist) == 2
    assert hist[0]["role"] == "user"
    assert hist[1]["content"].startswith("你好")


def test_history_limit(isolated_memory):
    sid = "sess-limit"
    for i in range(30):
        isolated_memory.append_message(sid, "user", f"消息{i}")
    hist = isolated_memory.get_history(sid, limit=20)
    assert len(hist) == 20


def test_history_empty(isolated_memory):
    assert isolated_memory.get_history("不存在") == []


def test_context_roundtrip(isolated_memory):
    isolated_memory.save_context("current_kb", {"id": "kb-1", "name": "默认"})
    assert isolated_memory.get_context("current_kb") == {"id": "kb-1", "name": "默认"}
    assert isolated_memory.get_context("missing", {"fallback": True}) == {"fallback": True}


def test_errors_swallowed(isolated_memory):
    """数据库损坏时操作只记日志不抛异常。"""
    isolated_memory.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    isolated_memory.DB_PATH.write_text("not a sqlite db", encoding="utf-8")
    # 重新连接会失败,但接口应吞掉异常
    isolated_memory.append_message("s", "user", "x")
    isolated_memory.get_history("s")
    isolated_memory.save_context("k", "v")
    isolated_memory.get_context("k")
