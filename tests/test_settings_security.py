"""设置页安全回归：Key 脱敏、白名单、掩码值拒绝。"""

import pytest
from fastapi.testclient import TestClient

from bobanana.app import app
from bobanana.routes import settings as settings_route


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(settings_route, "ENV_PATH", env_path)
    return env_path


def test_get_settings_masks_api_keys(client, tmp_env):
    tmp_env.write_text(
        'DEEPSEEK_API_KEY="sk-test123456"\n'
        'OPENAI_API_KEY="sk-openai1234"\n'
        'STUDYWIKI_AUTH_TOKEN="secret-token"\n',
        encoding="utf-8",
    )
    resp = client.get("/api/settings/")
    assert resp.status_code == 200
    data = resp.json()["data"]["settings"]
    assert data["DEEPSEEK_API_KEY"] == "sk-...3456"
    assert data["OPENAI_API_KEY"] == "sk-...1234"
    assert "STUDYWIKI_AUTH_TOKEN" not in data
    assert "sk-test123456" not in resp.text
    assert "secret-token" not in resp.text


def test_save_setting_rejects_unknown_key(client, tmp_env):
    resp = client.post(
        "/api/settings/",
        json={"key": "STUDYWIKI_AUTH_TOKEN", "value": "x"},
    )
    assert resp.status_code == 400


def test_save_setting_rejects_masked_api_key(client, tmp_env):
    resp = client.post(
        "/api/settings/",
        json={"key": "DEEPSEEK_API_KEY", "value": "sk-...abcd"},
    )
    assert resp.status_code == 400


def test_save_setting_accepts_whitelisted_key(client, tmp_env):
    resp = client.post(
        "/api/settings/",
        json={"key": "LLM_TEMPERATURE", "value": "0.2"},
    )
    assert resp.status_code == 200
    env_text = tmp_env.read_text(encoding="utf-8")
    assert 'LLM_TEMPERATURE=0.2' in env_text or 'LLM_TEMPERATURE="0.2"' in env_text
