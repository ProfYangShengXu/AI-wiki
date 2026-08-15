"""导入任务状态机 — queued → scanning → extracting → linking → done / failed / cancelled。

职责:
- 任务生命周期管理 (create_task / cancel / resume / list_tasks),模块级单例 `import_task_manager`;
- 状态与进度持久化到 ``tmp/import_tasks/{task_id}/state.json`` (每次状态迁移写盘);
- LLM 调用速率控制: token bucket,默认 15 次 / 10s (常量在本文件,不读 config);
- 去重: 标题规范化 + 别名匹配 + 与既有卡片 embedding 余弦相似度阈值判定。

本模块不 import agent (仅在后台执行时惰性 import),避免循环依赖:
agent.py 顶层可安全 import 本模块的 TokenBucket / DedupIndex 等。
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
import uuid
from datetime import UTC, datetime

from bobanana.config import DATA_DIR
from bobanana.errors import SW_TASK_404, SW_UPLOAD_400, SWError

logger = logging.getLogger(__name__)

# ── 速率控制常量 (默认 15 次 / 10s,不读 config) ─────────────
TOKEN_BUCKET_CAPACITY = 15
TOKEN_BUCKET_WINDOW_SEC = 10.0

# ── 去重常量 ────────────────────────────────────────────────
DEDUP_SIMILARITY_THRESHOLD = 0.95

# ── 持久化目录: tmp/import_tasks/ ───────────────────────────
IMPORT_TASKS_DIR = DATA_DIR / "tmp" / "import_tasks"

# ── 状态机 ──────────────────────────────────────────────────
STATUS_QUEUED = "queued"
STATUS_SCANNING = "scanning"
STATUS_EXTRACTING = "extracting"
STATUS_LINKING = "linking"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

_TERMINAL = {STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED}
_RESUMABLE = {STATUS_FAILED, STATUS_CANCELLED}


def _record_terminal_metric(status: str) -> None:
    """终态迁移指标埋点 — 任何异常仅记日志, 不影响导入流程。"""
    if status not in _TERMINAL:
        return
    try:
        from bobanana.observability import metrics
        metrics.inc("import_tasks_total", labels={"status": status})
    except Exception as e:  # noqa: BLE001
        logger.debug("导入任务指标埋点失败: %s", e)


def utc_now_iso() -> str:
    """ISO8601 UTC 时间戳。"""
    return datetime.now(UTC).isoformat()


def normalize_title(title: str) -> str:
    """标题规范化: lower / strip / 去除标点与空白折叠。"""
    t = (title or "").lower().strip()
    t = re.sub(r"[\W_]+", "", t, flags=re.UNICODE)
    return t


def _cosine(a: list[float], b: list[float]) -> float:
    """向量余弦相似度。维度不一致时按较短维度计算。

    兼容 numpy 数组(chroma 返回)与普通 list;用 len() 判空,
    避免 numpy 数组真值歧义。
    """
    try:
        n = min(len(a), len(b))
    except TypeError:
        return 0.0
    if n == 0:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class TokenBucket:
    """简单 token bucket 限速器。

    突发容量 ``capacity``,每 ``window_sec`` 补充满一桶。
    ``acquire()`` 桶空时等待;传入 cancel_event 时响应取消并返回 False。
    """

    def __init__(
        self,
        capacity: int = TOKEN_BUCKET_CAPACITY,
        window_sec: float = TOKEN_BUCKET_WINDOW_SEC,
    ):
        self.capacity = float(capacity)
        self.window_sec = float(window_sec)
        self.refill_per_sec = self.capacity / self.window_sec
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, cancel_event: threading.Event | None = None) -> bool:
        """获取一个 token;桶空时等待。取消时返回 False。"""
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last
                self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_per_sec)
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                need = 1.0 - self._tokens
                wait = need / self.refill_per_sec
            # 分段休眠,便于及时响应取消
            time.sleep(min(wait, 0.2))
            if cancel_event is not None and cancel_event.is_set():
                return False


# 进程级共享限速器(所有导入任务共用)。
llm_token_bucket = TokenBucket()


class DedupIndex:
    """既有卡片去重索引。

    - titles / aliases: 归一化标题与别名集合;
    - embed_entries: 既有卡片的 embedding (经 ``load_embeddings`` 惰性加载)。

    ``check`` 返回 ``(is_duplicate, reason)``,重复项交由调用方记入 skipped,不静默丢弃。
    """

    def __init__(self, cards: list):
        self.titles: set[str] = set()
        self.aliases: set[str] = set()
        self.embed_entries: list[dict] = []
        for c in cards:
            t = normalize_title(getattr(c, "title", ""))
            if t:
                self.titles.add(t)
            for a in (getattr(c, "aliases", None) or []):
                na = normalize_title(a)
                if na:
                    self.aliases.add(na)

    def load_embeddings(self) -> None:
        """从当前 collection 读取既有卡片 embedding(懒加载,失败降级为仅标题/别名去重)。"""
        try:
            from bobanana.database import db_manager

            coll = db_manager.get_collection()
            if coll is None:
                return
            data = coll.get(include=["embeddings", "metadatas", "documents"])
            if not data or not data.get("ids"):
                return
            ids = data.get("ids") or []
            embs = data.get("embeddings")
            embs = [] if embs is None else embs
            metas = data.get("metadatas")
            metas = [] if metas is None else metas
            for i, _cid in enumerate(ids):
                emb = embs[i] if i < len(embs) else None
                meta = metas[i] if i < len(metas) else {}
                title = (meta or {}).get("title", "") if meta else ""
                # emb 可能是 numpy 数组,不能用 bool(emb) 判真(多元素数组会抛异常)。
                if emb is not None and len(emb) > 0:
                    self.embed_entries.append({"title": title, "embedding": emb})
        except Exception as e:  # noqa: BLE001
            logger.warning("去重索引 embedding 加载失败(降级为标题去重): %s", e)

    def check(self, title: str, aliases: list, embedding_text: str) -> tuple[bool, str]:
        """判断候选卡片是否与既有卡片重复。"""
        t = normalize_title(title)
        if t and t in self.titles:
            return True, "标题重复"
        for a in (aliases or []):
            na = normalize_title(a)
            if na and (na in self.titles or na in self.aliases):
                return True, "别名重复"

        if not self.embed_entries or not embedding_text:
            return False, ""

        emb: list[float] | None = None
        try:
            import bobanana.tools as tools

            emb = tools.embed_text(embedding_text)
        except Exception as e:  # noqa: BLE001
            logger.warning("去重嵌入计算失败(降级为标题去重): %s", e)
            return False, ""

        if not emb:
            return False, ""
        for entry in self.embed_entries:
            sim = _cosine(emb, entry["embedding"])
            if sim >= DEDUP_SIMILARITY_THRESHOLD:
                return True, f"与既有卡片语义相似(sim={sim:.3f})"
        return False, ""


class _Task:
    """单个导入任务的运行时状态。cancel_event 不持久化,仅内存。"""

    def __init__(self, task_id: str, file_path: str, filename: str,
                 kb_id: str = "", file_type: str = "course"):
        self.task_id = task_id
        self.file_path = file_path
        self.filename = filename
        self.kb_id = kb_id
        self.file_type = file_type
        self.cancel_event = threading.Event()
        self.created_at = utc_now_iso()
        self.updated_at = self.created_at
        self.status = STATUS_QUEUED
        self.message = "排队中..."
        self.progress: dict = {"stage": STATUS_QUEUED, "current": 0, "total": 0}
        self.result: dict = {"imported": 0, "skipped": 0, "failed": 0, "errors": []}
        self.checkpoints: dict = {}
        self.skip_ranges: set[int] = set()
        self._any_checkpoint = False

    def to_state(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "message": self.message,
            "progress": {
                "stage": self.progress.get("stage", self.status),
                "current": self.progress.get("current", 0),
                "total": self.progress.get("total", 0),
            },
            "result": {
                "imported": self.result.get("imported", 0),
                "skipped": self.result.get("skipped", 0),
                "failed": self.result.get("failed", 0),
                "errors": list(self.result.get("errors", [])),
            },
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "file_path": self.file_path,
            "filename": self.filename,
            "kb_id": self.kb_id,
            "file_type": self.file_type,
            "checkpoints": dict(self.checkpoints),
        }


class ImportTaskManager:
    """导入任务管理器 — 模块级单例。

    后台线程推进状态机,每次状态迁移把 state.json 原子写入
    ``tmp/import_tasks/{task_id}/state.json``。
    """

    def __init__(self):
        self._tasks: dict[str, _Task] = {}
        self._lock = threading.RLock()

    # ── 内部工具 ──────────────────────────────────────────

    def _task_dir(self, task_id: str):
        return IMPORT_TASKS_DIR / task_id

    def _state_file(self, task_id: str):
        return self._task_dir(task_id) / "state.json"

    def _save(self, task: _Task) -> None:
        """原子写 state.json(RLock 可重入,调用方可在锁内调用)。"""
        with self._lock:
            task.updated_at = utc_now_iso()
            d = self._task_dir(task.task_id)
            d.mkdir(parents=True, exist_ok=True)
            tmp = d / "state.json.tmp"
            tmp.write_text(
                json.dumps(task.to_state(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, self._state_file(task.task_id))
        # 终态迁移埋点 (done/failed/cancelled)
        _record_terminal_metric(task.status)

    def _load_state(self, task_id: str) -> dict | None:
        f = self._state_file(task_id)
        if not f.exists():
            return None
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            logger.warning("读取 state.json 失败: %s", f)
            return None

    def _task_from_state(self, state: dict) -> _Task:
        t = _Task(
            task_id=state.get("task_id", ""),
            file_path=state.get("file_path", ""),
            filename=state.get("filename", ""),
            kb_id=state.get("kb_id", ""),
            file_type=state.get("file_type", "course"),
        )
        t.status = state.get("status", STATUS_QUEUED)
        t.message = state.get("message", "")
        t.progress = dict(state.get("progress", {"stage": t.status, "current": 0, "total": 0}))
        t.result = state.get("result", {"imported": 0, "skipped": 0, "failed": 0, "errors": []})
        t.checkpoints = dict(state.get("checkpoints", {}))
        t.created_at = state.get("created_at", utc_now_iso())
        t.updated_at = state.get("updated_at", utc_now_iso())
        return t

    # ── 回调工厂 (供 agent.py 接线) ───────────────────────

    def _progress_cb(self, task: _Task):
        def cb(event: dict):
            if not isinstance(event, dict):
                return
            with self._lock:
                stage = event.get("stage")
                status = event.get("status")
                if stage == "parse":
                    task.progress["stage"] = STATUS_SCANNING
                    task.progress["current"] = event.get("current", task.progress.get("current", 0))
                    task.progress["total"] = event.get("total", task.progress.get("total", 0))
                elif stage == "scan":
                    task.progress["stage"] = STATUS_SCANNING
                    if status == "started":
                        task.status = STATUS_SCANNING
                        task.message = "解析文档中..."
                    elif status == "ok":
                        task.progress["total"] = event.get("total", task.progress.get("total", 0))
                elif stage == "extract":
                    task.progress["stage"] = STATUS_EXTRACTING
                    if status == "started":
                        task.status = STATUS_EXTRACTING
                        task.message = "提取知识点中..."
                        task.progress["total"] = event.get("total", task.progress.get("total", 0))
                    elif status == "ok":
                        task.progress["current"] = event.get("range", task.progress.get("current", 0))
                elif stage == "card_generate":
                    task.progress["stage"] = STATUS_LINKING
                    if status == "started":
                        task.status = STATUS_LINKING
                        task.message = "写入卡片并关联..."
                self._save(task)
        return cb

    def _checkpointer(self, task: _Task):
        def cp(info: dict):
            if not isinstance(info, dict):
                return
            with self._lock:
                r_idx = info.get("range_index")
                task._any_checkpoint = True
                task.checkpoints[str(r_idx)] = info
                task.result["imported"] = task.result.get("imported", 0) + int(info.get("imported", 0))
                task.result["skipped"] = task.result.get("skipped", 0) + int(info.get("skipped", 0))
                task.result["failed"] = task.result.get("failed", 0) + int(info.get("failed", 0))
                for err in (info.get("errors") or []):
                    if isinstance(err, dict):
                        task.result.setdefault("errors", []).append(err)
                if r_idx is not None:
                    task.progress["current"] = max(task.progress.get("current", 0), int(r_idx) + 1)
                task.progress["stage"] = STATUS_LINKING
                self._save(task)
        return cp

    # ── 后台执行 ──────────────────────────────────────────

    def _run(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return

        with self._lock:
            task.status = STATUS_SCANNING
            task.progress["stage"] = STATUS_SCANNING
            task.message = "解析文档中..."
            self._save(task)

        old_col = None
        try:
            from bobanana.config import CHROMA_COLLECTION_NAME
            from bobanana.database import db_manager

            old_col = db_manager.get_collection()
            if task.kb_id and task.kb_id != CHROMA_COLLECTION_NAME:
                try:
                    col = db_manager.client.get_or_create_collection(
                        name="kb_" + task.kb_id, metadata={"hnsw:space": "cosine"},
                    )
                    db_manager.switch_collection(col)
                except Exception:  # noqa: BLE001
                    pass

            from bobanana.agent import run_import_workflow, run_import_workflow_homework

            if task.file_type == "hw":
                result = run_import_workflow_homework(
                    file_path=task.file_path,
                    filename=task.filename,
                    progress_callback=self._progress_cb(task),
                    cancel_event=task.cancel_event,
                    checkpointer=self._checkpointer(task),
                )
                with self._lock:
                    task.result["imported"] = task.result.get("imported", 0) + len(result.success)
                    task.result["failed"] = task.result.get("failed", 0) + len(result.failed)
                    for f in result.failed:
                        task.result.setdefault("errors", []).append(
                            {"title": f.get("title", ""), "reason": f.get("reason", f.get("error", ""))}
                        )
                    task.status = STATUS_DONE
                    task.progress["stage"] = STATUS_DONE
                    task.message = (
                        f"成功 {task.result['imported']} 张, 跳过 {task.result['skipped']} 张, "
                        f"失败 {task.result['failed']} 张"
                    )
                    self._save(task)
            else:
                result = run_import_workflow(
                    file_path=task.file_path,
                    filename=task.filename,
                    progress_callback=self._progress_cb(task),
                    cancel_event=task.cancel_event,
                    checkpointer=self._checkpointer(task),
                    skip_ranges=task.skip_ranges,
                )
                with self._lock:
                    # 顶层异常(如扫描失败)未经过 checkpointer,这里兜底补记。
                    if not task._any_checkpoint and result.failed:
                        task.result["failed"] = task.result.get("failed", 0) + len(result.failed)
                        for f in result.failed:
                            task.result.setdefault("errors", []).append(
                                {"title": f.get("title", ""), "reason": f.get("reason", "")}
                            )
                        task.status = STATUS_FAILED
                        task.progress["stage"] = STATUS_FAILED
                        task.message = f"导入失败: {result.failed[0].get('reason', '')}"
                    elif task.cancel_event.is_set() and \
                            task.progress.get("current", 0) < task.progress.get("total", 0):
                        task.status = STATUS_CANCELLED
                        task.progress["stage"] = STATUS_CANCELLED
                        task.message = "任务已取消"
                    else:
                        task.status = STATUS_DONE
                        task.progress["stage"] = STATUS_DONE
                        task.message = (
                            f"成功 {task.result['imported']} 张, 跳过 {task.result['skipped']} 张, "
                            f"失败 {task.result['failed']} 张"
                        )
                    self._save(task)
        except Exception as e:  # noqa: BLE001
            logger.error("导入任务失败: %s", e, exc_info=True)
            with self._lock:
                task.status = STATUS_FAILED
                task.progress["stage"] = STATUS_FAILED
                task.message = str(e)
                task.result["failed"] = max(task.result.get("failed", 0), 1)
                task.result.setdefault("errors", []).append({"title": "", "reason": str(e)})
                self._save(task)
        finally:
            if old_col is not None:
                try:
                    db_manager.switch_collection(old_col)
                except Exception:  # noqa: BLE001
                    pass

    def _start_thread(self, task: _Task) -> None:
        t = threading.Thread(target=self._run, args=(task.task_id,), daemon=True,
                             name=f"import-{task.task_id}")
        t.start()

    # ── 对外接口 ──────────────────────────────────────────

    def create_task(self, file_path: str, filename: str, kb_id: str = "",
                    file_type: str = "course") -> str:
        task_id = uuid.uuid4().hex[:12]
        task = _Task(task_id, file_path, filename, kb_id=kb_id, file_type=file_type)
        with self._lock:
            self._tasks[task_id] = task
            self._save(task)
        return task_id

    def start(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise SWError(SW_TASK_404, "任务不存在", status_code=404)
            self._start_thread(task)

    def cancel(self, task_id: str) -> dict:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                state = self._load_state(task_id)
                if state is None:
                    raise SWError(SW_TASK_404, "任务不存在", status_code=404)
                task = self._task_from_state(state)
                self._tasks[task_id] = task
            if task.status in _TERMINAL:
                return task.to_state()
            task.cancel_event.set()
            task.message = "取消中..."
            self._save(task)
            return task.to_state()

    def resume(self, task_id: str) -> dict:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                state = self._load_state(task_id)
                if state is None:
                    raise SWError(SW_TASK_404, "任务不存在", status_code=404)
                task = self._task_from_state(state)
                self._tasks[task_id] = task

            if task.status not in _RESUMABLE:
                raise SWError(
                    SW_UPLOAD_400,
                    f"任务状态为 {task.status},仅 failed/cancelled 可恢复",
                    status_code=400,
                )
            if not self._state_file(task_id).exists():
                raise SWError(SW_TASK_404, "任务状态文件不存在,无法恢复", status_code=404)

            # 已完成区间来自 checkpoints (status=done),续跑跳过它们。
            skip: set[int] = set()
            for k, v in task.checkpoints.items():
                if isinstance(v, dict) and v.get("status") == "done":
                    try:
                        skip.add(int(k))
                    except (TypeError, ValueError):
                        pass
            task.skip_ranges = skip
            task.cancel_event = threading.Event()
            task.status = STATUS_QUEUED
            task.message = "恢复中..."
            task.progress = {
                "stage": STATUS_QUEUED,
                "current": len(skip),
                "total": task.progress.get("total", 0),
            }
            task._any_checkpoint = False
            self._save(task)
            self._start_thread(task)
            return task.to_state()

    def get_task(self, task_id: str) -> dict | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                return task.to_state()
        return self._load_state(task_id)

    def list_tasks(self) -> list[dict]:
        """任务列表: 内存中的活动任务 + 磁盘扫描的持久化任务(去重)。"""
        seen: set[str] = set()
        out: list[dict] = []
        with self._lock:
            for task in self._tasks.values():
                seen.add(task.task_id)
                out.append(task.to_state())
        if IMPORT_TASKS_DIR.exists():
            for child in sorted(IMPORT_TASKS_DIR.iterdir()):
                if not child.is_dir():
                    continue
                state = self._load_state(child.name)
                if state and state.get("task_id") not in seen:
                    out.append(state)
        return out


# ── 模块级单例 ────────────────────────────────────────────
import_task_manager = ImportTaskManager()
