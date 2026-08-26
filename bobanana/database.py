"""ChromaDB 数据库操作 — 客户端初始化、CRUD、lifecycle。全部方法用 threading.Lock 序列化。"""

import json
import logging
import shutil
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

import chromadb
from chromadb.config import Settings

from bobanana.config import (
    CHROMA_COLLECTION_NAME,
    CHROMA_DB_DIR,
    CHROMA_DISK_STOP_MB,
    CHROMA_DISK_WARN_MB,
    CHROMA_PERSIST_INTERVAL,
    EMBEDDING_DIMENSION,
)
from bobanana.errors import SW_DB_507, SWError, sw_raise
from bobanana.models import KnowledgeCard
from bobanana.retrieval import HybridRetriever

logger = logging.getLogger(__name__)

# ── 失败写入队列重试参数 ──────────────────────────────
_RETRY_INTERVAL_SEC = 300   # 5 分钟
_RETRY_MAX_ATTEMPTS = 3


class DatabaseManager:
    def __init__(self):
        self._client: chromadb.Client | None = None
        self._collection: chromadb.Collection | None = None
        self._lock = threading.Lock()
        self._collection_lock = threading.Lock()
        # ── 生命周期后台线程状态 ─────────────────────
        self._stop_event = threading.Event()
        self._retry_stop_event = threading.Event()
        self._persist_thread: threading.Thread | None = None
        self._retry_thread: threading.Thread | None = None
        # ── 失败写入队列 ─────────────────────────────
        self._pending_fails: list[dict] = []
        self._fails_lock = threading.Lock()

    def switch_collection(self, col):
        with self._collection_lock:
            self._collection = col

    def get_collection(self):
        """线程安全地获取当前 collection 引用。"""
        with self._collection_lock:
            return self._collection

    def _require_collection(self) -> Any:
        """返回已初始化的 collection 引用;未初始化时抛 RuntimeError。

        ``startup`` 完成后 ``_collection`` 必然非空,CRUD/检索仅在启动后调用;
        此处显式判空用于类型收窄并避免空引用静默传播。
        """
        collection = self._collection
        if collection is None:
            raise RuntimeError("ChromaDB 未初始化")
        return collection

    def switch_collection_safe(self, col):
        """切换 collection 并返回旧的 collection。原子操作。"""
        with self._collection_lock:
            old = self._collection
            self._collection = col
            return old

    # ── Lifecycle ─────────────────────────────────────────

    async def startup(self) -> None:
        logger.info("Connecting ChromaDB ...")
        self._client = chromadb.PersistentClient(
            path=str(CHROMA_DB_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        await self._health_check()
        await self._validate_dimension()

        # ── 启动后台线程(daemon) ─────────────────────
        self._stop_event = threading.Event()
        self._persist_thread = threading.Thread(
            target=self._persist_loop, name="swkb-persist", daemon=True,
        )
        self._persist_thread.start()

        self._retry_stop_event = threading.Event()
        self._retry_thread = threading.Thread(
            target=self._retry_loop, name="swkb-retry", daemon=True,
        )
        self._retry_thread.start()

        logger.info("ChromaDB ready | %s | dim=%d", CHROMA_DB_DIR, EMBEDDING_DIMENSION)

    async def shutdown(self) -> None:
        """幂等关闭: 停后台线程、join、最后显式 persist 并 flush 失败队列。"""
        if self._client is None and self._collection is None:
            return  # 已经关闭或从未启动
        logger.info("Shutting down ChromaDB ...")
        self._stop_event.set()
        self._retry_stop_event.set()
        for t in (self._persist_thread, self._retry_thread):
            if t is not None and t.is_alive():
                t.join(timeout=5)
        # 关闭前最后一次 persist + flush 失败写入队列
        self._try_persist()
        self._retry_pending_fails()
        self._client = None
        self._collection = None

    async def _health_check(self) -> None:
        collection = self._require_collection()
        try:
            test_id = f"hc_{uuid.uuid4().hex[:8]}"
            collection.add(
                ids=[test_id],
                embeddings=[[0.0] * EMBEDDING_DIMENSION],
                metadatas=[{"_test": True}],
                documents=["health_check"],
            )
            collection.delete(ids=[test_id])
        except Exception as e:
            logger.error("Health check failed: %s", e)
            raise

    @property
    def client(self):
        if self._client is None:
            raise RuntimeError("ChromaDB 未初始化")
        return self._client

    async def _validate_dimension(self) -> None:
        collection = self._require_collection()
        count = collection.count()
        if count == 0: return
        sample = collection.get(limit=1)
        if sample and sample.get("embeddings"):
            actual = len(sample["embeddings"][0])
            if actual != EMBEDDING_DIMENSION:
                logger.warning("Dimension mismatch! config=%d, actual=%d", EMBEDDING_DIMENSION, actual)

    # ── 磁盘水位 / 持久化 / 失败重试 ───────────────────────

    def _check_disk_space(self) -> None:
        """写入前检查 CHROMA_DB_DIR 所在分区剩余空间。

        - 剩余 < CHROMA_DISK_WARN_MB: 记 warning 日志(仍允许写入);
        - 剩余 < CHROMA_DISK_STOP_MB: 拒绝写入并抛 SWError(SW-DB-507)。
        检查失败(如路径暂不可用)仅记日志, 不阻断写入, 避免单机场景误伤。
        """
        try:
            usage = shutil.disk_usage(CHROMA_DB_DIR)
            free_mb = usage.free // (1024 * 1024)
        except Exception as e:
            logger.warning("磁盘空间检查失败, 跳过: %s", e)
            return
        if free_mb < CHROMA_DISK_STOP_MB:
            sw_raise(
                SW_DB_507,
                f"磁盘剩余空间不足: {free_mb}MB < {CHROMA_DISK_STOP_MB}MB, 拒绝写入",
            )
        if free_mb < CHROMA_DISK_WARN_MB:
            logger.warning(
                "磁盘剩余空间偏低: %dMB < %dMB(阈值 CHROMA_DISK_WARN_MB)",
                free_mb, CHROMA_DISK_WARN_MB,
            )

    def _try_persist(self) -> None:
        """对 collection 做健康检查 + persist 尝试(异常记日志, 不抛出)。

        注: chromadb 0.5+ (rust 后端) 自动持久化, 无显式 ``persist()`` 方法;
        这里以 ``heartbeat()`` 作为持久化探针; 若版本提供 ``persist`` 则调用之。
        """
        try:
            col = self.get_collection()
            if col is not None:
                col.count()  # 健康检查: 确认 collection 可用
            client = self._client
            persist = getattr(client, "persist", None)
            if callable(persist):
                persist()
            else:
                heartbeat = getattr(client, "heartbeat", None)
                if callable(heartbeat):
                    heartbeat()
        except Exception as e:
            logger.warning("持久化/健康检查失败: %s", e)

    def _persist_loop(self) -> None:
        """后台线程: 每 CHROMA_PERSIST_INTERVAL 秒做一次健康检查 + persist 尝试。"""
        while not self._stop_event.wait(CHROMA_PERSIST_INTERVAL):
            self._try_persist()

    def _enqueue_failed_write(
        self, cid: str, card: KnowledgeCard, embedding: list[float], error: Exception,
    ) -> None:
        """把失败的写入入队, 供后台线程重试。"""
        with self._fails_lock:
            self._pending_fails.append(
                {
                    "cid": cid,
                    "card": card,
                    "embedding": embedding,
                    "attempts": 0,
                    "error": str(error),
                }
            )

    def _retry_loop(self) -> None:
        """后台线程: 每 _RETRY_INTERVAL_SEC 秒重试失败写入队列。"""
        while not self._retry_stop_event.wait(_RETRY_INTERVAL_SEC):
            self._retry_pending_fails()

    def _retry_pending_fails(self) -> None:
        """重试失败写入队列: 成功移除, 失败记录 attempts, 耗尽(>=3 次)记 error 日志并放弃。"""
        if self._collection is None:
            return
        with self._fails_lock:
            items = list(self._pending_fails)
        remaining: list[dict] = []
        for item in items:
            if item["attempts"] >= _RETRY_MAX_ATTEMPTS:
                logger.error(
                    "失败写入重试耗尽(%d 次), 放弃: cid=%s error=%s",
                    item["attempts"], item.get("cid"), item.get("error"),
                )
                continue
            item["attempts"] += 1
            try:
                card = item["card"]
                with self._lock:
                    self._collection.add(
                        ids=[item["cid"]],
                        embeddings=[item["embedding"]],
                        metadatas=[_meta(card)],
                        documents=[card.content],
                    )
                logger.info("失败写入重试成功: cid=%s (第 %d 次)", item["cid"], item["attempts"])
            except Exception as e:
                item["error"] = str(e)
                if item["attempts"] >= _RETRY_MAX_ATTEMPTS:
                    logger.error(
                        "失败写入重试耗尽(%d 次), 放弃: cid=%s error=%s",
                        item["attempts"], item["cid"], e,
                    )
                else:
                    remaining.append(item)
                    logger.warning(
                        "失败写入第 %d 次重试失败: cid=%s error=%s",
                        item["attempts"], item["cid"], e,
                    )
        with self._fails_lock:
            self._pending_fails = remaining

    # ── CRUD (all locked) ─────────────────────────────────

    def add_card(self, card: KnowledgeCard, embedding: list[float]) -> str:
        self._check_disk_space()
        collection = self._require_collection()
        cid = card.id or str(uuid.uuid4())
        try:
            with self._lock:
                collection.add(
                    ids=[cid], embeddings=[embedding],
                    metadatas=[_meta(card)], documents=[card.content],
                )
        except SWError:
            raise
        except Exception as e:
            # 瞬时失败(如维度不匹配/锁冲突)入队, 后台线程重试
            self._enqueue_failed_write(cid, card, embedding, e)
            logger.error("add_card 失败, 已入队重试: cid=%s error=%s", cid, e)
            raise
        return cid

    def update_card(self, cid: str, card: KnowledgeCard, embedding: list[float]) -> None:
        self._check_disk_space()
        card.updated_at = datetime.now(UTC).isoformat()
        collection = self._require_collection()
        with self._lock:
            collection.update(
                ids=[cid], embeddings=[embedding],
                metadatas=[_meta(card)], documents=[card.content],
            )

    def delete_card(self, cid: str) -> None:
        collection = self._require_collection()
        with self._lock:
            collection.delete(ids=[cid])

    def get_card(self, cid: str) -> KnowledgeCard | None:
        collection = self._require_collection()
        with self._lock:
            result = collection.get(ids=[cid])
        return _to_card(result, 0) if result and result.get("ids") else None

    def list_cards(
        self, category: str | None = None, page: int = 1, limit: int = 50,
        sort: str = "created",
    ) -> tuple[list[KnowledgeCard], int]:
        """列出卡片, 支持排序:
        - sort="created": 按创建时间正序 (ChromaDB 返回序, 兼容旧行为)
        - sort="source":  按「文件导入时间 → 页码」排 (同一文件按页码连续排列)
        """
        where = {"category": category} if category else None
        collection = self._require_collection()
        with self._lock:
            result = collection.get(where=where)
        if not result or not result.get("ids"):
            return [], 0
        total = len(result["ids"])

        if sort == "source":
            # 每个 source_file 的导入时间 = 该文件最早卡片的 created_at
            cards = [_to_card(result, i) for i in range(total)]
            file_order: dict[str, str] = {}
            for c in cards:
                if c.source_file and (
                    c.source_file not in file_order
                    or c.created_at < file_order[c.source_file]
                ):
                    file_order[c.source_file] = c.created_at
            cards.sort(
                key=lambda c: (
                    file_order.get(c.source_file, ""),
                    c.source_page or 0,
                    c.created_at,
                )
            )
        else:
            cards = [_to_card(result, i) for i in range(total)]

        start, end = (page-1)*limit, min(page*limit, total)
        return cards[start:end], total

    def search_cards(
        self, query_embedding: list[float], top_k: int = 10,
    ) -> list[tuple[KnowledgeCard, float]]:
        """纯向量检索(旧接口,保持兼容):query_embedding 为向量,走 ChromaDB 余弦查询。"""
        with self._lock:
            result = self._require_collection().query(query_embeddings=[query_embedding], n_results=top_k)
        cards = []
        if result and result.get("ids") and result["ids"]:
            for i in range(len(result["ids"][0])):
                card = _to_card(result, i, is_query=True)
                dist = result["distances"][0][i] if result.get("distances") else 0.0
                cards.append((card, 1.0 - dist))
        return cards

    def hybrid_search(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int = 10,
        **filters,
    ) -> list[tuple[KnowledgeCard, float]]:
        """混合检索(BM25 + 向量余弦 + RRF 融合)。

        内部 collection.get(include=["documents","metadatas","embeddings"]) 拉全量文档
        重建索引;卡片量为个人级(<1 万),全量重建 BM25 索引与向量打分可接受。

        支持过滤:filters 中的 category / source_file / min_mastery(在候选取出后过滤),
        以及 enable_rewrite / llm_invoke(查询改写,默认关闭)。
        返回 [(KnowledgeCard, rrf_score)]。
        """
        with self._lock:
            result = self._require_collection().get(include=["documents", "metadatas", "embeddings"])
        if not result or not result.get("ids"):
            return []

        ids = result["ids"]
        metas = result.get("metadatas")
        if metas is None:
            metas = []
        docs = result.get("documents")
        if docs is None:
            docs = []
        # 注意:embeddings 可能是 numpy 数组,不能用 `or []` 判空(歧义真值)
        embs = result.get("embeddings")
        if embs is None:
            embs = []
        n = len(ids)

        titles = [(metas[i].get("title", "") if i < len(metas) and metas[i] else "") for i in range(n)]
        aliases = []
        for i in range(n):
            raw = (metas[i].get("aliases", "") if i < len(metas) and metas[i] else "") or ""
            aliases.append([a.strip() for a in raw.split(",") if a.strip()])

        enable_rewrite = bool(filters.pop("enable_rewrite", False))
        llm_invoke = filters.pop("llm_invoke", None)

        retriever = HybridRetriever()
        retriever.build(ids, titles, docs, embs, aliases=aliases, metadatas=metas)
        hits = retriever.search(
            query,
            query_embedding,
            top_k,
            category=filters.get("category"),
            source_file=filters.get("source_file"),
            min_mastery=filters.get("min_mastery"),
            enable_rewrite=enable_rewrite,
            llm_invoke=llm_invoke,
        )

        idx_map = {cid: i for i, cid in enumerate(ids)}
        cards: list[tuple[KnowledgeCard, float]] = []
        for card_id, score, _rank_info in hits:
            pos = idx_map.get(card_id)
            if pos is None:
                continue
            cards.append((_to_card(result, pos), score))
        return cards

    def get_categories(self) -> list[str]:
        collection = self._require_collection()
        with self._lock:
            result = collection.get()
        cats = set()
        for m in (result.get("metadatas") or []):
            if m and "category" in m:
                cats.add(m["category"])
        return sorted(cats)

    def rename_category(self, old_name: str, new_name: str) -> int:
        """重命名分类: 把所有 old_name 卡片的 category 改为 new_name。返回改动数。"""
        collection = self._require_collection()
        with self._lock:
            result = collection.get()
        if not result or not result.get("ids"):
            return 0
        ids = result["ids"]
        metas = result.get("metadatas") or []
        changed = 0
        for i, cid in enumerate(ids):
            m = metas[i] if i < len(metas) and metas[i] else None
            if m and m.get("category") == old_name:
                m["category"] = new_name
                with self._lock:
                    collection.update(ids=[cid], metadatas=[m])
                changed += 1
        return changed

    def delete_category(self, category: str, fallback: str = "通用") -> int:
        """删除分类: 把该分类下所有卡片的 category 改为 fallback。返回改动数。"""
        collection = self._require_collection()
        with self._lock:
            result = collection.get()
        if not result or not result.get("ids"):
            return 0
        ids = result["ids"]
        metas = result.get("metadatas") or []
        changed = 0
        for i, cid in enumerate(ids):
            m = metas[i] if i < len(metas) and metas[i] else None
            if m and m.get("category") == category:
                m["category"] = fallback
                with self._lock:
                    collection.update(ids=[cid], metadatas=[m])
                changed += 1
        return changed

    def count(self) -> int:
        collection = self._require_collection()
        with self._lock:
            return collection.count()

    def _update_related_cards(self, cid: str, related: list[str]) -> None:
        collection = self._require_collection()
        with self._lock:
            result = collection.get(ids=[cid])
        if result and result.get("metadatas"):
            meta = result["metadatas"][0]
            meta["related_cards"] = ",".join(related)
            with self._lock:
                collection.update(ids=[cid], metadatas=[meta])

    def update_mastery_metadata(self, cid: str, attempts: int, score: int) -> None:
        """更新卡片的掌握度元数据（无需 embedding）。"""
        collection = self._require_collection()
        with self._lock:
            result = collection.get(ids=[cid])
        if result and result.get("metadatas"):
            meta = result["metadatas"][0]
            meta["mastery_attempts"] = str(attempts)
            meta["mastery_score"] = str(score)
            with self._lock:
                collection.update(ids=[cid], metadatas=[meta])


# ── Helpers ──────────────────────────────────────────────

def _meta(card: KnowledgeCard) -> dict:
    return {
        "title": card.title,
        "aliases": ",".join(card.aliases),
        "examples": json.dumps(card.examples, ensure_ascii=False),
        "questions": json.dumps(card.questions, ensure_ascii=False),
        "category": card.category,
        "source_file": card.source_file,
        "source_page": card.source_page,
        "related_cards": ",".join(card.related_cards),
        "mastery_attempts": str(card.mastery_attempts),
        "mastery_score": str(card.mastery_score),
        "created_at": card.created_at,
        "updated_at": card.updated_at,
    }


def _to_card(result: dict, index: int, is_query: bool = False) -> KnowledgeCard:
    ids = result["ids"] if not is_query else result["ids"][0]
    cid = ids[index]
    metas = result["metadatas"] if not is_query else result["metadatas"][0]
    docs = result["documents"] if not is_query else result["documents"][0]
    meta = metas[index] if metas else {}
    content = docs[index] if docs else ""

    def _parse_list(raw: str) -> list:
        try: return json.loads(raw) if isinstance(raw, str) else raw
        except Exception: return []

    return KnowledgeCard(
        id=cid,
        title=meta.get("title", ""),
        aliases=meta.get("aliases", "").split(",") if meta.get("aliases") else [],
        content=content,
        examples=_parse_list(meta.get("examples", "[]")),
        questions=_parse_list(meta.get("questions", "[]")),
        category=meta.get("category", "未分类"),
        source_file=meta.get("source_file", ""),
        source_page=int(meta.get("source_page", 0)),
        related_cards=meta.get("related_cards", "").split(",") if meta.get("related_cards") else [],
        mastery_attempts=int(meta.get("mastery_attempts", 0)),
        mastery_score=int(meta.get("mastery_score", 0)),
        created_at=meta.get("created_at", ""),
        updated_at=meta.get("updated_at", ""),
    )


db_manager = DatabaseManager()
