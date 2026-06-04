"""卡片 CRUD 路由 — 直通路由，不经 Agent。"""

from fastapi import APIRouter, HTTPException, Query

from bobanana.models import (
    CardCreate, CardUpdate, CardResponse, CardListResponse, ApiResponse,
)
from bobanana.service.card_service import card_service

router = APIRouter(prefix="/api/cards", tags=["cards"])


@router.get("", response_model=ApiResponse)
async def list_cards(
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
):
    cards, total = await card_service.list_cards(category, page, limit)
    return ApiResponse(
        status="success",
        data=CardListResponse(
            cards=[CardResponse(**c.model_dump()) for c in cards],
            total=total,
            page=page,
            limit=limit,
        ).model_dump(),
    )


@router.get("/search", response_model=ApiResponse)
async def search_cards(q: str = Query(..., min_length=1)):
    results = await card_service.search_cards(q)
    cards = [CardResponse(**c.model_dump()) for c, _ in results]
    return ApiResponse(
        status="success",
        data={"cards": [c.model_dump() for c in cards], "total": len(cards)},
    )


@router.get("/{card_id}", response_model=ApiResponse)
async def get_card(card_id: str):
    card = await card_service.get_card(card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return ApiResponse(
        status="success",
        data=CardResponse(**card.model_dump()).model_dump(),
    )


@router.post("", response_model=ApiResponse, status_code=201)
async def create_card(data: CardCreate):
    card = await card_service.create_card(data)
    return ApiResponse(
        status="success",
        message="卡片创建成功",
        data=CardResponse(**card.model_dump()).model_dump(),
    )


@router.put("/{card_id}", response_model=ApiResponse)
async def update_card(card_id: str, data: CardUpdate):
    card = await card_service.update_card(card_id, data)
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return ApiResponse(
        status="success",
        message="卡片更新成功",
        data=CardResponse(**card.model_dump()).model_dump(),
    )


@router.delete("/{card_id}", response_model=ApiResponse)
async def delete_card(card_id: str):
    deleted = await card_service.delete_card(card_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return ApiResponse(status="success", message="卡片已删除")
