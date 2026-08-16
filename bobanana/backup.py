"""备份 / 恢复库 — 纯函数实现, 不依赖 FastAPI。

职责:
- ``create_backup``: 快照 chroma_db + uploads, 打包为 ``backups/swkb-YYYYmmdd-HHMMSS.zip``,
  附带 ``backup_manifest.json``(版本 / 时间 / 文件名列表 / chroma_db 集合计数)。
- ``list_backups``: 扫描 ``backups/`` 目录, 返回 name / size / created_at / manifest 摘要。
- ``restore_backup``: ``dry_run=True`` 仅校验并返回计划; 真实恢复先自动
  ``pre-restore-*`` 备份, 再停机式覆盖还原, 失败时用 pre-restore 备份回滚。

错误码常量放在本模块顶部(避免与 errors.py 的另一并行工作流冲突);
OpenAPI 契约同步在第 4 轮处理。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import chromadb
from chromadb.config import Settings

from bobanana.config import CHROMA_DB_DIR, DATA_DIR, UPLOAD_DIR
from bobanana.errors import SWError, sw_raise

# ── 错误码常量 ──────────────────────────────────────────
SW_BACKUP_404 = "SW-BACKUP-404"   # 备份不存在
SW_BACKUP_500 = "SW-BACKUP-500"   # 备份 / 恢复失败

# ── 路径常量 ────────────────────────────────────────────
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)  # 已在 .gitignore

_MANIFEST_VERSION = "1.0"
_MASTERY_REL = "mastery.json"
_MANIFEST_NAME = "backup_manifest.json"

# 打包时显式排除的敏感/运行时内容(.env 与 logs/ 本就不在 chroma_db/uploads 下,
# 此处作为防御性过滤, 保证 zip 内容不含密钥与日志)。
_EXCLUDED_FILENAMES = {".env"}
_EXCLUDED_DIRS = {"logs", "__pycache__"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _is_excluded(rel_path: Path) -> bool:
    """过滤 .env 与 logs/ 目录。"""
    if rel_path.name in _EXCLUDED_FILENAMES:
        return True
    return any(part in _EXCLUDED_DIRS for part in rel_path.parts)


def _zip_dir(zf: zipfile.ZipFile, src: Path, arcname: str) -> None:
    """把 src 目录递归写入 zip, 排除 .env 与 logs/。"""
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        if _is_excluded(rel):
            continue
        zf.write(path, f"{arcname}/{rel.as_posix()}")


def _count_collections(chroma_dir: Path) -> dict[str, int]:
    """打开 chroma_dir 下的 ChromaDB, 返回 {collection_name: count}。"""
    try:
        client = chromadb.PersistentClient(
            path=str(chroma_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        return {col.name: col.count() for col in client.list_collections()}
    except Exception as e:
        raise SWError(
            error_code=SW_BACKUP_500,
            message=f"无法读取 ChromaDB 集合计数: {e}",
        ) from e


def create_backup(name: str | None = None) -> Path:
    """创建备份 zip, 返回生成的 Path。

    zip 内容:
    - ``chroma_db/``   整个目录(先快照到 tempfile 再打包, 避免打包中 ChromaDB 写入)
    - ``uploads/``     整个目录
    - ``mastery.json`` 来自 ``chroma_db/mastery.json``(同时放在顶层, 便于恢复)
    - ``backup_manifest.json`` 版本 / 时间 / 文件名列表 / 集合计数

    ``name`` 为空时自动生成 ``swkb-YYYYmmdd-HHMMSS.zip``。
    """
    backup_name = name or f"swkb-{_timestamp()}"
    if not backup_name.lower().endswith(".zip"):
        backup_name += ".zip"
    target = BACKUP_DIR / backup_name

    try:
        with tempfile.TemporaryDirectory(prefix="swkb-backup-") as tmp:
            tmp_root = Path(tmp)
            chroma_snapshot = tmp_root / "chroma_db"
            uploads_snapshot = tmp_root / "uploads"

            # 1) 先快照 chroma_db 到临时目录(避免打包过程中 ChromaDB 写入导致不一致)
            if CHROMA_DB_DIR.exists():
                shutil.copytree(CHROMA_DB_DIR, chroma_snapshot)
            # 2) 快照 uploads
            if UPLOAD_DIR.exists():
                shutil.copytree(UPLOAD_DIR, uploads_snapshot)

            # 3) mastery.json(物理上位于 chroma_db/ 内, 额外复制一份到顶层)
            mastery_top = tmp_root / _MASTERY_REL
            mastery_in_snapshot = chroma_snapshot / _MASTERY_REL
            if mastery_in_snapshot.exists():
                shutil.copy2(mastery_in_snapshot, mastery_top)
            else:
                mastery_src = CHROMA_DB_DIR / _MASTERY_REL
                if mastery_src.exists():
                    shutil.copy2(mastery_src, mastery_top)

            # 4) 基于快照统计集合计数
            collections = (
                _count_collections(chroma_snapshot) if chroma_snapshot.exists() else {}
            )

            # 5) 打包
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
                if chroma_snapshot.exists():
                    _zip_dir(zf, chroma_snapshot, "chroma_db")
                if uploads_snapshot.exists():
                    _zip_dir(zf, uploads_snapshot, "uploads")
                if mastery_top.exists():
                    zf.write(mastery_top, _MASTERY_REL)

                # 文件名列表 = 当前已写入的数据条目(不含 manifest 自身)
                files = sorted(n for n in zf.namelist())
                manifest = {
                    "version": _MANIFEST_VERSION,
                    "created_at": _utc_now(),
                    "name": backup_name,
                    "files": files,
                    "collections": collections,
                }
                zf.writestr(
                    _MANIFEST_NAME,
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                )
        return target
    except SWError:
        raise
    except Exception as e:
        # 清理半成品 zip
        if target.exists():
            try:
                target.unlink()
            except Exception:
                pass
        raise SWError(
            error_code=SW_BACKUP_500,
            message=f"备份失败: {e}",
        ) from e


def list_backups() -> list[dict]:
    """扫描 backups/ 目录, 返回 name / size / created_at / manifest 摘要列表。"""
    results: list[dict] = []
    if not BACKUP_DIR.exists():
        return results

    for p in sorted(BACKUP_DIR.glob("*.zip"), key=lambda x: x.name):
        item: dict = {
            "name": p.name,
            "size": p.stat().st_size,
            "created_at": None,
            "manifest": None,
        }
        manifest: dict | None = None
        try:
            with zipfile.ZipFile(p) as zf:
                raw = zf.read(_MANIFEST_NAME).decode("utf-8")
                manifest = json.loads(raw)
        except Exception as e:
            item["manifest"] = {"error": f"无法读取 manifest: {e}"}

        if manifest:
            item["created_at"] = manifest.get("created_at")
            item["manifest"] = {
                "version": manifest.get("version"),
                "collections": manifest.get("collections", {}),
                "files_count": len(manifest.get("files", [])),
            }

        if not item["created_at"]:
            item["created_at"] = datetime.fromtimestamp(
                p.stat().st_mtime, tz=UTC
            ).isoformat()
        results.append(item)

    return results


def _find_backup(name: str) -> Path | None:
    """按名称定位备份 zip(兼容省略 .zip 后缀)。"""
    if not name:
        return None
    candidate = BACKUP_DIR / name
    if candidate.is_file():
        return candidate
    if not name.lower().endswith(".zip"):
        candidate2 = BACKUP_DIR / (name + ".zip")
        if candidate2.is_file():
            return candidate2
    return None


def _open_backup_chroma(extract_dir: Path) -> dict[str, int]:
    """校验并打开解压后的 chroma_db, 返回 {collection_name: count}。"""
    chroma_dir = extract_dir / "chroma_db"
    if not chroma_dir.exists():
        sw_raise(SW_BACKUP_500, "备份损坏: 缺少 chroma_db/ 目录")
    try:
        client = chromadb.PersistentClient(
            path=str(chroma_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        return {col.name: col.count() for col in client.list_collections()}
    except Exception as e:
        sw_raise(SW_BACKUP_500, f"备份损坏: chroma_db 无法打开: {e}")


def _swap_dir(src: Path, dst: Path) -> None:
    """用 src 目录替换 dst 目录(先 copy 到 staging, 再 rename 交换, 失败回滚)。

    避免直接 rmtree(dst) 造成中途失败后无旧数据可恢复。
    """
    staging = dst.with_name(dst.name + f".staging-{uuid.uuid4().hex[:8]}")
    old = dst.with_name(dst.name + f".old-{uuid.uuid4().hex[:8]}")
    shutil.copytree(src, staging)
    if dst.exists():
        os.replace(dst, old)
    try:
        os.replace(staging, dst)
    except Exception:
        # 尽力还原旧目录
        if old.exists() and not dst.exists():
            try:
                os.replace(old, dst)
            except Exception:
                pass
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if old.exists():
        shutil.rmtree(old, ignore_errors=True)


def _restore_trees(extract_dir: Path) -> list[str]:
    """从解压目录覆盖还原 chroma_db / uploads / mastery.json, 返回已还原项。"""
    restored: list[str] = []
    chroma_src = extract_dir / "chroma_db"
    uploads_src = extract_dir / "uploads"
    mastery_src = extract_dir / _MASTERY_REL

    if chroma_src.exists():
        _swap_dir(chroma_src, CHROMA_DB_DIR)
        restored.append("chroma_db/")

    if uploads_src.exists():
        _swap_dir(uploads_src, UPLOAD_DIR)
        restored.append("uploads/")

    # 顶层 mastery.json 兜底覆盖到 chroma_db/mastery.json
    if mastery_src.exists():
        CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mastery_src, CHROMA_DB_DIR / _MASTERY_REL)
        if _MASTERY_REL not in restored:
            restored.append(_MASTERY_REL)

    return restored


def restore_backup(name: str, dry_run: bool = False) -> dict:
    """恢复备份。

    - ``dry_run=True``: 只校验完整性(manifest 存在、chroma_db 可打开), 不做任何修改,
      返回计划 ``{files, collection_count, collections, created_at}``。
    - 真实恢复: 先自动 ``create_backup(name="pre-restore-<ts>")`` 备份当前状态, 然后
      停机式覆盖还原 chroma_db / uploads / mastery.json; 任何一步失败用 pre-restore 备份回滚。
      返回 ``{restored, collection_count, collections, pre_restore}``。
    """
    backup_path = _find_backup(name)
    if backup_path is None:
        sw_raise(SW_BACKUP_404, f"备份不存在: {name}")

    with tempfile.TemporaryDirectory(prefix="swkb-restore-") as tmp:
        extract_dir = Path(tmp)
        with zipfile.ZipFile(backup_path) as zf:
            zf.extractall(extract_dir)

        manifest_path = extract_dir / _MANIFEST_NAME
        if not manifest_path.exists():
            sw_raise(SW_BACKUP_500, "备份损坏: 缺少 backup_manifest.json")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            sw_raise(SW_BACKUP_500, f"备份损坏: manifest 无法解析: {e}")

        collections = _open_backup_chroma(extract_dir)
        total_cards = sum(collections.values())
        with zipfile.ZipFile(backup_path) as zf:
            files = [n for n in zf.namelist() if n != _MANIFEST_NAME]

        if dry_run:
            return {
                "files": files,
                "collection_count": total_cards,
                "collections": collections,
                "created_at": manifest.get("created_at"),
            }

        # ── 真实恢复: 先自动备份当前状态 ──────────────
        pre_name = f"pre-restore-{_timestamp()}"
        try:
            create_backup(name=pre_name)
        except Exception as e:
            sw_raise(SW_BACKUP_500, f"恢复前自动备份失败: {e}")

        # ── 停机式覆盖还原, 失败回滚 ──────────────────
        try:
            restored = _restore_trees(extract_dir)
        except Exception as e:
            rollback_err = None
            rollback_tmp = None
            try:
                pre_path = _find_backup(pre_name)
                if pre_path is None:
                    rollback_err = "未找到 pre-restore 备份"
                else:
                    rollback_tmp = tempfile.mkdtemp(prefix="swkb-rollback-")
                    with zipfile.ZipFile(pre_path) as zf:
                        zf.extractall(rollback_tmp)
                    _restore_trees(Path(rollback_tmp))
            except Exception as rb_e:
                rollback_err = str(rb_e)
            finally:
                if rollback_tmp and Path(rollback_tmp).exists():
                    shutil.rmtree(rollback_tmp, ignore_errors=True)
            if rollback_err:
                sw_raise(
                    SW_BACKUP_500,
                    f"恢复失败且回滚失败: {e} | 回滚错误: {rollback_err}",
                )
            sw_raise(SW_BACKUP_500, f"恢复失败, 已回滚到恢复前状态: {e}")

        return {
            "restored": restored,
            "collection_count": total_cards,
            "collections": collections,
            "pre_restore": pre_name + ".zip",
            "note": "已恢复。若服务正在运行, 建议重启以重新加载 ChromaDB 客户端。",
        }
