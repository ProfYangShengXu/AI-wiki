"""文件上传路由 — 接收文件后触发 Agent 导入工作流。"""

import asyncio
import logging
from pathlib import Path

import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File

from bobanana.config import UPLOAD_DIR
from bobanana.models import ApiResponse
from bobanana.agent import run_import_workflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/upload", tags=["upload"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".md", ".txt"}


def _run_import_sync(file_path: str, filename: str):
    """在线程中同步运行导入工作流。"""
    return run_import_workflow(file_path=file_path, filename=filename)


@router.post("", response_model=ApiResponse)
async def upload_file(file: UploadFile = File(...)):
    # 校验文件类型
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {ext}，允许: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # 保存文件
    safe_name = file.filename.replace("..", "").replace("/", "").replace("\\", "")
    dest = UPLOAD_DIR / safe_name
    content = await file.read()
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)

    logger.info("文件已保存: %s (%d bytes)", safe_name, len(content))

    # 在线程中运行 Agent 工作流，避免阻塞事件循环
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, _run_import_sync, str(dest), safe_name
    )

    return ApiResponse(
        status="success",
        message=f"文件解析完成: 成功 {len(result.success)} 张, 失败 {len(result.failed)} 张",
        data={
            "filename": safe_name,
            "size": len(content),
            "imported": len(result.success),
            "failed": len(result.failed),
            "failed_details": result.failed[:10],
            "cards": result.success[:20],
        },
    )
