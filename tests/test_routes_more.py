"""路由补充覆盖:cards generate/update/delete/deduplicate、history、settings、kb。"""

import pytest
from fastapi.testclient import TestClient

from bobanana.app import app
from bobanana.models import CardCreate
from bobanana.service.card_service import card_service


@pytest.fixture
def client():
    c = TestClient(app)
    yield c
    c.close()


@pytest.fixture
def fake_cards_llm(monkeypatch):
    from tests.fakes import FakeLLM
    fake = FakeLLM()
    fake.responses["知识卡片生成专家"] = (
        '{"title":"CPU","content":"中央处理器,负责取指译码执行。",'
        '"examples":["计算"],"questions":["什么是CPU"],"aliases":["处理器"],'
        '"category":"计算机"}'
    )
    monkeypatch.setattr("bobanana.routes.cards.llm_invoke", fake)
    return fake


def _mk(title="与门", category="数字逻辑"):
    return card_service.create_card_sync(CardCreate(
        title=title, category=category, content=f"{title}的内容。", source_file="test",
    ))


def test_cards_generate(fake_cards_llm, client):
    r = client.post("/api/cards/generate", json={"title": "CPU", "category": "计算机"})
    assert r.status_code == 201
    assert r.json()["data"]["title"] == "CPU"


def test_card_update_and_delete(client):
    cid = _mk()["id"]
    r = client.put(f"/api/cards/{cid}", json={"title": "新与门", "content": "更新内容"})
    assert r.status_code == 200
    assert r.json()["data"]["title"] == "新与门"

    r2 = client.delete(f"/api/cards/{cid}")
    assert r2.status_code == 200
    assert client.get(f"/api/cards/{cid}").status_code == 404


def test_cards_deduplicate(client):
    _mk("重复卡1")
    _mk("重复卡2")
    r = client.post("/api/cards/deduplicate")
    assert r.status_code == 200
    assert "merged" in r.json()["data"] or "deleted" in r.json()["data"]


def test_cards_list_with_category(client):
    _mk("分类卡", "专属分类")
    r = client.get("/api/cards", params={"category": "专属分类"})
    assert r.status_code == 200
    assert any(c["title"] == "分类卡" for c in r.json()["data"]["cards"])


def test_history_endpoints(client):
    cid = _mk()["id"]
    r = client.post("/api/history", json={"card_id": cid, "title": "与门", "timestamp": ""})
    assert r.status_code == 200
    r2 = client.get("/api/history")
    assert r2.status_code == 200


def test_settings_get_masked(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    data = r.json()["data"]
    assert "settings" in data
    # 完整 API Key 不得明文出现在响应中(掩码只显示尾部)
    from bobanana import config
    full_key = config.DEEPSEEK_API_KEY or ""
    body = str(r.json())
    if full_key:
        assert full_key not in body
        assert "sk-..." in body


def test_settings_save_allowed_key(tmp_path, monkeypatch, client):
    from bobanana.routes import settings as settings_mod
    monkeypatch.setattr(settings_mod, "ENV_PATH", tmp_path / ".env")
    (tmp_path / ".env").write_text('LLM_TEMPERATURE="0.1"\n', encoding="utf-8")
    r = client.post("/api/settings", json={"key": "LLM_TEMPERATURE", "value": "0.2"})
    assert r.status_code == 200
    assert "LLM_TEMPERATURE=0.2" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_settings_save_rejects_masked_key(tmp_path, monkeypatch, client):
    from bobanana.routes import settings as settings_mod
    monkeypatch.setattr(settings_mod, "ENV_PATH", tmp_path / ".env")
    r = client.post("/api/settings", json={"key": "DEEPSEEK_API_KEY", "value": "sk-***abcd"})
    assert r.status_code == 400


def test_settings_save_rejects_unknown_key(tmp_path, monkeypatch, client):
    from bobanana.routes import settings as settings_mod
    monkeypatch.setattr(settings_mod, "ENV_PATH", tmp_path / ".env")
    r = client.post("/api/settings", json={"key": "NOT_A_REAL_KEY", "value": "x"})
    assert r.status_code == 400


def test_kb_create_list_rename_delete(client):
    r = client.post("/api/kb/create", json={"name": "临时库"})
    assert r.status_code == 200
    kb_id = r.json()["data"]["id"]

    rl = client.get("/api/kb/list")
    names = [k["name"] for k in rl.json()["data"]["kbs"]]
    assert "临时库" in names

    rr = client.post(f"/api/kb/rename/{kb_id}", json={"name": "改名库"})
    assert rr.status_code == 200

    rd = client.delete(f"/api/kb/{kb_id}")
    assert rd.status_code == 200
