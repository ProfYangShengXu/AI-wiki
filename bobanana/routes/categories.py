"""分类路由 — 列表 + 手动 CRUD。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from bobanana.models import ApiResponse
from bobanana.service.card_service import card_service

router = APIRouter(prefix="/api/categories", tags=["categories"])


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)


class CategoryRename(BaseModel):
    old_name: str = Field(..., min_length=1, max_length=50)
    new_name: str = Field(..., min_length=1, max_length=50)


@router.get("", response_model=ApiResponse)
async def list_categories():
    categories = await card_service.get_categories()
    return ApiResponse(
        status="success",
        data={"categories": categories},
    )


@router.post("", response_model=ApiResponse, status_code=201)
async def create_category(data: CategoryCreate):
    """新建分类 — 分类以卡片 category 字段存在, 这里仅校验名称可用。"""
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="分类名不能为空")
    existing = await card_service.get_categories()
    if name in existing:
        raise HTTPException(status_code=400, detail=f"分类「{name}」已存在")
    from bobanana.models import CardCreate
    card = await card_service.create_card(
        CardCreate(
            title=name,
            content="__CATEGORY_PLACEHOLDER__",
            category=name,
        )
    )
    return ApiResponse(
        status="success",
        message=f"分类「{name}」已创建",
        data={"category": name, "card_id": card.id},
    )


@router.put("", response_model=ApiResponse)
async def rename_category(data: CategoryRename):
    """重命名分类 — 同步修改该分类下所有卡片的 category。"""
    old_name = data.old_name.strip()
    new_name = data.new_name.strip()
    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="分类名不能为空")
    if old_name == new_name:
        return ApiResponse(status="success", message="名称未变化", data={"changed": 0})
    existing = await card_service.get_categories()
    if old_name not in existing:
        raise HTTPException(status_code=404, detail=f"分类「{old_name}」不存在")
    changed = await card_service.rename_category(old_name, new_name)
    return ApiResponse(
        status="success",
        message=f"分类已重命名, {changed} 张卡片受影响",
        data={"changed": changed},
    )


@router.delete("/{category}", response_model=ApiResponse)
async def delete_category(category: str):
    """删除分类 — 该分类下卡片归入「通用」。"""
    name = category.strip()
    existing = await card_service.get_categories()
    if name not in existing:
        raise HTTPException(status_code=404, detail=f"分类「{name}」不存在")
    changed = await card_service.delete_category(name, fallback="通用")
    return ApiResponse(
        status="success",
        message=f"分类「{name}」已删除, {changed} 张卡片归入「通用」",
        data={"changed": changed},
    )
