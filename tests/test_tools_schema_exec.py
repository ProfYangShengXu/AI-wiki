"""工具执行层 (execute_tool) 全分支测试。"""

import pytest

from bobanana.models import CardCreate
from bobanana.service.card_service import card_service
from bobanana.tools_schema import TOOLS, execute_tool, validate_tool_args


@pytest.fixture
def seeded():
    card_service.create_card_sync(CardCreate(
        title="与门", category="数字逻辑", content="与门:所有输入为1时输出1。",
        aliases=["AND"], examples=["双钥匙门"], source_file="test",
    ))
    card_service.create_card_sync(CardCreate(
        title="或门", category="数字逻辑", content="或门:任一输入为1输出1。",
        source_file="test",
    ))


@pytest.fixture
def fake_llm(monkeypatch):
    from tests.fakes import FakeLLM
    fake = FakeLLM()
    monkeypatch.setattr("bobanana.tools_schema.llm_invoke", fake)
    # 导入流水线 (upload_document) 内部走 agent/tools 的 llm_invoke,一并打桩
    monkeypatch.setattr("bobanana.agent.llm_invoke", fake)
    monkeypatch.setattr("bobanana.tools.llm_invoke", fake)
    return fake


def test_validate_tool_args_create_card():
    ok, model = validate_tool_args("create_card", {"title": "逻辑门"})
    assert ok
    ok2, err = validate_tool_args("create_card", {})
    assert not ok2


def test_validate_unknown_tool():
    ok, err = validate_tool_args("no_such_tool", {})
    assert not ok


def test_all_tools_have_pydantic_models():
    from bobanana.tools_schema import TOOL_PYDANTIC_MODELS
    assert set(TOOL_PYDANTIC_MODELS.keys()) == {t["name"] for t in TOOLS}


def test_search_and_categories(seeded):
    r = execute_tool("search_knowledge", {"query": "与门"})
    assert r["count"] >= 1
    r2 = execute_tool("list_categories", {})
    assert "数字逻辑" in r2["categories"]


def test_get_card(seeded):
    r = execute_tool("get_card", {"card_id_or_title": "与门"})
    assert r["card"]["title"] == "与门"
    r2 = execute_tool("get_card", {"card_id_or_title": "不存在卡片xyz"})
    assert "error" in r2


def test_create_card_with_content(seeded):
    r = execute_tool("create_card", {
        "title": "全加器", "category": "数字逻辑",
        "content": "全加器含进位输入。", "examples": ["加法器"],
    })
    assert r["status"] == "created"


def test_create_card_autofill(fake_llm):
    fake_llm.responses["完整卡片 JSON"] = (
        '{"title":"CPU","content":"中央处理器。","examples":["例子"],'
        '"category":"计算机"}'
    )
    r = execute_tool("create_card", {"title": "CPU", "category": "计算机"})
    assert r["status"] == "created"


def test_update_card(seeded):
    r = execute_tool("update_card", {"card_id_or_title": "与门", "aliases": ["AND gate"]})
    assert r["status"] == "updated"
    card = card_service.get_card_sync(r["card"]["id"])
    assert "AND gate" in card.aliases


def test_update_card_missing(seeded):
    r = execute_tool("update_card", {"card_id_or_title": "不存在xyz", "content": "x"})
    assert "error" in r


def test_delete_card(seeded):
    r = execute_tool("delete_card", {"card_id_or_title": "或门"})
    assert r["status"] == "deleted"
    r2 = execute_tool("delete_card", {"card_id_or_title": "或门"})
    assert "error" in r2


def test_start_quiz(fake_llm, seeded):
    fake_llm.responses["简答题"] = '[{"question":"Q1","ref_answer":"A1"}]'
    r = execute_tool("start_quiz", {"card_id_or_title": "与门"})
    assert len(r["questions"]) == 1


def test_grade_quiz(fake_llm, seeded):
    cards, _ = card_service.list_cards_sync()
    card = next(c for c in cards if c.title == "与门")
    fake_llm.responses["严格评分"] = '[{"score":8,"comment":"对","reference":"参考"}]'
    r = execute_tool("grade_quiz", {
        "card_id": card.id,
        "answers": [{"question": "Q", "answer": "A"}],
    })
    assert r["total"] == 8
    assert r["max_score"] == 10


def test_create_exam(fake_llm, seeded):
    fake_llm.responses["组卷"] = '[{"question":"Q","ref_answer":"A","related_cards":["与门"]}]'
    r = execute_tool("create_exam", {"category_names": ["数字逻辑"]})
    assert len(r["questions"]) == 1


def test_get_mastery(seeded):
    r = execute_tool("get_mastery", {"card_id_or_title": "与门"})
    assert r["card_title"] == "与门"
    assert 0 <= r["mastery_pct"] <= 100


def test_upload_document(tmp_path, monkeypatch, fake_llm):
    """upload_document 工具走真实导入流水线 (FakeLLM 提取)。"""
    doc = tmp_path / "note.md"
    doc.write_text(
        "# 与门\n\n与门是最基本的逻辑门之一,只有当所有输入都为高电平时输出才为高电平。"
        "与门的逻辑表达式为 Y 等于 A 与 B,两输入真值表共有四种组合,只有输入都为一时输出才为一。"
        "与门常用于数字电路中的条件判断,例如使能信号与数据信号同时有效时才允许数据通过。\n",
        encoding="utf-8",
    )
    fake_llm.responses["知识提取专家"] = (
        '[{"title":"与门(导入)","content":"与门内容。","category":"数字逻辑",'
        '"examples":[],"questions":[],"aliases":[]}]'
    )
    r = execute_tool("upload_document", {"file_path": str(doc)})
    assert r["status"] == "imported", r
    assert r["imported"] >= 1


def test_upload_document_missing_file(tmp_path):
    r = execute_tool("upload_document", {"file_path": str(tmp_path / "nope.md")})
    assert "error" in r


def test_unknown_tool():
    r = execute_tool("not_a_tool", {})
    assert "error" in r
