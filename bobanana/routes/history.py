"""浏览历史路由 — 直通路由 (P1 骨架: 内存存储，后续可持久化)。"""

from fastapi import APIRouter
from pydantic import BaseModel

from bobanana.models import ApiResponse

router = APIRouter(prefix="/api/history", tags=["history"])

# P1 骨架: 内存列表，进程重启丢失
_history: list[dict] = []


class HistoryRecord(BaseModel):
    card_id: str
    title: str
    timestamp: str


@router.get("", response_model=ApiResponse)
async def get_history():
    return ApiResponse(
        status="success",
        data={"history": _history[-100:]},  # 最多保留 100 条
    )


@router.post("", response_model=ApiResponse)
async def record_history(record: HistoryRecord):
    _history.append(record.model_dump())
    return ApiResponse(status="success", message="记录成功")
