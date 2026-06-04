"""ChromaDB 数据库操作 — 客户端初始化、CRUD、lifecycle。"""

import json
import logging
import shutil
import uuid
from datetime import datetime, timezone
from typing import Optional

import threading
import chromadb
from chromadb.config import Settings

from bobanana.config import (
    CHROMA_DB_DIR,
    CHROMA_COLLECTION_NAME,
    CHROMA_PERSIST_INTERVAL,
    CHROMA_DISK_STOP_MB,
    EMBEDDING_DIMENSION,
)
from bobanana.models import KnowledgeCard, CardCreate, CardUpdate

logger = logging.getLogger(__name__)


# ── ChromaDB 管理器 ──────────────────────────────────────

class DatabaseManager:
    """ChromaDB 生命周期管理 + 集合操作。"""

    def __init__(self):
        self._client: Optional[chromadb.Client] = None
        self._collection: Optional[chromadb.Collection] = None
        self._persist_interval = CHROMA_PERSIST_INTERVAL
        self._lock = threading.Lock()  # 序列化所有 ChromaDB 访问（线程安全）

    # ── Lifecycle ─────────────────────────────────────────

    async def startup(self) -> None:
        """阶段1: 启动 — 初始化客户端 + health check + 维度校验。"""
        logger.info("正在连接 ChromaDB ...")
        self._client = chromadb.PersistentClient(
            path=str(CHROMA_DB_DIR),
            settings=Settings(anonymized_telemetry=False),
        )

        # 获取或创建集合
        self._collection = self._client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        # Health check: 写入一条测试记录并删除
        await self._health_check()

        # 维度校验
        await self._validate_dimension()

        logger.info(
            "ChromaDB 就绪 | 持久化: %s | 集合: %s | 维度: %d",
            CHROMA_DB_DIR, CHROMA_COLLECTION_NAME, EMBEDDING_DIMENSION,
        )

    async def shutdown(self) -> None:
        """阶段3: 关闭 — 排空 + 显式 persist。"""
        logger.info("正在关闭 ChromaDB ...")
        if self._client:
            # persist() auto-flushes in chromadb >= 1.5
            logger.info("ChromaDB 持久化完成")
            self._client = None
            self._collection = None

    async def _health_check(self) -> None:
        """校验 ChromaDB 读写是否正常。"""
        if not self._collection:
            raise RuntimeError("ChromaDB 未初始化")
        try:
            test_id = f"health_check_{uuid.uuid4().hex[:8]}"
            self._collection.add(
                ids=[test_id],
                embeddings=[[0.0] * EMBEDDING_DIMENSION],
                metadatas=[{"_test": True}],
                documents=["health_check"],
            )
            self._collection.delete(ids=[test_id])
            logger.info("ChromaDB health check 通过")
        except Exception as e:
            logger.error("ChromaDB health check 失败: %s", e)
            raise

    async def _validate_dimension(self) -> None:
        """校验现有数据维度与配置是否一致。"""
        if not self._collection:
            return
        count = self._collection.count()
        if count == 0:
            return
        # 读第一条记录确认维度
        sample = self._collection.get(limit=1)
        if sample and sample.get("embeddings") and len(sample["embeddings"]) > 0:
            actual_dim = len(sample["embeddings"][0])
            if actual_dim != EMBEDDING_DIMENSION:
                logger.warning(
                    "向量维度不匹配! 配置=%d, 现有数据=%d. "
                    "请检查 EMBEDDING_DIMENSION 配置或重建 collection.",
                    EMBEDDING_DIMENSION, actual_dim,
                )

    async def check_disk_space(self) -> Optional[str]:
        """检查磁盘空间，不足时返回警告信息。"""
        try:
            usage = shutil.disk_usage(CHROMA_DB_DIR)
            free_mb = usage.free / (1024 * 1024)
            if free_mb < CHROMA_DISK_STOP_MB:
                return f"磁盘剩余 {free_mb:.0f}MB，低于停止阈值 {CHROMA_DISK_STOP_MB}MB"
            if free_mb < 100:
                logger.warning("磁盘剩余 %.0fMB", free_mb)
        except OSError:
            pass
        return None

    # ── 集合访问 ──────────────────────────────────────────

    @property
    def collection(self) -> chromadb.Collection:
        if self._collection is None:
            raise RuntimeError("ChromaDB 未初始化，请先调用 startup()")
        return self._collection

    @property
    def client(self) -> chromadb.Client:
        if self._client is None:
            raise RuntimeError("ChromaDB 未初始化，请先调用 startup()")
        return self._client

    # ── CRUD 操作 ─────────────────────────────────────────

    def add_card(self, card: KnowledgeCard, embedding: list[float]) -> str:
        """添加一张卡片到 ChromaDB。返回卡片 ID。"""
        card_id = card.id or str(uuid.uuid4())
        self.collection.add(
            ids=[card_id],
            embeddings=[embedding],
            metadatas=[{
                "title": card.title,
                "aliases": ",".join(card.aliases),
                "examples": json.dumps(card.examples, ensure_ascii=False),
                "questions": json.dumps(card.questions, ensure_ascii=False),
                "category": card.category,
                "source_file": card.source_file,
                "source_page": card.source_page,
                "related_cards": ",".join(card.related_cards),
                "created_at": card.created_at,
                "updated_at": card.updated_at,
            }],
            documents=[card.content],
        )
        return card_id

    def update_card(self, card_id: str, card: KnowledgeCard, embedding: list[float]) -> None:
        """更新卡片。"""
        card.updated_at = datetime.now(timezone.utc).isoformat()
        self.collection.update(
            ids=[card_id],
            embeddings=[embedding],
            metadatas=[{
                "title": card.title,
                "aliases": ",".join(card.aliases),
                "examples": json.dumps(card.examples, ensure_ascii=False),
                "questions": json.dumps(card.questions, ensure_ascii=False),
                "category": card.category,
                "source_file": card.source_file,
                "source_page": card.source_page,
                "related_cards": ",".join(card.related_cards),
                "created_at": card.created_at,
                "updated_at": card.updated_at,
            }],
            documents=[card.content],
        )

    def _update_related_cards(self, card_id: str, related_ids: list[str]) -> None:
        """只更新卡片的 related_cards 字段（关联检测专用，不重新嵌入）。"""
        # 读取完整元数据
        result = self.collection.get(ids=[card_id])
        if not result or not result.get("metadatas") or not result["metadatas"]:
            return
        meta = result["metadatas"][0]
        meta["related_cards"] = ",".join(related_ids)
        self.collection.update(
            ids=[card_id],
            metadatas=[meta],
        )

    def delete_card(self, card_id: str) -> None:
        """删除卡片。"""
        self.collection.delete(ids=[card_id])

    def get_card(self, card_id: str) -> Optional[KnowledgeCard]:
        """根据 ID 获取卡片。"""
        result = self.collection.get(ids=[card_id])
        if not result or not result.get("ids"):
            return None
        return self._result_to_card(result, 0)

    def list_cards(
        self, category: Optional[str] = None, page: int = 1, limit: int = 20
    ) -> tuple[list[KnowledgeCard], int]:
        """列出卡片，支持按分类过滤和分页。"""
        where = {"category": category} if category else None
        result = self.collection.get(where=where)
        if not result or not result.get("ids"):
            return [], 0

        total = len(result["ids"])
        # 手动分页
        start = (page - 1) * limit
        end = start + limit
        cards = []
        for i in range(start, min(end, total)):
            cards.append(self._result_to_card(result, i))
        return cards, total

    def search_cards(self, query_embedding: list[float], top_k: int = 10) -> list[tuple[KnowledgeCard, float]]:
        """向量相似度搜索。返回 (卡片, 相似度分数) 列表。"""
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )
        cards: list[tuple[KnowledgeCard, float]] = []
        if not result or not result.get("ids") or not result["ids"]:
            return cards

        for i in range(len(result["ids"][0])):
            card = self._result_to_card(result, i, is_query=True)
            distance = result["distances"][0][i] if result.get("distances") else 0.0
            score = 1.0 - distance  # 余弦距离转相似度
            cards.append((card, score))
        return cards

    def get_categories(self) -> list[str]:
        """获取所有分类。"""
        result = self.collection.get()
        if not result or not result.get("metadatas"):
            return []
        categories = set()
        for m in result["metadatas"]:
            if m and "category" in m:
                categories.add(m["category"])
        return sorted(categories)

    def count(self) -> int:
        """获取卡片总数。"""
        return self.collection.count()

    # ── 辅助方法 ──────────────────────────────────────────

    @staticmethod
    def _result_to_card(result: dict, index: int, is_query: bool = False) -> KnowledgeCard:
        """将 ChromaDB 查询结果转为 KnowledgeCard。"""
        ids = result["ids"]
        if is_query:
            ids = result["ids"][0]
        card_id = ids[index]

        metadatas = result["metadatas"]
        if is_query:
            metadatas = result["metadatas"][0]
        meta = metadatas[index] if metadatas else {}

        documents = result["documents"]
        if is_query:
            documents = result["documents"][0]
        content = documents[index] if documents else ""

        examples_raw = meta.get("examples", "[]")
        questions_raw = meta.get("questions", "[]")
        try:
            examples = json.loads(examples_raw) if isinstance(examples_raw, str) else examples_raw
        except (json.JSONDecodeError, TypeError):
            examples = []
        try:
            questions = json.loads(questions_raw) if isinstance(questions_raw, str) else questions_raw
        except (json.JSONDecodeError, TypeError):
            questions = []

        return KnowledgeCard(
            id=card_id,
            title=meta.get("title", ""),
            aliases=meta.get("aliases", "").split(",") if meta.get("aliases") else [],
            content=content,
            examples=examples,
            questions=questions,
            category=meta.get("category", "未分类"),
            source_file=meta.get("source_file", ""),
            source_page=int(meta.get("source_page", 0)),
            related_cards=meta.get("related_cards", "").split(",") if meta.get("related_cards") else [],
            created_at=meta.get("created_at", ""),
            updated_at=meta.get("updated_at", ""),
        )


# ── 全局单例 ─────────────────────────────────────────────

db_manager = DatabaseManager()
