"""WebSocket 聊天测试:欢迎消息、Ask 流、Agent 工具事件、审批闭环。"""

import pytest
from fastapi.testclient import TestClient

from bobanana.app import app
from bobanana.models import CardCreate
from bobanana.service.card_service import card_service


@pytest.fixture
def ws_env(tmp_path, monkeypatch):
    """隔离记忆库。"""
    from bobanana import memory
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "memory.db")
    memory.init_db()
    return monkeypatch


def _patch_llm(monkeypatch, fake):
    monkeypatch.setattr("bobanana.tools.llm_invoke", fake)
    monkeypatch.setattr("bobanana.tools.llm_stream", lambda *a, **k: iter([fake(*a)]))
    monkeypatch.setattr("bobanana.agent_react.llm_invoke", fake)
    monkeypatch.setattr("bobanana.agent_react.llm_stream", lambda *a, **k: iter([fake(*a)]))
    monkeypatch.setattr("bobanana.tools.get_llm", lambda: None)
    monkeypatch.setattr("bobanana.agent_react.get_llm", lambda: None)


@pytest.fixture
def client():
    # 不使用上下文管理器: 避免 lifespan 启动生产 Chroma 客户端
    c = TestClient(app)
    yield c
    c.close()


def _drain_until(ws, pred, cap=30):
    """顺序接收消息直到命中 pred;服务端消息序是确定的,不会无限阻塞。"""
    for _ in range(cap):
        msg = ws.receive_json()
        if pred(msg):
            return msg
    raise TimeoutError("未等到期望的 WS 消息")


def test_welcome_and_session_started(ws_env, client):
    with client.websocket_connect("/ws/chat") as ws:
        started = ws.receive_json()
        assert started["type"] == "session.started"
        assert started["data"]["session_id"]
        welcome = ws.receive_json()
        assert welcome["type"] == "response"
        assert "StudyWiki" in welcome["content"]


def test_ask_mode_roundtrip(ws_env, client):
    from tests.fakes import FakeLLM
    ask = FakeLLM()
    ask.responses["问题"] = "测试回答:这是知识库中检索到的内容。"
    _patch_llm(ws_env, ask)

    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()  # session.started
        ws.receive_json()  # 欢迎
        ws.send_json({"type": "message", "content": "问题:什么是与门?", "data": {"mode": "ask"}})
        resp = _drain_until(ws, lambda m: m["type"] == "response" and "测试回答" in m["content"])
        assert "测试回答" in resp["content"]


def test_agent_tool_events_and_approval(ws_env, client):
    """Agent 模式:脚本化 ReAct → 审批 → 批准 → 完成并真实删除卡片。"""
    from tests.fakes import FakeLLM

    class AgentLLM(FakeLLM):
        def __init__(self):
            super().__init__()
            self.n = 0

        def __call__(self, system_prompt="", user_prompt="", timeout_sec=None):
            self.n += 1
            if self.n == 1:
                return 'Action: delete_card({"card_id_or_title": "待删卡片"})'
            return "Final Answer: 已删除「待删卡片」。"

    _patch_llm(ws_env, AgentLLM())

    card_service.create_card_sync(CardCreate(
        title="待删卡片", category="测试", content="用于审批流程测试的卡片。",
        source_file="test",
    ))
    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()  # session.started
        ws.receive_json()  # 欢迎
        ws.send_json({"type": "message", "content": "删除「待删卡片」", "data": {"mode": "agent"}})

        approval = _drain_until(ws, lambda m: m["type"] == "approval_required")
        assert approval["data"]["tool"] == "delete_card"
        aid = approval["data"]["approval_id"]

        ws.send_json({"type": "approval", "data": {"approval_id": aid, "approved": True}})

        final = _drain_until(ws, lambda m: m["type"] == "response" and "已删除" in m["content"])
        assert "已删除" in final["content"]

    cards, _ = card_service.list_cards_sync()
    assert not any(c.title == "待删卡片" for c in cards)
