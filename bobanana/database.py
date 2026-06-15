"""ChromaDB 数据库操作 — 客户端初始化、CRUD、lifecycle。全部方法用 threading.Lock 序列化。"""

import json
import logging
import shutil
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

import chromadb
from chromadb.config import Settings

from bobanana.config import (
    CHROMA_DB_DIR, CHROMA_COLLECTION_NAME, CHROMA_PERSIST_INTERVAL,
    CHROMA_DISK_STOP_MB, EMBEDDING_DIMENSION,
)
from bobanana.models import KnowledgeCard

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self._client: Optional[chromadb.Client] = None
        self._collection: Optional[chromadb.Collection] = None
        self._lock = threading.Lock()

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
        logger.info("ChromaDB ready | %s | dim=%d", CHROMA_DB_DIR, EMBEDDING_DIMENSION)

    async def shutdown(self) -> None:
        logger.info("Shutting down ChromaDB ...")
        self._client = None
        self._collection = None

    async def _health_check(self) -> None:
        try:
            test_id = f"hc_{uuid.uuid4().hex[:8]}"
            self._collection.add(
                ids=[test_id],
                embeddings=[[0.0] * EMBEDDING_DIMENSION],
                metadatas=[{"_test": True}],
                documents=["health_check"],
            )
            self._collection.delete(ids=[test_id])
        except Exception as e:
            logger.error("Health check failed: %s", e)
            raise

    @property
    def client(self):
        if self._client is None:
            raise RuntimeError("ChromaDB 未初始化")
        return self._client

    async def _validate_dimension(self) -> None:
        count = self._collection.count()
        if count == 0: return
        sample = self._collection.get(limit=1)
        if sample and sample.get("embeddings"):
            actual = len(sample["embeddings"][0])
            if actual != EMBEDDING_DIMENSION:
                logger.warning("Dimension mismatch! config=%d, actual=%d", EMBEDDING_DIMENSION, actual)

    # ── CRUD (all locked) ─────────────────────────────────

    def add_card(self, card: KnowledgeCard, embedding: list[float]) -> str:
        cid = card.id or str(uuid.uuid4())
        with self._lock:
            self._collection.add(ids=[cid], embeddings=[embedding], metadatas=[_meta(card)], documents=[card.content])
        return cid

    def update_card(self, cid: str, card: KnowledgeCard, embedding: list[float]) -> None:
        card.updated_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._collection.update(ids=[cid], embeddings=[embedding], metadatas=[_meta(card)], documents=[card.content])

    def delete_card(self, cid: str) -> None:
        with self._lock:
            self._collection.delete(ids=[cid])

    def get_card(self, cid: str) -> Optional[KnowledgeCard]:
        with self._lock:
            result = self._collection.get(ids=[cid])
        return _to_card(result, 0) if result and result.get("ids") else None

    def list_cards(self, category: Optional[str] = None, page: int = 1, limit: int = 50) -> tuple[list[KnowledgeCard], int]:
        where = {"category": category} if category else None
        with self._lock:
            result = self._collection.get(where=where)
        if not result or not result.get("ids"):
            return [], 0
        total = len(result["ids"])
        start, end = (page-1)*limit, min(page*limit, total)
        return [_to_card(result, i) for i in range(start, end)], total

    def search_cards(self, query_embedding: list[float], top_k: int = 10) -> list[tuple[KnowledgeCard, float]]:
        with self._lock:
            result = self._collection.query(query_embeddings=[query_embedding], n_results=top_k)
        cards = []
        if result and result.get("ids") and result["ids"]:
            for i in range(len(result["ids"][0])):
                card = _to_card(result, i, is_query=True)
                dist = result["distances"][0][i] if result.get("distances") else 0.0
                cards.append((card, 1.0 - dist))
        return cards

    def get_categories(self) -> list[str]:
        with self._lock:
            result = self._collection.get()
        cats = set()
        for m in (result.get("metadatas") or []):
            if m and "category" in m:
                cats.add(m["category"])
        return sorted(cats)

    def count(self) -> int:
        with self._lock:
            return self._collection.count()

    def _update_related_cards(self, cid: str, related: list[str]) -> None:
        with self._lock:
            result = self._collection.get(ids=[cid])
        if result and result.get("metadatas"):
            meta = result["metadatas"][0]
            meta["related_cards"] = ",".join(related)
            with self._lock:
                self._collection.update(ids=[cid], metadatas=[meta])


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
        except: return []

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
        created_at=meta.get("created_at", ""),
        updated_at=meta.get("updated_at", ""),
    )


db_manager = DatabaseManager()
