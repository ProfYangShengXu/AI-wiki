"""工具层 + 规划层测试。"""

import json
import pytest
from unittest.mock import patch

from bobanana.agent_react import (
    _parse_reAct, _build_tools_desc, run_ask_mode, run_agent_mode
)
from bobanana.tools_schema import TOOLS as TOOLS_SCHEMA, execute_tool
from bobanana.database import db_manager


class TestReActParser:
    """_parse_reAct 解析器全覆盖测试。"""

    def test_parse_simple_action(self):
        raw = "Thought: 需要搜索。\nAction: search_knowledge({\"query\": \"CPU\"})"
        thought, action = _parse_reAct(raw)
        assert thought == "需要搜索。"
        assert action == ("search_knowledge", {"query": "CPU"})

    def test_parse_no_action(self):
        raw = "Thought: 知识库中没有相关信息。"
        thought, action = _parse_reAct(raw)
        assert thought == "知识库中没有相关信息。"
        assert action is None

    def test_parse_final_answer(self):
        raw = "Final Answer: 知识库显示CPU是中央处理器。"
        thought, action = _parse_reAct(raw)
        assert action is None

    def test_parse_nested_json(self):
        """Action 参数含嵌套 JSON。"""
        raw = 'Action: grade_quiz({"card_id": "abc", "answers": [{"q": "1", "a": "test"}]})'
        thought, action = _parse_reAct(raw)
        assert action is not None
        assert action[0] == "grade_quiz"
        assert action[1]["card_id"] == "abc"
        assert len(action[1]["answers"]) == 1

    def test_parse_empty(self):
        thought, action = _parse_reAct("")
        assert thought == ""
        assert action is None

    def test_parse_multiple_actions(self):
        """多 Action 取第一个。"""
        raw = "Action: search_knowledge({\"query\": \"X\"})\nAction: get_card({\"card_id_or_title\": \"Y\"})"
        thought, action = _parse_reAct(raw)
        assert action[0] == "search_knowledge"

    def test_parse_invalid_json_in_action(self):
        """JSON 格式错误时返回空 params。"""
        raw = "Action: bad_tool({invalid json})"
        thought, action = _parse_reAct(raw)
        assert action is not None
        assert action[0] == "bad_tool"
        assert action[1] == {}

    def test_parse_deeply_nested(self):
        """深度嵌套 JSON。"""
        raw = 'Action: create_card({"title": "X", "examples": [{"name": "test", "desc": "desc"}]})'
        _, action = _parse_reAct(raw)
        assert action is not None
        assert len(action[1]["examples"]) == 1


class TestBuildToolsDesc:
    """工具描述构建测试。"""

    def test_all_tools_included(self):
        desc = _build_tools_desc()
        assert len(desc) > 0
        assert "search_knowledge" in desc
        assert "create_card" in desc
        assert "delete_card" in desc
        assert "start_quiz" in desc
        assert "create_exam" in desc

    def test_concise_format(self):
        """验证精简格式：一行一个工具。"""
        desc = _build_tools_desc()
        lines = [l for l in desc.split("\n") if l.strip()]
        assert len(lines) == len(TOOLS_SCHEMA)


class TestExecuteTool:
    """工具执行函数测试（需要 ChromaDB 初始化）。"""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        import chromadb
        from bobanana.config import CHROMA_DB_DIR
        if db_manager._client is None:
            db_manager._client = chromadb.PersistentClient(
                path=str(CHROMA_DB_DIR),
                settings=chromadb.config.Settings(anonymized_telemetry=False),
            )
        test_col = db_manager._client.get_or_create_collection(
            name="test_tools_cards",
            metadata={"hnsw:space": "cosine"},
        )
        old = db_manager._collection
        db_manager._collection = test_col
        yield
        db_manager._collection = old

    def test_search_knowledge_empty(self):
        r = execute_tool("search_knowledge", {"query": "nonexistent_xyz"})
        assert r["count"] == 0

    def test_list_categories(self):
        r = execute_tool("list_categories", {})
        assert "categories" in r

    def test_get_card_not_found(self):
        r = execute_tool("get_card", {"card_id_or_title": "nonexistent_xyz"})
        assert "error" in r

    def test_unknown_tool(self):
        r = execute_tool("nonexistent_tool", {})
        assert "error" in r


class TestAskMode:
    """Ask 模式测试（mock LLM）。"""

    @patch("bobanana.agent_react.llm_invoke")
    @patch("bobanana.agent_react.card_search")
    def test_ask_with_results(self, mock_search, mock_llm):
        mock_search.return_value = [{
            "title": "CPU", "content": "中央处理器",
            "source_file": "test.pdf"
        }]
        mock_llm.return_value = "基于知识库，CPU是中央处理器。来源: test.pdf"

        result = run_ask_mode("什么是CPU？")
        assert "CPU" in result or "中央处理器" in result

    @patch("bobanana.agent_react.llm_invoke")
    @patch("bobanana.agent_react.card_search")
    def test_ask_no_results(self, mock_search, mock_llm):
        mock_search.return_value = []
        mock_llm.return_value = "知识库中暂无相关信息。"

        result = run_ask_mode("什么是火星？")
        assert "暂无" in result.lower() or "没有" in result.lower()


class TestAgentMode:
    """Agent 模式测试（mock LLM + mock tools）。"""

    @patch("bobanana.agent_react.execute_tool")
    @patch("bobanana.agent_react.llm_invoke")
    def test_agent_search_then_answer(self, mock_llm, mock_execute):
        """Agent 先搜索再回答。"""
        mock_llm.side_effect = [
            'Thought: 需要搜索。\nAction: search_knowledge({"query": "CPU"})',
            'Final Answer: 根据搜索，CPU是中央处理器。'
        ]
        mock_execute.return_value = {"results": [{"title": "CPU", "content": "test"}]}

        result = run_agent_mode("查找CPU", max_turns=3)
        assert "CPU" in result or "中央处理器" in result

    @patch("bobanana.agent_react.llm_invoke")
    def test_agent_direct_answer(self, mock_llm):
        """Agent 直接回答（无需工具）。"""
        mock_llm.return_value = "Final Answer: 你好！我是StudyWiki Agent。"

        result = run_agent_mode("你好", max_turns=2)
        assert len(result) > 0

    @patch("bobanana.agent_react.execute_tool")
    @patch("bobanana.agent_react.llm_invoke")
    def test_agent_unknown_tool_handling(self, mock_llm, mock_execute):
        """Agent 使用未知工具时优雅处理。"""
        mock_llm.side_effect = [
            'Thought: 尝试。\nAction: nonexistent_tool({"x": 1})',
            'Thought: 工具不存在。\nFinal Answer: 操作失败，工具不存在。'
        ]
        mock_execute.return_value = {"error": "未知工具"}

        result = run_agent_mode("测试", max_turns=3)
        assert "失败" in result or "不存在" in result

    @patch("bobanana.agent_react.execute_tool")
    @patch("bobanana.agent_react.llm_invoke")
    def test_agent_create_card_flow(self, mock_llm, mock_execute):
        """Agent 创建卡片全流程。"""
        mock_llm.side_effect = [
            'Thought: 创建卡片。\nAction: create_card({"title": "逻辑门"})',
            'Final Answer: 已创建"逻辑门"卡片。'
        ]
        mock_execute.return_value = {"status": "created", "card": {"title": "逻辑门"}}

        result = run_agent_mode("创建一张逻辑门的卡片", max_turns=3)
        assert "逻辑门" in result or "创建" in result
