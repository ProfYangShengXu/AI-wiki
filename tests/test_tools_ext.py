"""tools.py 扩展测试 — DocumentScanner + web_search + llm_invoke (mock)。"""

from unittest.mock import patch

from bobanana.tools import DocumentScanner, ScanResult, chunk_text


class TestDocumentScanner:
    """文档预扫描器测试 — mock parse_document 隔离文件系统。"""

    def _make_mock_pages(self, pages_data: list[dict]) -> list:
        """构造模拟页面数据。"""
        return [
            {"page_num": i + 1, "text": p.get("text", ""), "html": p.get("html", "")}
            for i, p in enumerate(pages_data)
        ]

    @patch("bobanana.tools.parse_document")
    @patch("bobanana.tools.llm_invoke")
    def test_skip_blank_pages(self, mock_llm, mock_parse):
        """跳过空白页。"""
        mock_parse.return_value = self._make_mock_pages([
            {"text": "第一章 计算机组成原理" * 15},  # 有效内容 > 50 chars
            {"text": ""},  # 空白页
            {"text": ""},  # 空白页
            {"text": "第二章 数据表示" * 15},
            {"text": "第三章 运算方法" * 15},
        ])
        # 让 LLM 扫描返回默认结构
        mock_llm.return_value = '{"language": "zh", "doc_type": "教材"}'

        scanner = DocumentScanner()
        result = scanner.scan("/fake/path.pdf")

        assert result.total_pages == 5
        assert len(result.skipped_pages) >= 2  # 空白页被跳过
        assert len(result.valid_ranges) >= 1

    @patch("bobanana.tools.parse_document")
    @patch("bobanana.tools.llm_invoke")
    def test_skip_cover_toc(self, mock_llm, mock_parse):
        """封面和目录（前几页内容少）被跳过。"""
        mock_parse.return_value = self._make_mock_pages([
            {"text": "封面"},  # < 200 字符，应跳过
            {"text": "目录\n第一章 1\n第二章 5"},  # < 200 字符
            {"text": "第一章 引言" * 20},  # 真正的正文
            {"text": "第二章 方法" * 20},
        ])
        mock_llm.return_value = '{"language": "zh", "doc_type": "教材"}'

        scanner = DocumentScanner()
        result = scanner.scan("/fake/path.pdf")

        assert len(result.skipped_pages) >= 2
        assert len(result.valid_ranges) >= 1

    @patch("bobanana.tools.parse_document")
    @patch("bobanana.tools.llm_invoke")
    def test_empty_document(self, mock_llm, mock_parse):
        """空文档无有效区间。"""
        mock_parse.return_value = []
        mock_llm.return_value = '{"language": "unknown", "doc_type": "unknown"}'

        scanner = DocumentScanner()
        result = scanner.scan("/fake/empty.pdf")

        assert result.total_pages == 0
        assert result.valid_ranges == []

    @patch("bobanana.tools.parse_document")
    @patch("bobanana.tools.llm_invoke")
    def test_llm_scan_failure_graceful(self, mock_llm, mock_parse):
        """LLM 扫描失败时使用默认值，不崩溃。"""
        mock_parse.return_value = self._make_mock_pages([
            {"text": "第一章 正文内容" * 50},
        ])
        mock_llm.side_effect = Exception("LLM 超时")

        scanner = DocumentScanner()
        result = scanner.scan("/fake/path.pdf")

        assert result.language == "zh"  # 默认值
        assert result.doc_type == "unknown"
        assert len(result.valid_ranges) >= 1  # 仍然能识别有效页


class TestChunkTextExtended:
    """chunk_text 扩展边界测试。"""

    def test_empty_text(self):
        assert chunk_text("") == [""]

    def test_exact_max_chars(self):
        text = "A" * 100
        result = chunk_text(text, max_chars=100, overlap=0)
        assert len(result) == 1
        assert len(result[0]) == 100

    def test_large_text(self):
        """大文本分块 — 每块不超过 max_chars。"""
        text = "Hello World! " * 10000  # ~130k chars
        result = chunk_text(text, max_chars=1000, overlap=50)
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) <= 1000

    def test_overlap_accuracy(self):
        """重叠区域包含前一块尾部内容。"""
        text = "ABCDE" * 20
        result = chunk_text(text, max_chars=20, overlap=5)
        if len(result) >= 2:
            # 第二块开头应包含第一块尾部
            assert result[1].startswith(result[0][-5:]) or \
                   result[0].endswith(result[1][:5])


class TestScanResult:
    """ScanResult 数据类测试。"""

    def test_default_values(self):
        r = ScanResult()
        assert r.total_pages == 0
        assert r.valid_ranges == []
        assert r.pages == []
        assert r.skipped_pages == []

    def test_with_data(self):
        r = ScanResult(
            total_pages=10,
            valid_ranges=[(1, 5, "第1-5页")],
            language="zh",
            doc_type="教材",
            skipped_pages=[6, 7],
            pages=[{"page_num": 1, "text": "test"}],
        )
        assert r.total_pages == 10
        assert len(r.valid_ranges) == 1
        assert len(r.pages) == 1
