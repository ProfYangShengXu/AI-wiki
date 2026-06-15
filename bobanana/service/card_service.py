"""CardService — 唯一写入入口，threading.Lock 序列化所有数据库变更。"""

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from bobanana.config import RETRIEVAL_TOP_K
from bobanana.database import db_manager
from bobanana.models import KnowledgeCard, CardCreate, CardUpdate, CardResponse, ImportResult
from bobanana.tools import embed_text

logger = logging.getLogger(__name__)


class CardService:
    """卡片服务层 — 封装所有 ChromaDB 写操作，提供写入隔离。

    读操作无锁，直接透传 database.py。
    写操作经 threading.Lock 序列化，跨线程/协程均有效。
    embedding 计算在锁外执行，避免 CPU 推理阻塞其他写请求。
    """

    def __init__(self):
        self._lock = threading.Lock()  # 跨线程锁，asyncio 和 sync 调用均生效
        self._pending_fails: list[dict] = []
        self._embedding_fn = embed_text

    # ── 嵌入计算（无锁，可并发） ─────────────────────────

    def _compute_embedding(self, text: str) -> list[float]:
        """计算向量嵌入 — 在锁外调用，避免阻塞。"""
        return self._embedding_fn(text)

    # ── 读操作（无锁） ─────────────────────────────────────

    async def get_card(self, card_id: str) -> Optional[KnowledgeCard]:
        return db_manager.get_card(card_id)

    async def list_cards(
        self, category: Optional[str] = None, page: int = 1, limit: int = 50
    ) -> tuple[list[KnowledgeCard], int]:
        return db_manager.list_cards(category, page, limit)

    async def search_cards(
        self, query: str, top_k: int = RETRIEVAL_TOP_K
    ) -> list[tuple[KnowledgeCard, float]]:
        embedding = self._compute_embedding(query)
        return db_manager.search_cards(embedding, top_k)

    async def get_categories(self) -> list[str]:
        return db_manager.get_categories()

    async def count(self) -> int:
        return db_manager.count()

    # ── 写操作（threading.Lock 序列化） ───────────────────

    async def create_card(self, data: CardCreate) -> KnowledgeCard:
        """创建卡片 — embedding 在锁外计算。"""
        now = datetime.now(timezone.utc).isoformat()
        card = KnowledgeCard(
            id=str(uuid.uuid4()),
            title=data.title,
            aliases=data.aliases or [],
            content=data.content,
            examples=data.examples or [],
            questions=data.questions or [],
            category=data.category or "未分类",
            source_file=data.source_file or "",
            source_page=data.source_page or 0,
            related_cards=data.related_cards or [],
            created_at=now,
            updated_at=now,
        )
        # 锁外计算 embedding
        embedding = self._compute_embedding(card.embedding_text())

        with self._lock:
            card.id = db_manager.add_card(card, embedding)
            logger.info("创建卡片: %s (%s)", card.id, card.title)
        # 关联检测在锁外执行，避免 threading.Lock + await 死锁
        await self._detect_and_link(card.id, card)
        return card

    async def update_card(self, card_id: str, data: CardUpdate) -> Optional[KnowledgeCard]:
        """更新卡片 — embedding 在锁外计算。"""
        existing = db_manager.get_card(card_id)
        if not existing:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(existing, field, value)
        existing.updated_at = datetime.now(timezone.utc).isoformat()

        # 锁外计算 embedding
        embedding = self._compute_embedding(existing.embedding_text())

        with self._lock:
            db_manager.update_card(card_id, existing, embedding)
            logger.info("更新卡片: %s", card_id)
        # 关联检测在锁外执行
        await self._detect_and_link(card_id, existing)
        return existing

    async def delete_card(self, card_id: str) -> bool:
        existing = db_manager.get_card(card_id)
        if not existing:
            return False
        with self._lock:
            db_manager.delete_card(card_id)
            logger.info("删除卡片: %s", card_id)
        return True

    async def batch_import(self, cards: list[CardCreate]) -> ImportResult:
        """批量导入 — 逐条独立事务，失败不影响已写入。"""
        # 锁外预计算所有 embedding
        prepared = []
        for data in cards:
            now = datetime.now(timezone.utc).isoformat()
            card = KnowledgeCard(
                id=str(uuid.uuid4()),
                title=data.title,
                aliases=data.aliases or [],
                content=data.content,
                examples=data.examples or [],
                questions=data.questions or [],
                category=data.category or "未分类",
                source_file=data.source_file or "",
                source_page=data.source_page or 0,
                related_cards=data.related_cards or [],
                created_at=now,
                updated_at=now,
            )
            embedding = self._compute_embedding(card.embedding_text())
            prepared.append((card, embedding))

        result = ImportResult(total=len(cards))
        # 先锁内批量写入
        with self._lock:
            for card, embedding in prepared:
                try:
                    card.id = db_manager.add_card(card, embedding)
                    result.success.append(card.model_dump())
                except Exception as e:
                    result.failed.append({"title": card.title, "reason": str(e)})
                    self._pending_fails.append({"title": card.title, "reason": str(e)})
        # 锁外统一做关联检测
        for card_resp in result.success:
            try:
                cid = card_resp.id if hasattr(card_resp, 'id') else ''
                if cid:
                    card = db_manager.get_card(cid)
                    if card:
                        await self._detect_and_link(cid, card)
            except Exception:
                pass
        logger.info("批量导入: %d 成功, %d 失败", len(result.success), len(result.failed))
        return result

    # ── 关联检测 ─────────────────────────────────────────

    async def _detect_and_link(self, card_id: str, card: KnowledgeCard) -> None:
        """扫描卡片内容，匹配已有卡片标题/别名，建立双向关联。"""
        search_text = (
            card.title + " " + " ".join(card.aliases) + " "
            + card.content + " " + " ".join(card.examples) + " "
            + " ".join(card.questions)
        ).lower()

        all_cards, total = db_manager.list_cards()
        if total == 0:
            return

        new_links = set(card.related_cards)
        for other in all_cards:
            if other.id == card_id:
                continue
            match_targets = [other.title.lower()] + [a.lower() for a in other.aliases]
            for target in match_targets:
                if target and len(target) >= 2 and target in search_text:
                    new_links.add(other.id)
                    other_related = set(other.related_cards)
                    if card_id not in other_related:
                        other_related.add(card_id)
                        db_manager._update_related_cards(other.id, list(other_related))
                    break

        if set(card.related_cards) != new_links:
            card.related_cards = list(new_links)
            embedding = self._compute_embedding(card.embedding_text())
            db_manager.update_card(card_id, card, embedding)
            logger.info("关联检测: %s → %d 个关联", card.title, len(new_links))

    # ── 同步方法 (供 Agent 线程调用) ─────────────────

    def create_card_sync(self, data: CardCreate) -> dict:
        """同步版创建 — 在新事件循环中执行，threading.Lock 跨循环生效。"""
        return asyncio.run(self.create_card(data)).model_dump()

    def batch_import_sync(self, cards: list[CardCreate]) -> ImportResult:
        """同步版批量导入。"""
        return asyncio.run(self.batch_import(cards))

    def list_cards_sync(self, category=None, page=1, limit=5000):
        """同步版列出卡片。"""
        return db_manager.list_cards(category, page, limit)

    def get_card_sync(self, card_id: str):
        return db_manager.get_card(card_id)

    def update_card_sync(self, card_id: str, data):
        card = db_manager.get_card(card_id)
        if not card: return None
        for f, v in data.model_dump(exclude_unset=True).items():
            setattr(card, f, v)
        embedding = self._compute_embedding(card.embedding_text())
        db_manager.update_card(card_id, card, embedding)
        return card

    def delete_card_sync(self, card_id: str):
        if not db_manager.get_card(card_id): return False
        db_manager.delete_card(card_id)
        return True

    def get_categories_sync(self):
        return db_manager.get_categories()

    def search_cards_sync(self, query: str, top_k: int = RETRIEVAL_TOP_K) -> list:
        """同步版搜索。"""
        embedding = self._compute_embedding(query)
        return db_manager.search_cards(embedding, top_k)

    # ── Lifecycle ─────────────────────────────────────────

    

# ── 全局单例 ─────────────────────────────────────────────

card_service = CardService()
