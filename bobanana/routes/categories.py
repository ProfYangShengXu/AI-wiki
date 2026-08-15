"""分类路由 — 直通路由。"""

from fastapi import APIRouter

from bobanana.models import ApiResponse
from bobanana.service.card_service import card_service

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=ApiResponse)
async def list_categories():
    categories = await card_service.get_categories()
    return ApiResponse(
        status="success",
        data={"categories": categories},
    )
