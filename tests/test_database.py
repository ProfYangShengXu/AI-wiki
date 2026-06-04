"""数据库 + 服务层集成测试（使用真实 ChromaDB 实例）。"""

import chromadb
import pytest

from bobanana.config import CHROMA_DB_DIR
from bobanana.database import db_manager
from bobanana.service.card_service import card_service
from bobanana.models import CardCreate, CardUpdate

# 测试集合名
TEST_COLLECTION = "test_p4_cards"


@pytest.fixture(autouse=True)
def setup_test_env():
    """初始化 ChromaDB + 创建测试集合。"""
    # 若未初始化，直接创建客户端
    if db_manager._client is None:
        db_manager._client = chromadb.PersistentClient(
            path=str(CHROMA_DB_DIR),
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
    # 清理旧测试集合
    try:
        db_manager._client.delete_collection(TEST_COLLECTION)
    except Exception:
        pass
    # 创建测试集合
    test_col = db_manager._client.create_collection(
        name=TEST_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )
    old_col = db_manager._collection
    db_manager._collection = test_col
    yield
    db_manager._collection = old_col
    try:
        db_manager._client.delete_collection(TEST_COLLECTION)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_create_and_get_card():
    """创建卡片 → 读取卡片。"""
    data = CardCreate(title="测试卡片", content="测试内容", category="测试分类")
    card = await card_service.create_card(data)
    assert card.id is not None
    assert card.title == "测试卡片"

    fetched = await card_service.get_card(card.id)
    assert fetched is not None
    assert fetched.title == "测试卡片"
    assert fetched.content == "测试内容"


@pytest.mark.asyncio
async def test_update_card():
    """更新卡片。"""
    card = await card_service.create_card(CardCreate(title="原标题"))
    updated = await card_service.update_card(card.id, CardUpdate(title="新标题"))
    assert updated is not None
    assert updated.title == "新标题"

    fetched = await card_service.get_card(card.id)
    assert fetched.title == "新标题"


@pytest.mark.asyncio
async def test_delete_card():
    """删除卡片。"""
    card = await card_service.create_card(CardCreate(title="待删除"))
    assert await card_service.get_card(card.id) is not None
    deleted = await card_service.delete_card(card.id)
    assert deleted is True
    assert await card_service.get_card(card.id) is None


@pytest.mark.asyncio
async def test_delete_nonexistent():
    """删除不存在的卡片。"""
    result = await card_service.delete_card("nonexistent-id")
    assert result is False


@pytest.mark.asyncio
async def test_update_nonexistent():
    """更新不存在的卡片。"""
    result = await card_service.update_card("nonexistent-id", CardUpdate(title="新"))
    assert result is None


@pytest.mark.asyncio
async def test_list_cards_empty():
    """空列表。"""
    cards, total = await card_service.list_cards()
    assert total == 0
    assert cards == []


@pytest.mark.asyncio
async def test_list_cards_with_data():
    """列表含分页。"""
    for i in range(5):
        await card_service.create_card(CardCreate(title=f"卡片{i}", category="A" if i % 2 == 0 else "B"))

    cards, total = await card_service.list_cards(page=1, limit=3)
    assert total == 5
    assert len(cards) == 3

    cards_a, total_a = await card_service.list_cards(category="A")
    assert total_a == 3


@pytest.mark.asyncio
async def test_get_categories():
    """分类聚合。"""
    await card_service.create_card(CardCreate(title="A1", category="X"))
    await card_service.create_card(CardCreate(title="B1", category="Y"))
    await card_service.create_card(CardCreate(title="A2", category="X"))

    cats = await card_service.get_categories()
    assert sorted(cats) == ["X", "Y"]


@pytest.mark.asyncio
async def test_batch_import():
    """批量导入。"""
    cards = [CardCreate(title=f"批量{i}", category="批量测试") for i in range(3)]
    result = await card_service.batch_import(cards)
    assert result.total == 3
    assert len(result.success) == 3

    all_cards, total = await card_service.list_cards()
    assert total == 3


@pytest.mark.asyncio
async def test_create_card_with_examples_and_questions():
    """创建含案例和问题的卡片。"""
    data = CardCreate(
        title="测试卡",
        content="内容",
        examples=["例1", "例2"],
        questions=["问1"],
        category="测试",
    )
    card = await card_service.create_card(data)
    assert len(card.examples) == 2
    assert len(card.questions) == 1

    fetched = await card_service.get_card(card.id)
    assert len(fetched.examples) == 2
    assert "例1" in fetched.examples


@pytest.mark.asyncio
async def test_association_detection():
    """关联检测 — 创建一张引用另一张标题的卡片。"""
    card1 = await card_service.create_card(CardCreate(title="CPU", content="CPU 是核心", category="硬件"))
    card2 = await card_service.create_card(CardCreate(
        title="冯诺依曼",
        content="冯诺依曼架构中 CPU 通过总线连接内存",
        category="硬件",
    ))
    fetched = await card_service.get_card(card2.id)
    assert len(fetched.related_cards) == 1, "新卡片应关联到 CPU"
    # 反向关联验证
    cpu_card = await card_service.get_card(card1.id)
    assert cpu_card is not None
    assert card2.id in cpu_card.related_cards, "CPU 卡片也应反向关联到冯诺依曼"
