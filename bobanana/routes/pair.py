"""设备配对路由 — 局域网伴侣端 (Android/Flutter) 配对 (Phase 2 §7.1)。

流程:
1. `POST /api/pair/code` — 服务端生成一次性 6 位配对码 (TTL 300s);
2. `POST /api/pair/verify` — 客户端提交 {code, device_id},恒定时间比较,
   匹配则登记设备并返回 paired:true;错误码 SW-PAIR-401/404/400;
3. `GET /api/pair/status` — 配对状态与已登记设备列表 (脱敏)。

配对数据持久化到 data/pairing.json (已在 .gitignore)。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time

from fastapi import APIRouter
from pydantic import BaseModel

from bobanana.config import BASE_DIR
from bobanana.errors import SWError
from bobanana.models import ApiResponse

router = APIRouter(prefix="/api/pair", tags=["pair"])

# ── 错误码(与 bobanana/errors.py 的常量保持一致) ────────
SW_PAIR_400 = "SW-PAIR-400"
SW_PAIR_401 = "SW-PAIR-401"
SW_PAIR_404 = "SW-PAIR-404"

PAIR_DATA_FILE = BASE_DIR / "data" / "pairing.json"
CODE_TTL_SEC = 300

_lock = threading.Lock()
_current_code: dict | None = None  # {"code": str, "expires": float}


class PairVerifyRequest(BaseModel):
    code: str = ""
    device_id: str = ""


class PairCodeRequest(BaseModel):
    ttl_sec: int = CODE_TTL_SEC


def _load_devices() -> dict:
    try:
        if PAIR_DATA_FILE.exists():
            data = json.loads(PAIR_DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("devices"), dict):
                return data["devices"]
    except Exception:  # noqa: BLE001 — 配对文件损坏时按空处理并重建
        pass
    return {}


def _save_devices(devices: dict) -> None:
    PAIR_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    PAIR_DATA_FILE.write_text(
        json.dumps({"devices": devices, "updated_at": time.time()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


@router.post("/code", response_model=ApiResponse)
async def create_pair_code(req: PairCodeRequest | None = None):
    """生成一次性 6 位配对码 (默认 300s 过期)。"""
    ttl = max(30, min(int(req.ttl_sec) if req else CODE_TTL_SEC, 3600))
    code = f"{secrets.randbelow(1_000_000):06d}"
    global _current_code
    with _lock:
        _current_code = {"code": code, "expires": time.monotonic() + ttl}
    return ApiResponse(status="success", data={
        "code": code, "ttl_sec": ttl,
        "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + ttl)),
    })


@router.post("/verify", response_model=ApiResponse)
async def verify_pair(req: PairVerifyRequest):
    """校验配对码并登记设备。"""
    global _current_code
    code = (req.code or "").strip()
    device_id = (req.device_id or "").strip()
    if len(code) != 6 or not code.isdigit():
        raise SWError(SW_PAIR_400, "配对码格式错误(应为 6 位数字)")
    if not device_id or len(device_id) > 64:
        raise SWError(SW_PAIR_400, "设备标识缺失或过长")

    with _lock:
        current = _current_code
    if current is None:
        raise SWError(SW_PAIR_404, "服务端尚未生成配对码,请先在服务端获取")
    if time.monotonic() > current["expires"]:
        with _lock:
            _current_code = None
        raise SWError(SW_PAIR_401, "配对码已过期,请重新获取")
    if not _constant_time_eq(current["code"], code):
        raise SWError(SW_PAIR_401, "配对码错误")

    with _lock:
        _current_code = None  # 一次性使用
    devices = _load_devices()
    devices[device_id] = {
        "paired_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "device_id_hash": hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:12],
    }
    _save_devices(devices)
    return ApiResponse(status="success", data={
        "paired": True,
        "device_id": device_id,
        "paired_devices": len(devices),
    })


@router.get("/status", response_model=ApiResponse)
async def pair_status():
    """配对状态:是否有活跃配对码 + 已登记设备数(不返回原始 device_id)。"""
    with _lock:
        has_code = _current_code is not None and time.monotonic() <= _current_code["expires"]
    devices = _load_devices()
    return ApiResponse(status="success", data={
        "enabled": True,
        "active_code": has_code,
        "paired_devices": len(devices),
        "devices": [
            {"paired_at": v.get("paired_at", ""), "hash": v.get("device_id_hash", "")}
            for v in devices.values()
        ],
    })
