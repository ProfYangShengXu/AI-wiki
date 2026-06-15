import os
"""Agent 工具集 — 文档解析、网络搜索、嵌入模型、文本分块。"""

import logging
import threading
import re
from pathlib import Path
from typing import Optional

from bobanana.config import (
    EMBEDDING_PROVIDER,
    EMBEDDING_DIMENSION,
    SENTENCE_TRANSFORMERS_MODEL,
    OPENAI_EMBEDDING_MODEL,
    RETRIEVAL_TOP_K,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 1. 嵌入模型
# ═══════════════════════════════════════════════════════════

_embedding_model = None
_embedding_lock = threading.Lock()


def get_embedding_model():
    # Force offline mode for HuggingFace (use local cache only)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    """懒加载嵌入模型。"""
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    with _embedding_lock:
        if _embedding_model is not None:
            return _embedding_model

    if EMBEDDING_PROVIDER == "sentence-transformers":
        from sentence_transformers import SentenceTransformer
        logger.info("加载嵌入模型: %s ...", SENTENCE_TRANSFORMERS_MODEL)
        _embedding_model = SentenceTransformer(SENTENCE_TRANSFORMERS_MODEL)
        logger.info("嵌入模型就绪, 维度: %d", _embedding_model.get_embedding_dimension())
    else:
        # OpenAI embedding: 直接返回 None, 由 embed_text 处理
        _embedding_model = "openai"
        logger.info("使用 OpenAI 嵌入: %s", OPENAI_EMBEDDING_MODEL)

    return _embedding_model


def embed_text(text: str) -> list[float]:
    """将文本转为向量。"""
    model = get_embedding_model()

    if model == "openai":
        from langchain_openai import OpenAIEmbeddings
        from bobanana.config import OPENAI_API_KEY
        emb = OpenAIEmbeddings(
            model=OPENAI_EMBEDDING_MODEL,
            openai_api_key=OPENAI_API_KEY,
        )
        vector = emb.embed_query(text)
        return vector
    else:
        vector = model.encode(text, normalize_embeddings=True).tolist()
        return vector


# ═══════════════════════════════════════════════════════════
# 2. 文档解析
# ═══════════════════════════════════════════════════════════

def parse_document(file_path: str) -> list[dict]:
    """解析文档，返回 [{page_num, text}, ...] 列表。"""
    path = Path(file_path)
    ext = path.suffix.lower()

    logger.info("解析文档: %s", file_path)

    if ext == ".pdf":
        return _parse_pdf(file_path)
    elif ext in (".docx", ".doc"):
        return _parse_docx(file_path)
    elif ext == ".md":
        return _parse_markdown(file_path)
    elif ext == ".txt":
        return _parse_text(file_path)
    else:
        raise ValueError(f"不支持的文件类型: {ext}")


def _parse_pdf(file_path: str) -> list[dict]:
    """解析 PDF — 逐页提取文本，文本少于 50 字时尝试 OCR。"""
    import fitz  # PyMuPDF
    pages = []
    doc = fitz.open(file_path)
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text().strip()
        # 文本太少 → 尝试 OCR
        if len(text) < 50:
            ocr_text = _ocr_page(page)
            if ocr_text and len(ocr_text) > len(text):
                text = ocr_text
        pages.append({"page_num": page_num + 1, "text": text})
    doc.close()
    ocr_pages = sum(1 for p in pages if p.get("_ocr"))
    if ocr_pages:
        logger.info("PDF 解析完成: %d 页 (其中 %d 页使用 OCR)", len(pages), ocr_pages)
    else:
        logger.info("PDF 解析完成: %d 页", len(pages))
    return pages


def _ocr_page(page) -> str:
    """对 PyMuPDF 页面做 OCR。失败时返回空字符串。"""
    try:
        import pytesseract
        # 设置 tesseract 路径（不在 PATH 时的 fallback）
        import os as _os
        for _p in [r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                   r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe']:
            if _os.path.exists(_p):
                pytesseract.pytesseract.tesseract_cmd = _p
                break
        from PIL import Image
        import io
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(img, lang="chi_sim+eng").strip()
        if text:
            return text
    except Exception as e:
        logger.debug("OCR 失败 (页 %d): %s", page.number + 1, e)
    return ""


def _parse_docx(file_path: str) -> list[dict]:
    """解析 Word — 按段落分页。"""
    from docx import Document
    pages = []
    doc = Document(file_path)
    current_text = []
    page_num = 1

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        # 分页符检测
        if "PAGE_BREAK" in text or "—————" in text:
            if current_text:
                pages.append({"page_num": page_num, "text": "\n".join(current_text)})
                page_num += 1
                current_text = []
        else:
            current_text.append(text)

    if current_text:
        pages.append({"page_num": page_num, "text": "\n".join(current_text)})

    # 如果没有分页符，整个文档作为一页
    if not pages:
        full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        pages.append({"page_num": 1, "text": full_text})

    logger.info("Word 解析完成: %d 页", len(pages))
    return pages


def _parse_markdown(file_path: str) -> list[dict]:
    """解析 Markdown — 按标题分节。"""
    import markdown as md_lib
    with open(file_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # 按 ## 标题分割
    sections = re.split(r"\n(?=##\s)", raw)
    pages = []
    for i, section in enumerate(sections):
        if section.strip():
            # 转 HTML 用于展示，但保留纯文本用于提取
            html = md_lib.markdown(section)
            pages.append({"page_num": i + 1, "text": section.strip(), "html": html})

    if not pages:
        pages.append({"page_num": 1, "text": raw})

    logger.info("Markdown 解析完成: %d 节", len(pages))
    return pages


def _parse_text(file_path: str) -> list[dict]:
    """解析纯文本 — 按空行分块。"""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    blocks = re.split(r"\n\s*\n", text)
    pages = []
    for i, block in enumerate(blocks):
        if block.strip():
            pages.append({"page_num": i + 1, "text": block.strip()})

    if not pages:
        pages.append({"page_num": 1, "text": text})

    logger.info("文本解析完成: %d 块", len(pages))
    return pages


# ═══════════════════════════════════════════════════════════
# 3. 文本分块
# ═══════════════════════════════════════════════════════════

def chunk_text(text: str, max_chars: int = 2000, overlap: int = 100) -> list[str]:
    """将长文本分块，避免超出 LLM 上下文窗口。"""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        if end >= len(text):
            chunks.append(text[start:])
            break

        # 在边界处寻找最近的换行符
        newline_pos = text.rfind("\n", start, end)
        if newline_pos > start + max_chars // 2:
            end = newline_pos
        else:
            space_pos = text.rfind(" ", start, end)
            if space_pos > start + max_chars // 2:
                end = space_pos

        chunks.append(text[start:end])
        start = end - overlap

    return chunks


# ═══════════════════════════════════════════════════════════
# 4. 网络搜索
# ═══════════════════════════════════════════════════════════

def web_search(query: str, top_k: int = 3) -> list[dict]:
    """使用 DuckDuckGo 搜索，返回 [{title, snippet, url}]。"""
    try:
        from duckduckgo_search import DDGS
        logger.info("网络搜索: %s", query)
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=top_k):
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                })
        logger.info("搜索结果: %d 条", len(results))
        return results
    except Exception as e:
        logger.warning("网络搜索失败: %s", e)
        return []


