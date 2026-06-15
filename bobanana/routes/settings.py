"""设置 API — 前端可配置 LLM 参数。"""

import os
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

ENV_PATH = Path(__file__).parent.parent / ".env"

RELOAD_KEYS = {
    "OPENAI_API_KEY": "OpenAI API Key",
    "OPENAI_MODEL": "OpenAI 模型名",
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
}


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
    return {"status": "success", "data": {"settings": env, "descriptions": RELOAD_KEYS}}


@router.post("/")
async def save_setting(update: SettingsUpdate):
    """更新单条 .env 配置。"""
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

    logger.info("设置已更新: %s=%s", update.key, update.value[:10] + "..." if len(update.value) > 10 else update.value)
    return {"status": "success", "message": f"{RELOAD_KEYS.get(update.key, update.key)} 已更新"}


@router.post("/batch")
async def save_settings(updates: list[SettingsUpdate]):
    """批量更新 .env 配置。"""
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
