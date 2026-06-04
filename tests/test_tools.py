"""工具集单元测试 — 文档解析 / 文本分块。"""

import os
import tempfile
import pytest

from bobanana.tools import parse_document, chunk_text


class TestDocumentParsing:
    """文档解析测试。"""

    def test_parse_markdown(self):
        """解析 .md 文件。"""
        content = """# 标题

## 第一节

这是第一节内容。

## 第二节

这是第二节内容。
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(content)
            tmp_path = f.name
        try:
            pages = parse_document(tmp_path)
            assert len(pages) >= 2
            assert any("第一节" in p["text"] for p in pages)
            assert any("第二节" in p["text"] for p in pages)
        finally:
            os.unlink(tmp_path)

    def test_parse_text(self):
        """解析 .txt 文件。"""
        content = "第一段内容\n\n第二段内容\n\n第三段内容"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(content)
            tmp_path = f.name
        try:
            pages = parse_document(tmp_path)
            assert len(pages) >= 2
        finally:
            os.unlink(tmp_path)

    def test_parse_empty_markdown(self):
        """空 Markdown 文件。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("")
            tmp_path = f.name
        try:
            pages = parse_document(tmp_path)
            assert len(pages) == 1  # 至少有一页（空页）
        finally:
            os.unlink(tmp_path)

    def test_unsupported_extension(self):
        """不支持的文件类型。"""
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            tmp_path = f.name
        try:
            with pytest.raises(ValueError, match="不支持"):
                parse_document(tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_nonexistent_file(self):
        """不存在的文件。"""
        with pytest.raises(Exception):
            parse_document("/nonexistent/file.pdf")


class TestChunkText:
    """文本分块测试。"""

    def test_short_text(self):
        """短文本不分块。"""
        text = "短文本"
        chunks = chunk_text(text, max_chars=100)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text(self):
        """长文本分块。"""
        text = "段落1\n\n段落2\n\n段落3\n\n段落4\n\n段落5"
        chunks = chunk_text(text, max_chars=20, overlap=5)
        assert len(chunks) > 1

    def test_exact_boundary(self):
        """文本长度恰好等于 max_chars。"""
        text = "A" * 100
        chunks = chunk_text(text, max_chars=100)
        assert len(chunks) == 1

    def test_overlap(self):
        """重叠分块。"""
        text = "词语A " * 50  # ~300 chars
        chunks = chunk_text(text, max_chars=100, overlap=20)
        # 验证分块数
        assert len(chunks) >= 2