# ═══════════════════════════════════════════════════════════
# 5. 知识提取辅助
# ═══════════════════════════════════════════════════════════

def build_page_context(pages: list[dict], current_idx: int, context_pages: int = 1) -> str:
    """构建当前页的上下文（前后共 context_pages 页）。"""
    start = max(0, current_idx - context_pages)
    end = min(len(pages), current_idx + context_pages + 1)

    parts = []
    for i in range(start, end):
        prefix = "【上文】" if i < current_idx else ("【下文】" if i > current_idx else "【当前页】")
        parts.append(f"{prefix} 第{pages[i]['page_num']}页:\n{pages[i]['text'][:500]}")
    return "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════
# 6. LLM 调用
# ═══════════════════════════════════════════════════════════

_llm = None


def get_llm():
    """懒加载 LLM 实例。"""
    global _llm
    if _llm is not None:
        return _llm

    from bobanana.config import (
        LLM_PROVIDER, LLM_TEMPERATURE,
        OPENAI_API_KEY, OPENAI_MODEL,
        OLLAMA_BASE_URL, OLLAMA_MODEL,
        DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    )

    if LLM_PROVIDER == "deepseek":
        from langchain_openai import ChatOpenAI
        api_key = DEEPSEEK_API_KEY or OPENAI_API_KEY
        _llm = ChatOpenAI(
            model=DEEPSEEK_MODEL,
            temperature=LLM_TEMPERATURE,
            api_key=api_key,
            base_url=DEEPSEEK_BASE_URL,
        )
        logger.info("LLM 就绪: DeepSeek %s @ %s", DEEPSEEK_MODEL, DEEPSEEK_BASE_URL)
    elif LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI
        _llm = ChatOpenAI(
            model=OPENAI_MODEL,
            temperature=LLM_TEMPERATURE,
            api_key=OPENAI_API_KEY,
        )
        logger.info("LLM 就绪: OpenAI %s", OPENAI_MODEL)
    else:
        from langchain_community.chat_models import ChatOllama
        _llm = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=LLM_TEMPERATURE,
        )
        logger.info("LLM 就绪: Ollama %s @ %s", OLLAMA_MODEL, OLLAMA_BASE_URL)

    return _llm


# ═══════════════════════════════════════════════════════════
# 7. 文档预扫描器 (Phase 1)
# ═══════════════════════════════════════════════════════════

