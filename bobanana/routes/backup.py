"""备份 / 恢复路由 — 重 IO 同步端点(FastAPI 自动放入线程池执行)。"""


from fastapi import APIRouter
from pydantic import BaseModel

from bobanana.backup import (
    SW_BACKUP_500,
    create_backup,
    list_backups,
    restore_backup,
)
from bobanana.errors import SWError, sw_raise

router = APIRouter(prefix="/api/backup", tags=["backup"])


class RestoreRequest(BaseModel):
    """恢复请求体。``dry_run=true`` 时仅校验并返回计划, 不做任何修改。"""

    dry_run: bool = False


@router.post("/create")
def backup_create():
    """创建备份 → ``backups/swkb-YYYYmmdd-HHMMSS.zip``。"""
    try:
        path = create_backup()
    except SWError:
        raise
    except Exception as e:
        sw_raise(SW_BACKUP_500, f"备份失败: {e}")
    return {
        "status": "success",
        "data": {
            "name": path.name,
            "path": str(path),
            "size": path.stat().st_size,
        },
    }


@router.get("/list")
def backup_list():
    """列出所有备份及其 manifest 摘要。"""
    return {"status": "success", "data": {"backups": list_backups()}}


@router.post("/restore/{name}")
def backup_restore(name: str, payload: RestoreRequest | None = None):
    """恢复指定备份。``dry_run=true`` 仅返回校验计划; 不存在返回 SW_BACKUP_404。"""
    dry_run = bool(payload and payload.dry_run)
    result = restore_backup(name, dry_run=dry_run)
    return {"status": "success", "data": result}
