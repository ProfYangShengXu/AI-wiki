"""指标路由 — GET /api/metrics 返回内存累积指标快照 (Phase 2 §5)。

鉴权由既有 auth 中间件统一处理, 本路由内不重复实现。
"""

import logging

from fastapi import APIRouter

from bobanana import config
from bobanana.models import ApiResponse
from bobanana.observability import metrics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/metrics", response_model=ApiResponse)
async def get_metrics():
    """返回内存累积指标快照 + LLM token 用量;METRICS_ENABLED=false 时返回 enabled:false。"""
    if not config.METRICS_ENABLED:
        return ApiResponse(status="success", data={"enabled": False})
    from bobanana.tools import get_token_usage
    data = metrics.snapshot()
    data["token_usage"] = get_token_usage()
    return ApiResponse(status="success", data=data)
