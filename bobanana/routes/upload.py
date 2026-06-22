"""文件上传路由 — 接收文件后立即返回，后台异步处理。"""

import asyncio
import logging
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File

from bobanana.config import UPLOAD_DIR
from bobanana.models import ApiResponse
from bobanana.agent import run_import_workflow, run_import_workflow_homework

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/upload", tags=["upload"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".md", ".txt"}

# 后台任务状态
_tasks: dict[str, dict] = {}


def _run_import_sync(file_path: str, filename: str, task_id: str, file_type: str = "course", kb_id: str = ""):
    """在线程中同步运行导入工作流，更新进度。"""
    from bobanana.database import db_manager
    from bobanana.config import CHROMA_COLLECTION_NAME
    old_col = db_manager._collection
    if kb_id and kb_id != CHROMA_COLLECTION_NAME:
        try:
            db_manager._collection = db_manager._client.get_or_create_collection(
                name="kb_" + kb_id, metadata={"hnsw:space": "cosine"},
            )
        except:
            pass
    try:
        if file_type == "hw":
            result = run_import_workflow_homework(file_path=file_path, filename=filename)
        else:
            result = run_import_workflow(file_path=file_path, filename=filename)
        _tasks[task_id] = {
            "status": "done",
            "message": f"成功 {len(result.success)} 张, 失败 {len(result.failed)} 张",
            "imported": len(result.success),
            "failed": len(result.failed),
            "cards": [c.model_dump() if hasattr(c, 'model_dump') else c for c in result.success[:20]],
        }
    except Exception as e:
        logger.error("导入失败: %s", e)
        _tasks[task_id] = {"status": "error", "message": str(e)}
    finally:
        db_manager._collection = old_col


@router.post("", response_model=ApiResponse)
async def upload_file(file: UploadFile = File(...), file_type: str = "course", kb_id: str = ""):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")
    if file_type not in ("course", "hw"):
        file_type = "course"

    safe_name = file.filename.replace("..", "").replace("/", "").replace("\\", "")
    dest = UPLOAD_DIR / safe_name
    content = await file.read()
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)

    logger.info("文件已保存: %s (%d bytes, type=%s)", safe_name, len(content), file_type)

    task_id = uuid.uuid4().hex[:12]
    _tasks[task_id] = {"status": "processing", "message": "解析中..."}

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_import_sync, str(dest), safe_name, task_id, file_type, kb_id)

    return ApiResponse(
        status="success",
        message="文件上传成功，后台解析中...",
        data={"task_id": task_id, "filename": safe_name, "size": len(content)},
    )


@router.get("/status/{task_id}", response_model=ApiResponse)
async def upload_status(task_id: str):
    """查询上传任务状态。"""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(status="success", data=task)
