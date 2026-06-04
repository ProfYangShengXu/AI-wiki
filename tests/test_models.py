"""数据模型单元测试。"""

import pytest
from pydantic import ValidationError
from datetime import datetime, timezone

from bobanana.models import (
    KnowledgeCard, CardCreate, CardUpdate, CardResponse,
    CardListResponse, ImportResult, ApiResponse, WSMessage,
)


class TestKnowledgeCard:
    """KnowledgeCard 内部模型测试。"""

    def test_minimal_card(self):
        """最简卡片创建。"""
        card = KnowledgeCard(title="测试")
        assert card.title == "测试"
        assert card.aliases == []
        assert card.category == "未分类"
        assert card.created_at is not None

    def test_full_card(self):
        """完整卡片。"""
        card = KnowledgeCard(
            title="CPU",
            aliases=["中央处理器", "处理器"],
            content="CPU 是计算机核心部件。",
            examples=["Intel Core i7", "ARM"],
            questions=["CPU 由哪些部分组成？"],
            category="计算机组成",
            source_file="test.md",
            source_page=3,
            related_cards=["uuid-1", "uuid-2"],
        )
        assert card.title == "CPU"
        assert len(card.aliases) == 2
        assert len(card.examples) == 2
        assert len(card.related_cards) == 2

    def test_embedding_text(self):
        """嵌入文本生成 — 应包含 title + aliases + content。"""
        card = KnowledgeCard(
            title="CPU",
            aliases=["中央处理器"],
            content="核心部件。",
        )
        text = card.embedding_text()
        assert "CPU" in text
        assert "中央处理器" in text
        assert "核心部件" in text

    def test_empty_title_fails(self):
        """空标题应报错。"""
        with pytest.raises(ValidationError):
            CardCreate(title="", content="test")


class TestCardCreate:
    """创建卡片请求 Schema 测试。"""

    def test_minimal(self):
        data = CardCreate(title="测试")
        assert data.title == "测试"
        assert data.category == "未分类"

    def test_title_too_long(self):
        with pytest.raises(ValidationError):
            CardCreate(title="x" * 201)

    def test_full(self):
        data = CardCreate(
            title="测试",
            aliases=["别名"],
            content="内容",
            examples=["例1"],
            questions=["问1"],
            category="分类",
            source_file="test.md",
            source_page=5,
            related_cards=["id-1"],
        )
        assert data.source_page == 5


class TestCardUpdate:
    """更新卡片请求 — 所有字段可选。"""

    def test_empty_update(self):
        data = CardUpdate()
        assert data.model_dump(exclude_unset=True) == {}

    def test_partial_update(self):
        data = CardUpdate(content="新内容")
        dumped = data.model_dump(exclude_unset=True)
        assert "content" in dumped
        assert "title" not in dumped


class TestApiSchemas:
    """API 响应 Schema 测试。"""

    def test_api_response_success(self):
        resp = ApiResponse(status="success", data={"key": "value"})
        assert resp.status == "success"
        assert resp.error_code is None

    def test_api_response_error(self):
        resp = ApiResponse(status="error", message="出错", error_code="DB_FAILURE")
        assert resp.error_code == "DB_FAILURE"

    def test_api_response_invalid_status(self):
        with pytest.raises(ValidationError):
            ApiResponse(status="invalid")

    def test_import_result(self):
        result = ImportResult(total=5)
        assert result.total == 5
        assert result.success == []
        assert result.failed == []

    def test_import_result_with_data(self):
        from bobanana.models import CardResponse
        card = CardResponse(
            id="id-1", title="T", aliases=[], content="",
            examples=[], questions=[], category="C",
            source_file="", source_page=0, related_cards=[],
            created_at="now", updated_at="now",
        )
        result = ImportResult(
            total=2,
            success=[card],
            failed=[{"title": "F", "reason": "err"}],
        )
        assert len(result.success) == 1
        assert len(result.failed) == 1


class TestWSMessage:
    """WebSocket 消息 Schema 测试。"""

    def test_valid_types(self):
        for t in ("message", "response", "progress", "card_preview", "card_update", "error"):
            msg = WSMessage(type=t, content="test")
            assert msg.type == t

    def test_invalid_type(self):
        with pytest.raises(ValidationError):
            WSMessage(type="unknown")
