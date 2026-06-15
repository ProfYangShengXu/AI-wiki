"""卡片 CRUD 路由 — 直通路由，不经 Agent。"""

import re

from fastapi import APIRouter, HTTPException, Query

from bobanana.models import (
    CardCreate, CardUpdate, CardResponse, CardListResponse, ApiResponse,
)
from bobanana.service.card_service import card_service
from bobanana.tools import llm_invoke

router = APIRouter(prefix="/api/cards", tags=["cards"])


@router.post("/generate", response_model=ApiResponse, status_code=201)
async def generate_card(data: CardCreate):
    """用 LLM 生成知识卡片内容。"""
    import asyncio
    loop = asyncio.get_event_loop()

    def _gen():
        prompt = f"""你是一个知识专家。请为以下知识点生成完整的学习卡片，JSON 格式：

知识点: {data.title}
分类: {data.category or '未分类'}
{"参考: " + data.content if data.content else ""}

返回 JSON:
{{
  "title": "精简标题(3-15字)",
  "aliases": ["别名1", "英文名"],
  "content": "详细解释(400-600字,包含: 核心概念概括 → 原理机制 → 比喻/类比 → 知识关联)",
  "examples": ["案例1(包含比喻)", "案例2(实际应用)"],
  "questions": ["理解型问题1", "联系型问题2"],
  "category": "分类"
}}"""
        return llm_invoke("你是知识卡片生成专家。只返回 JSON。", prompt)

    raw = await loop.run_in_executor(None, _gen)
    import json as _json
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    m = re.search(r"(\{.*\})", clean, re.DOTALL)
    if m: clean = m.group(1)
    try: parsed = _json.loads(clean)
    except:
        m = re.search(r"(\[.*\])", clean, re.DOTALL)
        if m:
            try: arr = _json.loads(m.group(1)); parsed = arr[0] if isinstance(arr, list) and arr else None
            except: parsed = None
        else: parsed = None
    if not parsed or not isinstance(parsed, dict):
        raise HTTPException(status_code=500, detail=f"LLM 生成失败，返回格式错误: {raw[:200]}")

    card_data = CardCreate(
        title=parsed.get("title", data.title),
        aliases=parsed.get("aliases", data.aliases or []),
        content=parsed.get("content", parsed.get("content", "")),
        examples=parsed.get("examples", []),
        questions=parsed.get("questions", []),
        category=parsed.get("category", data.category or "未分类"),
        source_file=data.source_file or "manual",
        source_page=0,
    )
    card = await card_service.create_card(card_data)
    return ApiResponse(
        status="success",
        message=f"卡片已生成: {card.title}",
        data=CardResponse(**card.model_dump()).model_dump(),
    )



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
