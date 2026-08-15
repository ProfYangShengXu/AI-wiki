"""文件上传路由 — 接收文件后立即返回，后台异步处理。

导入任务生命周期由 ``bobanana.import_tasks.ImportTaskManager`` 管理:
- POST /api/upload              → 创建任务 (queued),后台线程推进状态机;
- GET  /api/upload/status/{id}  → 查询任务状态;
- POST /api/upload/cancel/{id}  → 取消任务 (幂等);
- POST /api/upload/resume/{id}  → 断点续跑 (仅 failed/cancelled 且存在 state.json)。
"""

import logging
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile

from bobanana.config import UPLOAD_DIR
from bobanana.errors import SW_TASK_404, sw_raise
from bobanana.import_tasks import import_task_manager
from bobanana.models import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/upload", tags=["upload"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".md", ".txt"}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100MB

_STATUS_FIELDS = ("task_id", "status", "message", "progress", "result")


def _looks_valid(ext: str, content: bytes) -> bool:
    """基础魔数校验，避免把任意二进制伪装成文档。"""
    if ext == ".pdf":
        return content[:5] == b"%PDF-"
    if ext == ".docx":
        return content[:2] == b"PK"
    if ext == ".doc":
        return content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    return True


def _status_payload(task_id: str) -> dict:
    """从 manager 取状态并裁剪为对外返回字段。"""
    state = import_task_manager.get_task(task_id)
    if state is None:
        sw_raise(SW_TASK_404, "任务不存在")
    return {k: state.get(k) for k in _STATUS_FIELDS}


@router.post("", response_model=ApiResponse)
async def upload_file(file: UploadFile = File(...), file_type: str = "course", kb_id: str = ""):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")
    if file_type not in ("course", "hw"):
        file_type = "course"

    original_name = Path(file.filename or "upload").name.replace("..", "").replace("/", "").replace("\\", "")
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / safe_name
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 100MB 限制")
    if not _looks_valid(ext, content):
        raise HTTPException(status_code=400, detail="文件内容与扩展名不匹配")
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)

    logger.info("文件已保存: %s -> %s (%d bytes, type=%s)", original_name, safe_name, len(content), file_type)

    # 走 ImportTaskManager: 立即 queued,后台线程推进状态机。
    task_id = import_task_manager.create_task(
        file_path=str(dest), filename=original_name, kb_id=kb_id, file_type=file_type,
    )
    import_task_manager.start(task_id)

    return ApiResponse(
        status="success",
        message="文件上传成功，后台解析中...",
        data={"task_id": task_id, "filename": original_name, "storage_name": safe_name, "size": len(content)},
    )


@router.get("/status/{task_id}", response_model=ApiResponse)
async def upload_status(task_id: str):
    """查询上传任务状态。"""
    return ApiResponse(status="success", data=_status_payload(task_id))


@router.post("/cancel/{task_id}", response_model=ApiResponse)
async def upload_cancel(task_id: str):
    """取消上传任务 — 幂等;已完成/已取消返回原状态。"""
    state = import_task_manager.cancel(task_id)
    return ApiResponse(
        status="success",
        message="取消请求已受理",
        data={k: state.get(k) for k in _STATUS_FIELDS},
    )


@router.post("/resume/{task_id}", response_model=ApiResponse)
async def upload_resume(task_id: str):
    """断点续跑 — 仅 failed/cancelled 且存在 state.json 时可恢复。"""
    state = import_task_manager.resume(task_id)
    return ApiResponse(
        status="success",
        message="恢复请求已受理",
        data={k: state.get(k) for k in _STATUS_FIELDS},
    )
