"""tools.py 纯逻辑覆盖:文档扫描器、解析、llm_stream、get_llm 降级链。"""

import pytest

from bobanana import tools


@pytest.fixture
def scanner():
    return tools.DocumentScanner()


def test_scan_markdown(scanner, tmp_path, monkeypatch):
    # _detect_structure 内部会调 llm_invoke,打桩避免真实网络调用
    monkeypatch.setattr(
        "bobanana.tools.llm_invoke",
        lambda *a, **k: '{"language":"zh","doc_type":"教材"}',
    )
    doc = tmp_path / "a.md"
    doc.write_text(
        "# 标题\n\n" + ("这是有效内容。" * 30) + "\n\n## 第二节\n\n" + ("第二节内容。" * 20),
        encoding="utf-8",
    )
    result = scanner.scan(str(doc))
    assert result.total_pages >= 1
    assert len(result.valid_ranges) >= 1


def test_analyze_pages(scanner):
    pages = [
        {"text": "这是有效内容" * 30, "page_num": 1},
        {"text": "", "page_num": 2},
        {"text": "短", "page_num": 3},
    ]
    stats = scanner._analyze_pages(pages)
    assert stats[0]["is_blank"] is False
    assert stats[1]["is_blank"] is True
    assert stats[2]["is_blank"] is True


def test_compute_valid_ranges(scanner):
    pages = [{"text": "内容" * 60, "page_num": 1}, {"text": "内容" * 60, "page_num": 2}]
    stats = scanner._analyze_pages(pages)
    ranges, skipped = scanner._compute_valid_ranges(pages, stats)
    assert ranges == [(1, 2, "第1-2页")]
    assert skipped == []


def test_detect_structure_no_text(scanner):
    assert scanner._detect_structure([]) == {"language": "unknown", "doc_type": "unknown"}


def test_parse_document_markdown(tmp_path):
    doc = tmp_path / "a.md"
    doc.write_text("# 一\n\n内容" * 5, encoding="utf-8")
    pages = tools.parse_document(str(doc))
    assert len(pages) >= 1
    assert pages[0]["page_num"] == 1


def test_parse_document_unknown_type(tmp_path):
    doc = tmp_path / "a.bin"
    doc.write_bytes(b"\x00\x01" * 64)
    with pytest.raises(ValueError):
        tools.parse_document(str(doc))


def test_llm_stream_with_fake(monkeypatch):
    class FakeStreamLLM:
        def stream(self, messages):
            yield type("Chunk", (), {"content": "这是"})()
            yield type("Chunk", (), {"content": "流式回答"})()

    monkeypatch.setattr("bobanana.tools.get_llm", lambda: FakeStreamLLM())
    monkeypatch.setattr("bobanana.tools._is_chat_model", lambda llm: True)
    tools.reset_llm_cache()
    chunks = list(tools.llm_stream("系统", "问题内容"))
    assert "".join(chunks) == "这是流式回答"


def test_get_llm_cached(monkeypatch):
    """get_llm 返回缓存实例;重置后重新构造。"""
    tools.reset_llm_cache()
    llm1 = tools.get_llm()
    assert llm1 is not None
    llm2 = tools.get_llm()
    assert llm1 is llm2
    tools.reset_llm_cache()


def test_llm_invoke_fallback_all_fail(monkeypatch):
    """全部 provider 不可构造 → SW-LLM-503。"""
    from bobanana.errors import SWError

    monkeypatch.setattr("bobanana.tools._construct_llm", lambda p: None)
    tools.reset_llm_cache()
    with pytest.raises(SWError) as exc:
        tools.llm_invoke("s", "u", timeout_sec=5)
    assert exc.value.error_code == "SW-LLM-503"


def test_embed_text_returns_vector():
    vec = tools.embed_text("测试文本")
    assert isinstance(vec, list)
    assert len(vec) == 384
    assert all(isinstance(v, float) for v in vec)


def test_web_search_network_failure_returns_empty(monkeypatch):
    """web_search 网络不可用时返回空列表(不抛异常)。"""
    import duckduckgo_search

    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(duckduckgo_search, "DDGS", _boom)
    results = tools.web_search("测试")
    assert results == []
