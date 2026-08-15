"""import_tasks 单元覆盖:TokenBucket、去重、状态机、bootstrap Key 验证。"""

import threading

import pytest

from bobanana import import_tasks


def test_normalize_title():
    assert import_tasks.normalize_title("  Hello, World!  ") == "helloworld"
    assert import_tasks.normalize_title("与门(AND)") == "与门and"


def test_token_bucket_exhausts():
    bucket = import_tasks.TokenBucket(capacity=2, window_sec=10)
    assert bucket.acquire() is True
    assert bucket.acquire() is True
    # 桶空:带取消事件 → 分段休眠后响应取消,返回 False
    ev = threading.Event()
    ev.set()
    assert bucket.acquire(cancel_event=ev) is False


def test_dedup_index(isolated_chroma):
    from bobanana.models import CardCreate
    from bobanana.service.card_service import card_service
    card_service.create_card_sync(CardCreate(
        title="与门", category="数字逻辑", content="与门是基本逻辑门。", aliases=["AND"],
    ))
    cards, _ = card_service.list_cards_sync()
    di = import_tasks.DedupIndex(cards)
    # 标题规范化命中
    ok, reason = di.check("与门", [], "其它内容")
    assert ok is True and reason
    # 别名命中(候选以别名形式提供)
    ok2, _ = di.check("异名标题", ["AND"], "其它内容")
    assert ok2 is True
    # 全新知识点
    ok3, _ = di.check("触发器", [], "触发器是时序电路的基本单元")
    assert ok3 is False


def test_manager_create_get_cancel(tmp_path, monkeypatch):
    monkeypatch.setattr(import_tasks, "IMPORT_TASKS_DIR", tmp_path / "tasks")
    mgr = import_tasks.ImportTaskManager()
    task_id = mgr.create_task("/tmp/x.md", "x.md", kb_id="")
    task = mgr.get_task(task_id)
    assert task["status"] == "queued"
    state = mgr.cancel(task_id)
    # queued 任务的取消是异步信号:事件置位,状态由 worker 观察后迁移
    assert state["status"] in ("queued", "cancelled")
    assert mgr._tasks[task_id].cancel_event.is_set()


def test_manager_resume_queued_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(import_tasks, "IMPORT_TASKS_DIR", tmp_path / "tasks")
    mgr = import_tasks.ImportTaskManager()
    task_id = mgr.create_task("/tmp/x.md", "x.md", kb_id="")
    with pytest.raises(Exception):  # noqa: B017
        mgr.resume(task_id)  # queued 状态不可续跑


def test_manager_unknown_task(tmp_path, monkeypatch):
    monkeypatch.setattr(import_tasks, "IMPORT_TASKS_DIR", tmp_path / "tasks")
    mgr = import_tasks.ImportTaskManager()
    assert mgr.get_task("no-such-id") is None


def test_bootstrap_verify_api_key_models_ok(monkeypatch):
    """_verify_api_key:/models 返回 200 → 成功,不发补全请求。"""
    from bobanana.routes import bootstrap

    class FakeResponse:
        status_code = 200

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, headers):
            assert "/models" in url
            return FakeResponse()

        def post(self, url, headers, json):
            raise AssertionError("不应走到补全接口")

    monkeypatch.setattr(bootstrap.httpx, "Client", FakeClient)
    ok, msg, code = bootstrap._verify_api_key("deepseek", "sk-test", "")
    assert ok is True and code == ""


def test_bootstrap_verify_api_key_401(monkeypatch):
    from bobanana.routes import bootstrap

    class FakeResponse:
        status_code = 401

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, headers):
            raise RuntimeError("models 不可用")

        def post(self, url, headers, json):
            return FakeResponse()

    monkeypatch.setattr(bootstrap.httpx, "Client", FakeClient)
    ok, msg, code = bootstrap._verify_api_key("deepseek", "sk-bad", "")
    assert ok is False and code == "SW-BOOTSTRAP-401"


def test_bootstrap_verify_api_key_network_error(monkeypatch):
    from bobanana.routes import bootstrap

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, headers):
            raise bootstrap.httpx.ConnectError("down")

        def post(self, url, headers, json):
            raise bootstrap.httpx.ConnectError("down")

    monkeypatch.setattr(bootstrap.httpx, "Client", FakeClient)
    ok, msg, code = bootstrap._verify_api_key("deepseek", "sk-x", "")
    assert ok is False and code == "SW-BOOTSTRAP-NETWORK"
