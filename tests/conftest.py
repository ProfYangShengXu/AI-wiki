"""pytest 全局测试底座。

目标:
- 让整个测试套件在【无 API Key、无网络】环境下全绿;
- 让所有测试使用 tmp_path 下的隔离 ChromaDB, 永不触碰生产 chroma_db/ 目录;
- 提供 STUDYWIKI_TEST_MODE=1 供代码侧未来判断测试环境。

所有需要数据库的测试模块 (test_e2e / test_database / test_routes / test_tools_layer 等)
无需再自行创建指向生产路径的 PersistentClient, 统一由本文件提供。
"""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _studywiki_test_mode():
    """会话级标记测试环境, 供 bobanana 侧未来判断。"""
    os.environ["STUDYWIKI_TEST_MODE"] = "1"
    yield
    os.environ.pop("STUDYWIKI_TEST_MODE", None)


TEST_SUITE_COLLECTION = "test_suite_cards"


@pytest.fixture(autouse=True)
def isolated_chroma(tmp_path, monkeypatch):
    """函数级隔离 ChromaDB。

    每个测试在 tmp_path 下创建独立 PersistentClient (关闭遥测), 并让
    bobanana.database.db_manager 单例切换到该客户端上的专用测试 collection。
    测试结束删除该 collection, 并把 _client 恢复原状 (monkeypatch 自动还原)。
    """
    import chromadb

    from bobanana.database import db_manager

    client = chromadb.PersistentClient(
        path=str(tmp_path / "chroma"),
        settings=chromadb.config.Settings(anonymized_telemetry=False),
    )
    # 把单例 db_manager 指向隔离客户端 (其它模块已持有同一单例引用, 均生效)
    monkeypatch.setattr(db_manager, "_client", client)

    test_col = client.get_or_create_collection(
        name=TEST_SUITE_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )
    old_col = db_manager.get_collection()
    db_manager.switch_collection(test_col)

    yield client

    # 收尾:取消并等待仍未结束的后台导入任务,避免其 worker 线程
    # 跨测试触碰下一个测试的 collection(串扰 flake)。
    try:
        import time as _time

        from bobanana.import_tasks import import_task_manager as _task_manager
        _terminal = ("done", "failed", "cancelled")
        for _task in list(getattr(_task_manager, "_tasks", {}).values()):
            if getattr(_task, "status", "done") not in _terminal:
                _task_manager.cancel(getattr(_task, "task_id", ""))
        _deadline = _time.monotonic() + 2
        while _time.monotonic() < _deadline:
            _active = [
                t for t in getattr(_task_manager, "_tasks", {}).values()
                if getattr(t, "status", "done") not in _terminal
            ]
            if not _active:
                break
            _time.sleep(0.1)
    except Exception:
        pass

    db_manager.switch_collection(old_col)
    try:
        client.delete_collection(TEST_SUITE_COLLECTION)
    except Exception:
        pass
