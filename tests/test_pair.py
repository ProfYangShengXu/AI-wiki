"""设备配对 (Phase 2 §7.1) 测试。"""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bobanana.routes import pair as pair_mod
from bobanana.routes.pair import router as pair_router


@pytest.fixture
def pair_env(tmp_path, monkeypatch):
    monkeypatch.setattr(pair_mod, "PAIR_DATA_FILE", tmp_path / "pairing.json")
    with pair_mod._lock:
        pair_mod._current_code = None
    app = FastAPI()

    # 注册与 bobanana.app 一致的 SWError 处理器
    from fastapi import Request
    from fastapi.responses import JSONResponse

    from bobanana.errors import SWError

    @app.exception_handler(SWError)
    async def _sw_error_handler(request: Request, exc: SWError):
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    app.include_router(pair_router)
    c = TestClient(app)
    yield c
    c.close()


def test_code_then_verify(pair_env):
    r = pair_env.post("/api/pair/code", json={"ttl_sec": 300})
    assert r.status_code == 200
    code = r.json()["data"]["code"]
    assert len(code) == 6 and code.isdigit()

    r2 = pair_env.post("/api/pair/verify", json={"code": code, "device_id": "android-001"})
    assert r2.status_code == 200
    assert r2.json()["data"]["paired"] is True


def test_verify_wrong_code(pair_env):
    r = pair_env.post("/api/pair/code", json={})
    code = r.json()["data"]["code"]
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"  # 保证与生成码不同
    r2 = pair_env.post("/api/pair/verify", json={"code": wrong, "device_id": "d"})
    assert r2.status_code == 401
    assert r2.json()["error_code"] == "SW-PAIR-401"


def test_verify_bad_format(pair_env):
    r = pair_env.post("/api/pair/verify", json={"code": "abc", "device_id": "d"})
    assert r.status_code == 400
    assert r.json()["error_code"] == "SW-PAIR-400"


def test_verify_no_code_generated(pair_env):
    r = pair_env.post("/api/pair/verify", json={"code": "123456", "device_id": "d"})
    assert r.status_code == 404
    assert r.json()["error_code"] == "SW-PAIR-404"


def test_code_single_use(pair_env):
    r = pair_env.post("/api/pair/code", json={})
    code = r.json()["data"]["code"]
    ok = pair_env.post("/api/pair/verify", json={"code": code, "device_id": "dev-1"})
    assert ok.status_code == 200
    again = pair_env.post("/api/pair/verify", json={"code": code, "device_id": "dev-2"})
    assert again.status_code in (401, 404)  # 一次性使用


def test_code_expiry(pair_env):
    r = pair_env.post("/api/pair/code", json={"ttl_sec": 30})
    code = r.json()["data"]["code"]
    with pair_mod._lock:
        pair_mod._current_code["expires"] = time.monotonic() - 1
    resp = pair_env.post("/api/pair/verify", json={"code": code, "device_id": "d"})
    assert resp.status_code == 401


def test_status(pair_env):
    r = pair_env.get("/api/pair/status")
    assert r.status_code == 200
    data = r.json()["data"]
    assert "paired_devices" in data and "enabled" in data
