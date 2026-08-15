"""浏览历史路由 — 持久化到 JSON 文件，服务重启不丢失。"""

import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from bobanana.config import CHROMA_DB_DIR
from bobanana.models import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/history", tags=["history"])

HISTORY_FILE = CHROMA_DB_DIR / "browse_history.json"
MAX_HISTORY = 200


def _load_history() -> list[dict]:
    """从文件加载浏览历史。"""
    try:
        if HISTORY_FILE.exists():
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data[-MAX_HISTORY:]
    except Exception as e:
        logger.warning("读取浏览历史失败: %s", e)
    return []


def _save_history(history: list[dict]):
    """保存浏览历史到文件。"""
    try:
        HISTORY_FILE.write_text(
            json.dumps(history[-MAX_HISTORY:], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error("保存浏览历史失败: %s", e)


# 启动时加载
_history: list[dict] = _load_history()


class HistoryRecord(BaseModel):
    card_id: str
    title: str
    timestamp: str


@router.get("", response_model=ApiResponse)
async def get_history():
    return ApiResponse(
        status="success",
        data={"history": _history[-MAX_HISTORY:]},
    )


@router.post("", response_model=ApiResponse)
async def record_history(record: HistoryRecord):
    _history.append(record.model_dump())
    _save_history(_history)
    return ApiResponse(status="success", message="记录成功")
