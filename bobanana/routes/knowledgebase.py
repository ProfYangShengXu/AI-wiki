"""知识库管理 — 多库隔离，每个库使用独立 ChromaDB 集合。"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from bobanana.database import db_manager
from bobanana.config import CHROMA_COLLECTION_NAME

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kb", tags=["knowledgebase"])

_current_kb: str = CHROMA_COLLECTION_NAME
_kb_meta: dict[str, dict] = {
    CHROMA_COLLECTION_NAME: {
        "id": CHROMA_COLLECTION_NAME,
        "name": "默认知识库",
        "created": datetime.now(timezone.utc).isoformat(),
        "card_count": 0,
    }
}


class KBCreate(BaseModel):
    name: str


class KBRename(BaseModel):
    name: str


def _ensure_collection(name: str):
    return db_manager.client.get_or_create_collection(
        name=name, metadata={"hnsw:space": "cosine"},
    )


@router.get("/list")
async def list_kbs():
    """列出所有知识库 + 当前库。"""
    cid = _current_kb
    if cid in _kb_meta:
        try:
            _kb_meta[cid]["card_count"] = db_manager.count()
        except Exception:
            _kb_meta[cid]["card_count"] = 0
    return {"status": "success", "data": {"current": cid, "kbs": list(_kb_meta.values())}}


@router.post("/create")
async def create_kb(data: KBCreate):
    kb_id = uuid.uuid4().hex[:12]
    _kb_meta[kb_id] = {"id": kb_id, "name": data.name, "created": datetime.now(timezone.utc).isoformat(), "card_count": 0}
    try:
        _ensure_collection("kb_" + kb_id)
    except Exception:
        pass  # 集合会在第一次使用时自动创建
    return {"status": "success", "data": _kb_meta[kb_id]}


@router.post("/switch/{kb_id}")
async def switch_kb(kb_id: str):
    global _current_kb
    if kb_id not in _kb_meta:
        raise HTTPException(404, "知识库不存在")
    col_name = CHROMA_COLLECTION_NAME if kb_id == CHROMA_COLLECTION_NAME else "kb_" + kb_id
    try:
        db_manager._collection = _ensure_collection(col_name)
    except Exception as e:
        raise HTTPException(500, f"切换失败: {e}")
    _current_kb = kb_id
    count = db_manager.count()
    _kb_meta[kb_id]["card_count"] = count
    return {"status": "success", "data": {"current": kb_id, "name": _kb_meta[kb_id]["name"], "count": count}}


@router.delete("/{kb_id}")
async def delete_kb(kb_id: str):
    global _current_kb
    if kb_id not in _kb_meta:
        raise HTTPException(404, "知识库不存在")
    if kb_id == CHROMA_COLLECTION_NAME:
        raise HTTPException(400, "不能删除默认知识库")
    try:
        db_manager.client.delete_collection("kb_" + kb_id)
    except Exception:
        pass
    del _kb_meta[kb_id]
    if _current_kb == kb_id:
        col = _ensure_collection(CHROMA_COLLECTION_NAME)
        db_manager._collection = col
        _current_kb = CHROMA_COLLECTION_NAME
    return {"status": "success", "message": "已删除"}


@router.post("/rename/{kb_id}")
async def rename_kb(kb_id: str, data: KBRename):
    """重命名知识库。"""
    if kb_id not in _kb_meta:
        raise HTTPException(404, "知识库不存在")
    _kb_meta[kb_id]["name"] = data.name
    return {"status": "success", "data": _kb_meta[kb_id]}
