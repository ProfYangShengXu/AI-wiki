"""db_manager 生命周期测试:startup/shutdown/健康检查/维度校验/磁盘水位/失败重试。"""

import asyncio

import pytest

from bobanana.database import db_manager
from bobanana.errors import SWError
from bobanana.models import KnowledgeCard


@pytest.fixture
def card():
    return KnowledgeCard(
        id="test-card-1", title="测试卡", category="测试", content="内容" * 20,
    )


@pytest.fixture
def startup_env(tmp_path, monkeypatch):
    """startup/shutdown 测试专用:重定向生产路径,避免触碰生产 chroma_db。"""
    from bobanana import database as dbmod
    monkeypatch.setattr(dbmod, "CHROMA_DB_DIR", tmp_path / "chroma")
    monkeypatch.setattr(dbmod, "CHROMA_COLLECTION_NAME", "lifecycle_cards")
    # 停止后台线程需要的 stop_event
    return dbmod


def test_startup_shutdown_roundtrip(startup_env, monkeypatch):
    monkeypatch.setattr(db_manager, "_client", None)
    monkeypatch.setattr(db_manager, "_collection", None)
    asyncio.run(db_manager.startup())
    assert db_manager._persist_thread is not None
    assert db_manager._retry_thread is not None
    asyncio.run(db_manager.shutdown())
    asyncio.run(db_manager.shutdown())  # 幂等


def test_health_check(isolated_chroma):
    asyncio.run(db_manager._health_check())


def test_validate_dimension(isolated_chroma, card):
    db_manager.add_card(card, [0.1] * 384)
    asyncio.run(db_manager._validate_dimension())


def test_disk_space_stop_rejects(monkeypatch, isolated_chroma):
    from bobanana import database as dbmod
    monkeypatch.setattr(dbmod, "CHROMA_DISK_STOP_MB", 10**9)  # 强制低于阈值
    with pytest.raises(SWError) as exc:
        db_manager.add_card(
            KnowledgeCard(id="x1", title="t", content="c" * 30), [0.1] * 384,
        )
    assert exc.value.error_code == "SW-DB-507"


def test_disk_space_warn_allows(monkeypatch, isolated_chroma, card):
    from bobanana import database as dbmod
    monkeypatch.setattr(dbmod, "CHROMA_DISK_WARN_MB", 10**9)
    monkeypatch.setattr(dbmod, "CHROMA_DISK_STOP_MB", 1)
    cid = db_manager.add_card(card, [0.1] * 384)
    assert cid == "test-card-1"


def test_pending_fails_retry_success(isolated_chroma, card, monkeypatch):
    """add 瞬时失败 → 入队 → 故障恢复后重试成功。"""
    real_add = db_manager._collection.add
    calls = {"n": 0}

    def _flaky_add(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("瞬时写入失败")
        return real_add(**kwargs)

    monkeypatch.setattr(db_manager._collection, "add", _flaky_add)
    with pytest.raises(RuntimeError):
        db_manager.add_card(card, [0.1] * 384)
    assert len(db_manager._pending_fails) == 1
    db_manager._retry_pending_fails()
    assert db_manager.get_card("test-card-1") is not None
    assert db_manager._pending_fails == []


def test_pending_fails_gives_up_after_3(isolated_chroma, card, monkeypatch):
    """持续失败 → 重试 3 次后放弃并清空队列。"""
    def _always_fail(**kwargs):
        raise RuntimeError("持续失败")

    monkeypatch.setattr(db_manager._collection, "add", _always_fail)
    with pytest.raises(RuntimeError):
        db_manager.add_card(card, [0.1] * 384)
    for _ in range(4):
        db_manager._retry_pending_fails()
    assert db_manager._pending_fails == []
    assert db_manager.get_card("test-card-1") is None


def test_switch_collection_safe(isolated_chroma):
    old = db_manager.get_collection()
    restored = db_manager.switch_collection_safe(old)
    assert restored is old


def test_count(isolated_chroma, card):
    db_manager.add_card(card, [0.1] * 384)
    assert db_manager.count() >= 1
