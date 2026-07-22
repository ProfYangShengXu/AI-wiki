"""agent.py 核心函数测试 — mock LLM，不依赖网络/Kay。"""

import json
from unittest.mock import patch

from bobanana.agent import _parse_llm_json


class TestParseLlmJson:
    """_parse_llm_json 是所有 LLM 响应的入口，必须健壮。"""

    def test_normal_json_array(self):
        """标准 JSON 数组。"""
        result = _parse_llm_json('[{"title": "CPU", "content": "test"}]')
        assert result == [{"title": "CPU", "content": "test"}]

    def test_json_with_codeblock(self):
        """```json ... ``` 包裹。"""
        raw = '```json\n[{"title": "CPU"}]\n```'
        result = _parse_llm_json(raw)
        assert result == [{"title": "CPU"}]

    def test_json_with_triple_backtick_no_lang(self):
        """``` ... ``` 无 json 标记。"""
        raw = '```\n[{"title": "CPU"}]\n```'
        result = _parse_llm_json(raw)
        assert result == [{"title": "CPU"}]

    def test_single_quotes(self):
        """LLM 有时返回单引号。"""
        raw = "[{'title': 'CPU', 'content': 'test'}]"
        result = _parse_llm_json(raw)
        assert result == [{"title": "CPU", "content": "test"}]

    def test_trailing_comma(self):
        """尾逗号修复。"""
        raw = '[{"title": "CPU", "content": "test",}]'
        result = _parse_llm_json(raw)
        assert result == [{"title": "CPU", "content": "test"}]

    def test_empty_array(self):
        result = _parse_llm_json("[]")
        assert result == []

    def test_invalid_json(self):
        """非法 JSON 返回 None。"""
        result = _parse_llm_json("不是 JSON")
        assert result is None

    def test_empty_string(self):
        result = _parse_llm_json("")
        assert result is None

    def test_none_input(self):
        result = _parse_llm_json(None)
        assert result is None

    def test_json_object_not_array(self):
        """LLM 有时返回对象而非数组。"""
        raw = '{"title": "CPU", "content": "test"}'
        result = _parse_llm_json(raw)
        assert result is None  # 期望数组

    def test_codeblock_with_extra_text(self):
        """代码块前后有额外文本。"""
        raw = '以下是提取结果：\n```json\n[{"title": "CPU"}]\n```\n共1个知识点。'
        result = _parse_llm_json(raw)
        assert result == [{"title": "CPU"}]

    def test_truncated_no_closing(self):
        """无闭合 ```json 但 JSON 本身完整。"""
        raw = '```json\n[{"title": "CPU", "content": "test"}]'
        result = _parse_llm_json(raw)
        assert result == [{"title": "CPU", "content": "test"}]

    def test_truncated_partial_array(self):
        """无闭合 ```json，JSON 数组也完整。"""
        raw = '```json\n[{"title": "A"}, {"title": "B"}]'
        result = _parse_llm_json(raw)
        assert result == [{"title": "A"}, {"title": "B"}]

    def test_multiple_codeblocks(self):
        """多个代码块取第一个。"""
        raw = '```json\n[{"title": "A"}]\n```\n无关文本\n```\n[{"title": "B"}]\n```'
        result = _parse_llm_json(raw)
        assert result == [{"title": "A"}]


class TestExtractRange:
    """_extract_range 的逐页/聚合策略测试。"""

    @patch("bobanana.agent.llm_invoke")
    def test_per_page_extraction(self, mock_llm):
        """<=3 页走逐页提取。"""
        from bobanana.agent import _extract_range

        mock_llm.return_value = '[{"title": "测试", "content": "内容"}]'
        pages = [{"page_num": 1, "text": "第1页内容"}]
        result = _extract_range(
            pages, 1, 1, "第1-1页", "test.md", set()
        )
        assert len(result) == 1
        assert result[0]["title"] == "测试"
        assert result[0]["source_file"] == "test.md"
        assert result[0]["source_page"] == 1
        mock_llm.assert_called_once()

    @patch("bobanana.agent.llm_invoke")
    def test_aggregated_extraction(self, mock_llm):
        """>3 页走聚合提取。"""
        from bobanana.agent import _extract_range

        mock_llm.return_value = '[{"title": "聚合", "content": "一次提取"}]'
        pages = [{"page_num": i, "text": f"第{i}页内容"} for i in range(1, 6)]
        result = _extract_range(
            pages, 1, 5, "第1-5页", "test.md", set()
        )
        assert len(result) == 1
        mock_llm.assert_called_once()

    @patch("bobanana.agent.llm_invoke")
    def test_dedup_by_title(self, mock_llm):
        """已有标题不重复提取。"""
        from bobanana.agent import _extract_range

        mock_llm.return_value = '[{"title": "CPU"}, {"title": "内存"}]'
        pages = [{"page_num": 1, "text": "内容"}]
        existing = {"cpu"}
        result = _extract_range(
            pages, 1, 1, "第1-1页", "test.md", existing
        )
        assert len(result) == 1  # 只有"内存"
        assert result[0]["title"] == "内存"

    @patch("bobanana.agent.llm_invoke")
    def test_llm_failure_fallback(self, mock_llm):
        """聚合失败回退逐页。"""
        from bobanana.agent import _extract_range

        # 第一次(聚合)抛异常，第二次(逐页)成功
        mock_llm.side_effect = [
            Exception("LLM 聚合失败"),
            '[{"title": "回退", "content": "逐页提取"}]',
        ]
        pages = [{"page_num": i, "text": f"第{i}页内容"} for i in range(1, 5)]
        result = _extract_range(
            pages, 1, 4, "第1-4页", "test.md", set()
        )
        assert len(result) >= 1
        assert mock_llm.call_count >= 2



