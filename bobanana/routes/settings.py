"""设置 API — 前端可配置 LLM 参数。"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from bobanana import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

ENV_PATH = config.ENV_FILE

RELOAD_KEYS = {
    "OPENAI_API_KEY": "OpenAI API Key",
    "OPENAI_MODEL": "OpenAI 模型名",
    "OPENAI_BASE_URL": "OpenAI API 地址",
    "DEEPSEEK_API_KEY": "DeepSeek API Key",
    "DEEPSEEK_MODEL": "DeepSeek 模型名",
    "DEEPSEEK_BASE_URL": "DeepSeek API 地址",
    "OLLAMA_BASE_URL": "Ollama 地址",
    "OLLAMA_MODEL": "Ollama 模型名",
    "LLM_PROVIDER": "LLM 供应商 (openai/deepseek/ollama)",
    "LLM_TEMPERATURE": "温度 (0.0-2.0)",
    "LLM_MAX_TOKENS": "最大 Token 数",
    "LLM_TIMEOUT_SEC": "超时秒数",
    "EMBEDDING_PROVIDER": "嵌入模型 (openai/sentence-transformers)",
    "HOST": "监听地址(127.0.0.1 仅本机 / 0.0.0.0 允许局域网配对)",
}
def _mask_value(key: str, value: str) -> str:
    """API Key 只显示尾号，其他值原样返回。"""
    if "API_KEY" in key and value:
        value = value.strip().strip('"').strip("'")
        if len(value) <= 8:
            return "***"
        return f"{value[:3]}...{value[-4:]}"
    return value


def _validate_update(key: str, value: str) -> None:
    if key not in RELOAD_KEYS:
        raise HTTPException(status_code=400, detail=f"不允许修改配置项: {key}")
    if "API_KEY" in key and value and ("..." in value or "***" in value):
        raise HTTPException(status_code=400, detail="API Key 不能使用掩码值，请输入完整 Key")
    if key == "LLM_PROVIDER" and value not in {"openai", "deepseek", "ollama"}:
        raise HTTPException(status_code=400, detail="LLM_PROVIDER 仅支持 openai/deepseek/ollama")


def _log_value(key: str, value: str) -> str:
    return _mask_value(key, value) if "API_KEY" in key else value


class SettingsUpdate(BaseModel):
    key: str
    value: str


@router.get("/")
async def get_settings():
    """读取当前 .env 配置。"""
    env = {}
    if ENV_PATH.exists():
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    masked_env = {k: _mask_value(k, v) for k, v in env.items() if k in RELOAD_KEYS}
    return {"status": "success", "data": {"settings": masked_env, "descriptions": RELOAD_KEYS}}


@router.post("/")
async def save_setting(update: SettingsUpdate):
    """更新单条 .env 配置。"""
    _validate_update(update.key, update.value)
    env = {}
    if ENV_PATH.exists():
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()

    env[update.key] = update.value

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")

    logger.info("设置已更新: %s=%s", update.key, _log_value(update.key, update.value))
    return {"status": "success", "message": f"{RELOAD_KEYS.get(update.key, update.key)} 已更新"}


@router.post("/batch")
async def save_settings(updates: list[SettingsUpdate]):
    """批量更新 .env 配置。"""
    for update in updates:
        _validate_update(update.key, update.value)
    env = {}
    if ENV_PATH.exists():
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()

    for u in updates:
        env[u.key] = u.value

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")

    logger.info("批量设置已更新: %d 项", len(updates))
    return {"status": "success", "message": f"{len(updates)} 项设置已更新"}
