"""Bootstrap 路由 — 首次进入灰屏强制配置 API Key。

设计约束：
- status/test 永不返回完整 API Key；
- test 只验证、不落盘；
- configure 验证成功后才写入根目录 .env；
- 日志只记录 Key 尾号。
"""

import logging
import os
import tempfile
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from bobanana import config
from bobanana.models import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bootstrap", tags=["bootstrap"])

_PLACEHOLDER_KEYS = {"", "your-api-key-here", "sk-your-api-key-here", "sk-..."}

PROVIDERS = {
    "deepseek": {
        "key_env": "DEEPSEEK_API_KEY",
        "model_env": "DEEPSEEK_MODEL",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "default_base_url": "https://api.deepseek.com",
        "default_model": "deepseek-v4-flash",
    },
    "openai": {
        "key_env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "base_url_env": "OPENAI_BASE_URL",
        "default_base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
}


class BootstrapConfigRequest(BaseModel):
    provider: str = Field(default="deepseek", pattern="^(deepseek|openai)$")
    api_key: str = Field(..., min_length=8, max_length=512)
    base_url: str = Field(default="", max_length=512)
    model: str = Field(default="", max_length=128)


def _mask_key(api_key: str) -> str:
    """返回可安全展示的 Key 尾号，例如 sk-...abcd。"""
    if not api_key:
        return ""
    tail = api_key[-4:]
    prefix = "sk-..." if api_key.lower().startswith("sk-") else "..."
    return f"{prefix}{tail}"


def _provider_has_key(provider: str) -> bool:
    """当前供应商必须拥有有效 Key，避免用 OpenAI Key 冒充 DeepSeek。"""
    if provider == "openai":
        key = (config.OPENAI_API_KEY or "").strip()
    else:
        key = (config.DEEPSEEK_API_KEY or "").strip()
    return key.lower() not in _PLACEHOLDER_KEYS


def _read_env_file(env_path: Path) -> list[str]:
    if not env_path.exists():
        return []
    return env_path.read_text(encoding="utf-8").splitlines()


def _env_flag(env_path: Path) -> bool:
    for line in _read_env_file(env_path):
        line = line.strip()
        if line.startswith("STUDYWIKI_BOOTSTRAPPED="):
            return line.split("=", 1)[1].strip().strip('"').strip("'") == "1"
    return False


def _bootstrap_required(env_path: Path) -> bool:
    """首次运行或当前供应商无有效 Key 时要求灰屏。"""
    return not _env_flag(env_path) or not _provider_has_key(_current_provider())


def _current_provider() -> str:
    provider = (config.LLM_PROVIDER or "deepseek").strip().lower()
    return provider if provider in PROVIDERS else "deepseek"


def _provider_key_tail(provider: str) -> str:
    if provider == "openai":
        return _mask_key(config.OPENAI_API_KEY or "")
    return _mask_key(config.DEEPSEEK_API_KEY or "")


def _provider_base_url(provider: str) -> str:
    if provider == "openai":
        return config.OPENAI_BASE_URL or PROVIDERS["openai"]["default_base_url"]
    return config.DEEPSEEK_BASE_URL or PROVIDERS["deepseek"]["default_base_url"]


@router.get("/status", response_model=ApiResponse)
async def bootstrap_status():
    """返回灰屏状态。永不返回完整 API Key。"""
    provider = _current_provider()
    required = _bootstrap_required(config.ENV_FILE)
    key_tail = _provider_key_tail(provider)
    return ApiResponse(
        status="success",
        data={
            "required": required,
            "provider": provider,
            "has_key": _provider_has_key(provider),
            "key_tail": key_tail,
            "base_url": _provider_base_url(provider),
        },
    )


def _verify_api_key(
    provider: str, api_key: str, base_url: str, model: str = "",
) -> tuple[bool, str, str]:
    """用供应商轻量接口验证 Key。

    返回 (ok, message, error_code)。先尝试 /models,失败再尝试 1 token 补全。
    """
    base_url = (base_url or "").strip().rstrip("/") or PROVIDERS[provider]["default_base_url"]
    headers = {"Authorization": f"Bearer {api_key}"}
    probe_model = (model or "").strip() or PROVIDERS[provider]["default_model"]

    try:
        with httpx.Client(timeout=6.0) as client:
            models_resp = client.get(f"{base_url}/models", headers=headers)
            if models_resp.status_code == 200:
                return True, f"连接成功(模型 {probe_model})", ""
    except Exception:
        # /models 可能不存在或网络异常，继续走补全接口验证。
        pass

    try:
        payload = {
            "model": probe_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "temperature": 0,
        }
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        if resp.status_code == 200:
            return True, f"连接成功(模型 {probe_model})", ""
        if resp.status_code in (401, 403):
            return False, "API Key 无效或未授权，请检查后重试", "SW-BOOTSTRAP-401"
        if resp.status_code == 402:
            return False, "账户余额不足，请前往供应商控制台充值", "SW-BOOTSTRAP-429"
        if resp.status_code == 429:
            return False, "请求过于频繁或额度不足，请稍后重试", "SW-BOOTSTRAP-429"
        body_snippet = (resp.text or "")[:200].replace("\n", " ")
        return (
            False,
            f"模型服务返回异常状态码 {resp.status_code}: {body_snippet}",
            "SW-BOOTSTRAP-UPSTREAM",
        )
    except httpx.TimeoutException:
        return False, "验证超时，请检查网络或 API 地址", "SW-BOOTSTRAP-TIMEOUT"
    except httpx.HTTPError as exc:
        logger.warning("Bootstrap 验证网络错误: %s", exc.__class__.__name__)
        return False, "无法连接模型服务，请检查网络/代理或 API 地址", "SW-BOOTSTRAP-NETWORK"


@router.post("/test", response_model=ApiResponse)
async def bootstrap_test(payload: BootstrapConfigRequest):
    """验证 Key，不写 .env、不落盘。"""
    provider = payload.provider
    api_key = payload.api_key.strip()
    if api_key.lower() in _PLACEHOLDER_KEYS:
        raise HTTPException(status_code=400, detail="请填写有效的 API Key")

    ok, message, error_code = _verify_api_key(provider, api_key, payload.base_url, payload.model)
    if not ok:
        return ApiResponse(
            status="error",
            message=message,
            error_code=error_code,
            data={"ok": False, "key_tail": _mask_key(api_key)},
        )

    return ApiResponse(
        status="success",
        message=message,
        data={"ok": True, "provider": provider, "key_tail": _mask_key(api_key)},
    )


def _write_env_file(env_path: Path, updates: dict[str, str]) -> None:
    """原子更新 .env，保留注释与未涉及的配置项。"""
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = _read_env_file(env_path)
    key_positions: dict[str, int] = {}

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key:
            key_positions[key] = idx

    updated = set()
    for key, value in updates.items():
        quoted = f'{key}="{value}"'
        if key in key_positions:
            lines[key_positions[key]] = quoted
        else:
            lines.append(quoted)
        updated.add(key)

    fd, tmp_name = tempfile.mkstemp(prefix=".env.", dir=str(env_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            if lines and lines[-1] != "":
                f.write("\n")
        os.replace(tmp_name, env_path)
    except Exception:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except Exception:
            pass
        raise


def _apply_runtime_config(provider: str, api_key: str, base_url: str, model: str) -> None:
    """更新当前进程环境与 config 模块，使配置立即生效。"""
    spec = PROVIDERS[provider]
    base_url = (base_url or "").strip() or spec["default_base_url"]
    model = (model or "").strip() or spec["default_model"]

    updates = {
        "LLM_PROVIDER": provider,
        spec["key_env"]: api_key,
        spec["base_url_env"]: base_url,
        spec["model_env"]: model,
        "STUDYWIKI_BOOTSTRAPPED": "1",
    }
    for key, value in updates.items():
        os.environ[key] = value

    config.LLM_PROVIDER = provider
    if provider == "deepseek":
        config.DEEPSEEK_API_KEY = api_key
        config.DEEPSEEK_BASE_URL = base_url
        config.DEEPSEEK_MODEL = model
    else:
        config.OPENAI_API_KEY = api_key
        config.OPENAI_BASE_URL = base_url
        config.OPENAI_MODEL = model

    # 清空 LLM 缓存，确保后续请求使用新供应商。
    try:
        from bobanana.tools import reset_llm_cache

        reset_llm_cache()
    except Exception as exc:  # pragma: no cover - 仅在模块尚未加载时兜底
        logger.debug("清空 LLM 缓存失败: %s", exc)


@router.post("/configure", response_model=ApiResponse)
async def bootstrap_configure(payload: BootstrapConfigRequest):
    """验证成功后才写入 .env 并解除灰屏。"""
    provider = payload.provider
    api_key = payload.api_key.strip()
    if api_key.lower() in _PLACEHOLDER_KEYS:
        raise HTTPException(status_code=400, detail="请填写有效的 API Key")

    ok, message, error_code = _verify_api_key(provider, api_key, payload.base_url, payload.model)
    if not ok:
        return ApiResponse(
            status="error",
            message=message,
            error_code=error_code,
            data={"ok": False, "key_tail": _mask_key(api_key)},
        )

    spec = PROVIDERS[provider]
    base_url = (payload.base_url or "").strip() or spec["default_base_url"]
    model = (payload.model or "").strip() or spec["default_model"]

    env_path = config.ENV_FILE
    _write_env_file(
        env_path,
        {
            "LLM_PROVIDER": provider,
            spec["key_env"]: api_key,
            spec["base_url_env"]: base_url,
            spec["model_env"]: model,
            "STUDYWIKI_BOOTSTRAPPED": "1",
        },
    )
    _apply_runtime_config(provider, api_key, base_url, model)

    logger.info(
        "Bootstrap 完成: provider=%s key_tail=%s base_url=%s",
        provider,
        _mask_key(api_key),
        base_url,
    )

    return ApiResponse(
        status="success",
        message="配置成功，正在进入 StudyWiki-Agent",
        data={"ok": True, "provider": provider, "key_tail": _mask_key(api_key)},
    )
