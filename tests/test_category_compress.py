"""分类收敛 + 上下文压缩 的单元测试 (全 fake, 不触网)。"""

import asyncio

from tests.fakes import patch_embeddings, patch_llm

# ── 分类收敛 ─────────────────────────────────────────────

HISTORICAL_CATEGORIES = [
    'Agent基础', 'Agent工程', 'Agent教学', 'Agent架构', 'Agent框架', 'LLM基础', 'LLM工程',
    'MCP协议', 'RAG与知识检索', 'Workflow模式', '上下文管理', '多Agent', '多Agent系统',
    '学习方法', '安全与评估', '安全评估', '工具与交互', '工具与协议', '工具集成',
    '工程与架构', '性能优化', '技术栈', '推理优化', '架构设计', '框架', '框架与架构',
    '模型训练', '注意力机制', '源码阅读', '自更新', '记忆与上下文', '记忆与状态',
    '记忆系统', '软件架构', '面试技巧',
]


def test_normalize_maps_all_historical_to_canonical():
    from bobanana.agent import CANONICAL_CATEGORIES, normalize_category
    assert len(CANONICAL_CATEGORIES) == 7
    mapped = {normalize_category(c) for c in HISTORICAL_CATEGORIES}
    assert len(mapped) <= 7, f"应收敛到≤7个, 实际 {len(mapped)}: {mapped}"
    assert mapped <= set(CANONICAL_CATEGORIES)


def test_normalize_exact_and_unknown():
    from bobanana.agent import CANONICAL_CATEGORIES, normalize_category
    assert normalize_category(CANONICAL_CATEGORIES[0]) == CANONICAL_CATEGORIES[0]
    assert normalize_category("乱七八糟分类") == "通用"
    assert normalize_category("") == "通用"
    assert normalize_category(None) == "通用"


def test_create_card_keeps_manual_category(tmp_path, monkeypatch, isolated_chroma):
    """手动创建卡片保留用户指定分类(支持分类手动 CRUD)。"""
    patch_embeddings(monkeypatch)
    from bobanana.database import db_manager
    from bobanana.models import CardCreate
    from bobanana.service.card_service import card_service

    async def go():
        card = await card_service.create_card(
            CardCreate(title="测试", content="内容", category="自定义分类")
        )
        return card.category, db_manager.get_categories()

    category, cats = asyncio.run(go())
    assert category == "自定义分类"
    assert cats == ["自定义分类"]


def test_migrate_categories_normalizes_stored(tmp_path, monkeypatch, isolated_chroma):
    """存量卡片分类迁移: 脏分类 → 规范分类。"""
    patch_embeddings(monkeypatch)
    from bobanana.database import db_manager
    from bobanana.models import KnowledgeCard
    from bobanana.service.card_service import card_service

    db_manager.add_card(
        KnowledgeCard(title="旧卡", content="内容", category="LLM工程"), [0.1] * 384
    )
    db_manager.add_card(
        KnowledgeCard(title="规范卡", content="内容", category="工具与 MCP"), [0.1] * 384
    )
    assert card_service.migrate_categories() == 1  # 只有脏分类被迁移
    assert set(db_manager.get_categories()) == {"LLM 与模型", "工具与 MCP"}


# ── 上下文压缩 (前缀稳定) ────────────────────────────────

def test_compress_keeps_prefix_and_persists(tmp_path, monkeypatch):
    patch_embeddings(monkeypatch)
    patch_llm(monkeypatch, {"x": "压缩摘要"})
    from bobanana import memory
    from bobanana.routes.chat import (
        COMPRESS_PREFIX, COMPRESS_TAIL, _SUMMARY_TAG, _maybe_compress,
    )

    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "m.db")
    memory.init_db()

    hist = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"消息{i}"}
        for i in range(30)
    ]
    compressed = _maybe_compress("s1", hist)

    assert len(compressed) < len(hist)
    # 前缀逐条原文不变 (LLM 前缀缓存命中关键)
    assert compressed[:COMPRESS_PREFIX] == hist[:COMPRESS_PREFIX]
    # 尾部原文不变
    assert compressed[-COMPRESS_TAIL:] == hist[-COMPRESS_TAIL:]
    # 中间是摘要标记消息
    assert any(_SUMMARY_TAG in m.get("content", "") for m in compressed)
    # 压缩结果落盘
    assert memory.get_history("s1", limit=1000) == compressed


def test_compress_short_history_noop(tmp_path, monkeypatch):
    patch_llm(monkeypatch, {"x": "s"})
    from bobanana import memory
    from bobanana.routes.chat import _maybe_compress

    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "m.db")
    memory.init_db()
    hist = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    assert _maybe_compress("s2", hist) == hist


# ── 卡片排序 (文件导入时间 → 页码) ────────────────────────

def test_list_cards_sort_by_source(tmp_path, monkeypatch, isolated_chroma):
    """sort=source 时按 (文件导入时间, 页码) 排序。"""
    patch_embeddings(monkeypatch)
    from bobanana.database import db_manager
    from bobanana.models import KnowledgeCard
    from bobanana.service.card_service import card_service

    # 文件B 先导入但页码靠后; 文件A 后导入
    db_manager.add_card(
        KnowledgeCard(title="B1", content="b1", category="通用",
                      source_file="B.pdf", source_page=3), [0.1] * 384
    )
    db_manager.add_card(
        KnowledgeCard(title="B2", content="b2", category="通用",
                      source_file="B.pdf", source_page=1), [0.1] * 384
    )
    db_manager.add_card(
        KnowledgeCard(title="A1", content="a1", category="通用",
                      source_file="A.pdf", source_page=2), [0.1] * 384
    )
    db_manager.add_card(
        KnowledgeCard(title="A2", content="a2", category="通用",
                      source_file="A.pdf", source_page=1), [0.1] * 384
    )

    created, total = card_service.list_cards_sync(sort="created")
    assert total == 4
    assert [c.title for c in created] == ["B1", "B2", "A1", "A2"]  # 默认创建序

    sourced, total = card_service.list_cards_sync(sort="source")
    assert total == 4
    # 文件B 先导入 → B 的文件排前面, 组内按页码: B2(1) < B1(3); 然后 A: A2(1) < A1(2)
    assert [c.title for c in sourced] == ["B2", "B1", "A2", "A1"]


# ── 检索 embedding 失败回退 BM25 ─────────────────────────

def test_search_fallback_bm25_when_embedding_fails(tmp_path, monkeypatch, isolated_chroma):
    """embedding 计算失败时, ask 检索回退纯 BM25, 不返回空。"""
    patch_embeddings(monkeypatch)
    from bobanana.database import db_manager
    from bobanana.models import KnowledgeCard
    from bobanana.service.card_service import card_service

    db_manager.add_card(
        KnowledgeCard(title="提示链", content="将复杂任务拆解为固定顺序步骤的工作流模式",
                      category="通用"), [0.1] * 384
    )
    db_manager.add_card(
        KnowledgeCard(title="MCP协议", content="模型上下文协议, 工具调用", category="通用"),
        [0.1] * 384,
    )

    # 模拟 embedding 模型加载失败
    orig = card_service._compute_embedding
    def _boom(_text):
        raise RuntimeError("model load failed")
    card_service._compute_embedding = _boom
    try:
        cards = card_service.search_cards_sync("提示链", top_k=3)
    finally:
        card_service._compute_embedding = orig

    assert len(cards) >= 1, "embedding 失败时应有 BM25 回退结果"
    assert cards[0][0].title == "提示链"
