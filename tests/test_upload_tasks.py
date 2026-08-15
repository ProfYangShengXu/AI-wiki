"""上传任务状态机 (Phase 2 §2) 测试:queued→…→done/cancelled、取消、续跑、去重。"""

import json
import time

import pytest
from fastapi.testclient import TestClient

from bobanana.app import app


@pytest.fixture
def task_env(tmp_path, monkeypatch):
    """隔离任务状态目录 + FakeLLM 提取。"""
    from bobanana import import_tasks
    from tests.fakes import FakeLLM
    monkeypatch.setattr(import_tasks, "IMPORT_TASKS_DIR", tmp_path / "tasks")
    fake = FakeLLM()
    fake.responses["知识提取专家"] = json.dumps([
        {"title": "与门(任务)", "content": "与门内容:所有输入为1时输出为1。",
         "category": "数字逻辑", "examples": [], "questions": [], "aliases": []},
    ], ensure_ascii=False)
    monkeypatch.setattr("bobanana.tools.llm_invoke", fake)
    monkeypatch.setattr("bobanana.agent.llm_invoke", fake)
    return fake


@pytest.fixture
def client():
    # 注意: 不用上下文管理器,避免 lifespan 启动真实生产 Chroma 客户端;
    # conftest 已把 db_manager 单例切换到 tmp 隔离库。
    c = TestClient(app)
    yield c
    c.close()


@pytest.fixture
def long_doc(tmp_path):
    doc = tmp_path / "upload.md"
    doc.write_text(
        "# 与门\n\n" + "与门是最基本的逻辑门,只有当所有输入都为高电平时输出才为高电平。"
        "逻辑表达式 Y 等于 A 与 B。真值表共有四种组合,只有输入都为一时输出才为一。"
        "与门在数字电路中常用于条件判断和使能控制,例如两把钥匙同时转动才能开门。\n",
        encoding="utf-8",
    )
    return doc


def _wait_status(client, task_id, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/upload/status/{task_id}")
        st = r.json()["data"]["status"]
        if st in ("done", "failed", "cancelled"):
            return r.json()["data"]
        time.sleep(0.2)
    raise TimeoutError(f"任务 {task_id} 未在 {timeout}s 内终止")


def test_upload_full_flow(task_env, client, long_doc):
    with open(long_doc, "rb") as f:
        resp = client.post("/api/upload", files={"file": ("upload.md", f, "text/markdown")})
    assert resp.status_code == 200
    task_id = resp.json()["data"]["task_id"]
    assert task_id

    data = _wait_status(client, task_id)
    assert data["status"] == "done", data
    assert data["result"]["imported"] >= 1


def test_upload_cancel(task_env, client, long_doc):
    with open(long_doc, "rb") as f:
        resp = client.post("/api/upload", files={"file": ("upload.md", f, "text/markdown")})
    task_id = resp.json()["data"]["task_id"]
    cr = client.post(f"/api/upload/cancel/{task_id}")
    assert cr.status_code == 200
    data = _wait_status(client, task_id)
    assert data["status"] in ("cancelled", "done")  # 竞态:可能已完成


def test_upload_status_404(task_env, client):
    r = client.get("/api/upload/status/nonexistent-id")
    assert r.status_code == 404
    assert r.json()["error_code"] == "SW-TASK-404"


def test_upload_resume_not_found(task_env, client):
    r = client.post("/api/upload/resume/nonexistent-id")
    assert r.status_code in (404, 400)


def test_upload_invalid_type_rejected(task_env, client, tmp_path):
    exe = tmp_path / "evil.exe"
    exe.write_bytes(b"MZ" + b"\x00" * 64)
    with open(exe, "rb") as f:
        r = client.post("/api/upload", files={"file": ("evil.exe", f, "application/octet-stream")})
    assert r.status_code == 400


def test_state_file_written(task_env, client, long_doc):
    from bobanana import import_tasks
    with open(long_doc, "rb") as f:
        resp = client.post("/api/upload", files={"file": ("upload.md", f, "text/markdown")})
    task_id = resp.json()["data"]["task_id"]
    _wait_status(client, task_id)
    state_path = import_tasks.IMPORT_TASKS_DIR / task_id / "state.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "done"
    assert state["task_id"] == task_id
