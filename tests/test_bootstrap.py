"""Bootstrap 灰屏强制配置 API Key 测试。

不访问真实 LLM，所有验证函数均被 mock。
"""


import pytest
from fastapi.testclient import TestClient

from bobanana import config
from bobanana.app import app
from bobanana.routes import bootstrap as bootstrap_route


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """隔离 .env 路径与配置值，避免污染真实环境。"""
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(config, "OPENAI_BASE_URL", "https://api.openai.com/v1")
    return tmp_path / ".env"


def test_status_requires_bootstrap_without_env(client, isolated_env):
    resp = client.get("/api/bootstrap/status")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["required"] is True
    assert data["has_key"] is False
    assert data["key_tail"] == ""
    # 响应绝不能包含完整 Key 字段
    assert "api_key" not in resp.text
    assert "DEEPSEEK_API_KEY" not in resp.text


def test_status_configured_after_marker_and_key(client, isolated_env, monkeypatch):
    isolated_env.write_text(
        'LLM_PROVIDER="deepseek"\nDEEPSEEK_API_KEY="sk-test123456"\nSTUDYWIKI_BOOTSTRAPPED=1\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "sk-test123456")

    resp = client.get("/api/bootstrap/status")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["required"] is False
    assert data["has_key"] is True
    assert data["key_tail"] == "sk-...3456"
    assert "sk-test123456" not in resp.text


def test_test_endpoint_does_not_persist_key(client, isolated_env, monkeypatch):
    monkeypatch.setattr(
        bootstrap_route,
        "_verify_api_key",
        lambda provider, api_key, base_url, model="": (True, "连接成功", ""),
    )

    resp = client.post(
        "/api/bootstrap/test",
        json={
            "provider": "deepseek",
            "api_key": "sk-test123456",
            "base_url": "https://api.deepseek.com",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["ok"] is True
    assert data["data"]["key_tail"] == "sk-...3456"
    assert not isolated_env.exists()
    assert "sk-test123456" not in resp.text


def test_configure_rejects_invalid_key(client, isolated_env, monkeypatch):
    monkeypatch.setattr(
        bootstrap_route,
        "_verify_api_key",
        lambda provider, api_key, base_url, model="": (
            False,
            "API Key 无效或未授权，请检查后重试",
            "SW-BOOTSTRAP-401",
        ),
    )

    resp = client.post(
        "/api/bootstrap/configure",
        json={
            "provider": "deepseek",
            "api_key": "sk-badkey123456",
            "base_url": "https://api.deepseek.com",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["error_code"] == "SW-BOOTSTRAP-401"
    assert not isolated_env.exists()


def test_configure_writes_env_and_unlocks(client, isolated_env, monkeypatch):
    monkeypatch.setattr(
        bootstrap_route,
        "_verify_api_key",
        lambda provider, api_key, base_url, model="": (True, "连接成功", ""),
    )

    resp = client.post(
        "/api/bootstrap/configure",
        json={
            "provider": "deepseek",
            "api_key": "sk-test123456",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["provider"] == "deepseek"
    assert data["data"]["key_tail"] == "sk-...3456"
    assert "sk-test123456" not in resp.text

    env_text = isolated_env.read_text(encoding="utf-8")
    assert 'DEEPSEEK_API_KEY="sk-test123456"' in env_text
    assert 'LLM_PROVIDER="deepseek"' in env_text
    assert 'STUDYWIKI_BOOTSTRAPPED="1"' in env_text

    resp = client.get("/api/bootstrap/status")
    assert resp.json()["data"]["required"] is False


def test_configure_rejects_placeholder_key(client, isolated_env):
    resp = client.post(
        "/api/bootstrap/configure",
        json={
            "provider": "deepseek",
            "api_key": "your-api-key-here",
            "base_url": "https://api.deepseek.com",
        },
    )
    assert resp.status_code == 400
    assert not isolated_env.exists()