class ScanResult:
    """预扫描结果。"""
    def __init__(self, total_pages=0, valid_ranges=None, language="zh", doc_type="unknown", skipped_pages=None, pages=None):
        self.total_pages = total_pages
        self.valid_ranges = valid_ranges or []  # [(start, end, topic), ...]
        self.language = language
        self.doc_type = doc_type
        self.skipped_pages = skipped_pages or []
        self.pages = pages or []


class DocumentScanner:
    """Phase 1: 预扫描文档结构，识别有效内容区间。"""

    MIN_CONTENT_CHARS = 50  # 少于 50 个字符的页视为空白页

    def scan(self, file_path: str) -> ScanResult:
        pages = parse_document(file_path)
        if not pages:
            return ScanResult()

        total = len(pages)
        stats = self._analyze_pages(pages)
        structure = self._detect_structure(pages[:min(3, total)])
        valid_ranges, skipped = self._compute_valid_ranges(pages, stats)

        logger.info(
            "预扫描: %d 页, 有效区间 %d 个, 跳过 %d 页, 类型=%s, 语言=%s",
            total, len(valid_ranges), len(skipped), structure.get("doc_type","?"), structure.get("language","?"),
        )
        return ScanResult(
            total_pages=total,
            valid_ranges=valid_ranges,
            language=structure.get("language", "zh"),
            doc_type=structure.get("doc_type", "unknown"),
            skipped_pages=skipped,
            pages=pages,
        )

    def _analyze_pages(self, pages: list) -> list:
        """统计每页特征。"""
        stats = []
        for i, p in enumerate(pages):
            text = p.get("text", "")
            char_count = len(text.strip())
            non_space = len(text.strip().replace(" ", "").replace("\n", ""))
            stats.append({
                "index": i,
                "page_num": p.get("page_num", i + 1),
                "char_count": char_count,
                "non_space_chars": non_space,
                "is_blank": non_space < self.MIN_CONTENT_CHARS,
                "has_chinese": bool(re.search(r'[\u4e00-\u9fff]', text)),
            })
        return stats

    def _detect_structure(self, sample_pages: list) -> dict:
        """LLM 快速识别文档类型和语言。"""
        sample_text = "\n".join([p.get("text", "")[:500] for p in sample_pages if p.get("text")])[:2000]
        if not sample_text.strip():
            return {"language": "unknown", "doc_type": "unknown"}

        try:
            prompt = f"""分析以下文档开头的内容，返回 JSON:
{{
  "language": "zh" 或 "en",
  "doc_type": "教材" | "论文" | "PPT讲义" | "实验报告" | "其他",
  "title_hint": "可能的标题或主题"
}}

内容:
{sample_text[:1000]}"""
            result = llm_invoke("你是一个文档分析专家。只返回 JSON。", prompt)
            import json as _json
            for line in result.split("\n"):
                line = line.strip()
                if line.startswith("{"):
                    return _json.loads(line)
        except Exception:
            pass
        return {"language": "zh", "doc_type": "unknown"}

    def _compute_valid_ranges(self, pages: list, stats: list) -> tuple:
        """跳过空白页/封面/引用页，合并连续有效页为区间。"""
        valid_ranges = []
        skipped = []
        i = 0
        while i < len(pages):
            if stats[i]["is_blank"]:
                skipped.append(stats[i]["page_num"])
                i += 1
                continue

            # 检查是否可能是封面/目录（文档较长时才启用，避免误判短文档）
            if len(pages) > 3 and i < 3 and stats[i]["non_space_chars"] < 200:
                skipped.append(stats[i]["page_num"])
                i += 1
                continue

            # 合并连续有效页（每段最多 10 页，避免 LLM 响应过长被截断）
            start = stats[i]["page_num"]
            page_count = 0
            while i < len(pages) and not stats[i]["is_blank"] and page_count < 10:
                page_count += 1
                i += 1
            end = stats[i - 1]["page_num"]
            valid_ranges.append((start, end, f"第{start}-{end}页"))

        return valid_ranges, skipped


def llm_invoke(system_prompt: str, user_prompt: str, timeout_sec: int = None) -> str:
    """调用 LLM，返回文本结果。支持超时和重试。"""
    import concurrent.futures
    from langchain_core.messages import SystemMessage, HumanMessage
    from bobanana.config import LLM_TIMEOUT_SEC

    if timeout_sec is None:
        timeout_sec = LLM_TIMEOUT_SEC

    llm = get_llm()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    def _call():
        response = llm.invoke(messages)
        return response.content

    pool = concurrent.futures.ThreadPoolExecutor(1)
    future = pool.submit(_call)
    try:
        return future.result(timeout=timeout_sec)
    except concurrent.futures.TimeoutError:
        logger.warning("LLM 调用超时 (%.0fs)", timeout_sec)
        pool.shutdown(wait=False)
        raise TimeoutError(f"LLM 调用超时 ({timeout_sec}s)")
    except Exception as e:
        logger.error("LLM 调用失败: %s", e)
        pool.shutdown(wait=True)
        raise
    else:
        pool.shutdown(wait=True)
