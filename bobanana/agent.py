"""多 Agent 并发工作流 — 三阶段流水线: 预扫描 → 智能提取 → 增量入库。"""

import json
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Optional

from bobanana.config import RETRIEVAL_TOP_K
from bobanana.models import CardCreate, ImportResult
from bobanana.service.card_service import card_service
from bobanana.tools import (
    parse_document, web_search, embed_text, chunk_text, llm_invoke,
    build_page_context, DocumentScanner,
)

logger = logging.getLogger(__name__)

# ── Prompt ──────────────────────────────────────────────
SYSTEM_EXTRACT = """你是一个知识提取专家，擅长帮助学生理解和记忆。从课件内容中提取知识点，JSON 数组格式。

每个知识点包含:
- title: 知识点名词 (精简，3-15字)
- aliases: 别名/英文名列表
- content: 详细解释 (400-600字，中文)
  - 先用一句话概括核心概念
  - 展开讲解原理或机制 (200-300字)
  - 加入一个恰当的比喻或生活化类比帮助学生记忆
  - 指出该知识点与其他知识的关联 (如前置知识、后续知识、相似概念对比)
- examples: 案例列表 (2-3个，包含至少一个比喻或生活化例子)
- questions: 复习问题列表 (2-3个，考察理解和联系能力)
- category: 知识领域分类

要求:
1. 只提取明确出现在课件中的知识点，不编造
2. content 必须 400-600 字，信息丰富、逻辑清晰
3. 每张卡片必须包含比喻和知识关联
4. 返回纯 JSON 数组"""

SYSTEM_EXTRACT_AGGREGATED = """你是一个知识提取专家，擅长帮助学生理解和记忆。以下是文档中关于「{topic}」的内容({start}-{end}页)。
提取该区间内所有知识点，JSON 数组格式。注意去重，相同的知识点只出现一次。

每个知识点包含:
- title: 知识点名词 (精简，3-15字)
- aliases: 别名/英文名列表
- content: 详细解释 (400-600字，中文)
  - 先用一句话概括核心概念
  - 展开讲解原理或机制 (200-300字)
  - 加入一个恰当的比喻或生活化类比帮助学生记忆
  - 指出该知识点与其他知识的关联 (如前置知识、后续知识、相似概念对比)
- examples: 案例列表 (2-3个，包含至少一个比喻或生活化例子)
- questions: 复习问题列表 (2-3个，考察理解和联系能力)
- category: 知识领域分类

要求: content 必须 400-600 字，每张卡片必须包含比喻和知识关联。"""

SYSTEM_QA = """你是一个知识问答助手。基于知识库内容回答。
1. 基于检索到的卡片回答，不编造
2. 无相关信息时说"没有找到"
3. 引用卡片标题作为来源"""

SYSTEM_MODIFY = """你是一个卡片编辑助手。根据指令修改卡片，JSON 格式返回完整卡片。"""


# ═══════════════════════════════════════════════════════════
# 1. 三阶段导入流水线
# ═══════════════════════════════════════════════════════════

def _parse_llm_json(text: str) -> Any:
    """安全解析 LLM JSON。"""
    import re
    if not text or not isinstance(text, str):
        return None
    for m in [re.search(r"```(?:json)?\s*([\s\S]*?)```", text),
              re.search(r"(\[.*\])", text, re.DOTALL)]:
        if m:
            text = m.group(1).strip()
            break
    # 如果还残留 ```json 前缀（响应被截断无闭合标记），手动去掉
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text).strip()
    for fix in [lambda t: t, lambda t: t.replace("'", '"'),
                lambda t: re.sub(r",\s*}", "}", t),
                lambda t: re.sub(r",\s*\]", "]", t)]:
        try:
            result = json.loads(fix(text))
            if isinstance(result, list):
                return result
            return None
        except json.JSONDecodeError:
            continue
    return None


def _extract_range(pages: list, start: int, end: int, topic: str,
                   source_file: str, existing_titles: set) -> list[dict]:
    """智能提取一个区间的内容。

    短区间 (<=3页) → 逐页提取
    长区间 (>3页)  → 聚合提取（合并文本，一次性提取）
    """
    length = end - start + 1
    page_objs = [p for p in pages if start <= p["page_num"] <= end]
    results = []

    if length <= 3:
        # 逐页提取
        for p in page_objs:
            try:
                user_prompt = f"""文档第{p['page_num']}页:
{p['text'][:3000]}"""
                raw = llm_invoke(SYSTEM_EXTRACT, user_prompt)
                if not raw or len(raw) < 10:
                    logger.warning("第%d页 LLM 返回空", p["page_num"])
                logger.info("EXTRACT_RAW[%d]: %s", p["page_num"], raw[:200])
                parsed = _parse_llm_json(raw)
                if not parsed:
                    logger.warning("EXTRACT_FAIL[%d]: %s", p["page_num"], raw[:200])
                else:
                    logger.info("EXTRACT_OK[%d]: %d items", p["page_num"], len(parsed))
                if parsed and isinstance(parsed, list):
                    for item in parsed:
                        item["source_file"] = source_file
                        item["source_page"] = p["page_num"]
                    results.extend(parsed)
            except Exception as e:
                logger.warning("第%d页提取失败: %s\n%s", p["page_num"], e, traceback.format_exc())
    else:
        # 聚合提取: 合并文本一次提交
        try:
            combined = "\n\n---\n\n".join([
                f"【第{p['page_num']}页】\n{p['text'][:1500]}"
                for p in page_objs
            ])
            system = SYSTEM_EXTRACT_AGGREGATED.format(topic=topic, start=start, end=end)
            raw = llm_invoke(system, combined)
            parsed = _parse_llm_json(raw)
            if not parsed:
                logger.warning("聚合提取 [%d-%d] 解析失败: %s", start, end, raw[:100] if raw else "empty")
            if parsed and isinstance(parsed, list):
                for item in parsed:
                    item["source_file"] = source_file
                    item["source_page"] = start
                results.extend(parsed)
                logger.info("聚合提取 [%d-%d] 共 %d 个知识点 (节省 %d 次LLM调用)",
                           start, end, len(parsed), length - 1)
        except Exception as e:
            logger.warning("聚合提取 [%d-%d] 失败: %s，回退逐页", start, end, e)
            # 回退: 逐页
            for p in page_objs:
                try:
                    raw = llm_invoke(SYSTEM_EXTRACT, f"文档第{p['page_num']}页:\n{p['text'][:3000]}")
                    parsed = _parse_llm_json(raw)
                    if parsed and isinstance(parsed, list):
                        for item in parsed:
                            item["source_file"] = source_file
                            item["source_page"] = p["page_num"]
                        results.extend(parsed)
                except Exception:
                    pass

    # 去重 (基于标题) — 线程安全：lock 保护 check+set
    _titles_lock = getattr(_extract_range, "_titles_lock", None)
    if _titles_lock is None:
        import threading as _th
        _titles_lock = _th.Lock()
        _extract_range._titles_lock = _titles_lock
    deduped = []
    for item in results:
        t = item.get("title", "")
        if t:
            tl = t.lower()
            with _titles_lock:
                if tl not in existing_titles:
                    existing_titles.add(tl)
                    deduped.append(item)
    return deduped


def _search_and_supplement(item: dict) -> dict:
    """网络搜索补充知识点。"""
    if "信息不足" not in item.get("content", ""):
        return item
    query = f"{item['title']} {' '.join(item.get('aliases', []))}".strip()
    try:
        results = web_search(query, top_k=3)
        if results:
            context = "\n".join([f"- {r['snippet']}" for r in results if r.get("snippet")])
            if context:
                item["content"] = llm_invoke(
                    "你是一个知识补充助手。",
                    f"知识点: {item['title']}\n搜索结果:\n{context}\n请生成详细解释(100-300字)。"
                ).strip()
                item["_web_sourced"] = True
    except Exception:
        pass
    return item


def run_import_workflow(
    file_path: str,
    filename: str,
    progress_callback: Optional[Callable] = None,
) -> ImportResult:
    """三阶段导入流水线: 预扫描 → 智能提取 → 增量入库。"""
    def emit(event: dict):
        if progress_callback:
            try: progress_callback(event)
            except Exception: pass

    all_cards = []
    card_creates = []
    all_failed = []

    try:
        # ═══════════════════════════════════════════════════
        # Phase 1: 文档预扫描
        # ═══════════════════════════════════════════════════
        emit({"type": "progress", "stage": "scan", "status": "started"})
        scanner = DocumentScanner()
        scan_result = scanner.scan(file_path)
        # scanner.scan() 内部已调用 parse_document，结果缓存在 scan_result.pages 中

        emit({"type": "progress", "stage": "scan", "status": "ok",
              "total": scan_result.total_pages,
              "valid": len(scan_result.valid_ranges),
              "skipped": len(scan_result.skipped_pages),
              "doc_type": scan_result.doc_type})

        # 复用 scanner 已解析的页面，避免二次解析
        pages = scan_result.pages

        if not scan_result.valid_ranges:
            logger.warning("无有效内容区间: %s", filename)
            return ImportResult(total=0)

        # ═══════════════════════════════════════════════════
        # Phase 2: 智能并发提取
        # ═══════════════════════════════════════════════════
        emit({"type": "progress", "stage": "extract", "status": "started",
              "total": len(scan_result.valid_ranges)})

        existing_titles = set()
        # 加载已有标题用于去重
        try:
            existing, _ = card_service.list_cards_sync(limit=5000)
            for c in existing:
                existing_titles.add(c.title.lower())
                for a in c.aliases:
                    existing_titles.add(a.lower())
        except Exception:
            pass

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {}
            for r_idx, (start, end, topic) in enumerate(scan_result.valid_ranges):
                future = pool.submit(
                    _extract_range, pages, start, end, topic,
                    filename, existing_titles,
                )
                futures[future] = (r_idx, start, end, topic)

            for future in as_completed(futures):
                r_idx, start, end, topic = futures[future]
                try:
                    items = future.result()
                    emit({"type": "progress", "stage": "extract",
                          "range": r_idx + 1, "total": len(scan_result.valid_ranges),
                          "page": start, "status": "ok", "count": len(items)})

                    # ══════════════════════════════════════
                    # Phase 3: 增量入库（提取一条入一条）
                    # ══════════════════════════════════════
                    for item in items:
                            card_creates.append(CardCreate(
                                title=item.get("title", "未命名"),
                                aliases=item.get("aliases", []),
                                content=item.get("content", ""),
                                examples=item.get("examples", []),
                                questions=item.get("questions", []),
                                category=item.get("category", "未分类"),
                                source_file=item.get("source_file", filename),
                                source_page=item.get("source_page", 0),
                            ))

                except Exception as e:
                    logger.warning("区间 [%d-%d] 处理失败: %s", start, end, e)
                    all_failed.append({"title": f"区间[{start}-{end}]", "reason": str(e)})

        # ═══════════════════════════════════════════════════
        # 网络搜索补充（后台异步）
        # ═══════════════════════════════════════════════════
        # 批量导入
        if card_creates:
            result = card_service.batch_import_sync(card_creates)
            all_cards = result.success
            all_failed.extend(result.failed)
            emit({"type": "progress", "stage": "card_generate", "status": "ok",
                  "imported": len(result.success), "failed": len(result.failed)})

        logger.info("导入完成: %s → %d 成功, %d 失败", filename, len(all_cards), len(all_failed))
        return ImportResult(
            total=len(all_cards) + len(all_failed),
            success=all_cards,
            failed=all_failed,
        )

    except Exception as e:
        logger.error("导入异常: %s\n%s", e, traceback.format_exc())
        return ImportResult(total=len(all_cards), success=all_cards,
                            failed=all_failed + [{"reason": str(e)}])


# ═══════════════════════════════════════════════════════════
# 2. 问答工作流
# ═══════════════════════════════════════════════════════════

def _qa_search_worker(question: str) -> list[dict]:
    cards = card_service.search_cards_sync(question, top_k=RETRIEVAL_TOP_K)
    return [c.model_dump() for c, _ in cards]


def _qa_answer_worker(question: str, cards_data: list[dict], history: list[dict]) -> str:
    ctx = ""
    if cards_data:
        for c in cards_data:
            ctx += f"## {c['title']}\n{c['content']}\n"
            if c.get("examples"):
                ctx += f"案例: {'; '.join(c['examples'][:2])}\n"
    else:
        ctx = "（知识库中未找到相关信息）"
    hist_text = "\n".join([
        f"{'用户' if m.get('role')=='user' else '助手'}: {m['content']}"
        for m in history[-6:]
    ])
    return llm_invoke(SYSTEM_QA, f"""对话历史:\n{hist_text}\n\n知识库:\n{ctx}\n\n问题: {question}""").strip()


def run_qa_workflow(
    question: str,
    chat_history: Optional[list[dict]] = None,
    progress_callback: Optional[Callable] = None,
) -> str:
    def emit(event: dict):
        if progress_callback:
            try: progress_callback(event)
            except Exception: pass

    emit({"type": "progress", "stage": "qa_search", "status": "started"})
    try:
        cards = _qa_search_worker(question)
        emit({"type": "progress", "stage": "qa_search", "status": "ok", "total": len(cards)})
        emit({"type": "progress", "stage": "qa_answer", "status": "started"})
        answer = _qa_answer_worker(question, cards, chat_history or [])
        emit({"type": "progress", "stage": "qa_answer", "status": "ok"})
        return answer
    except Exception as e:
        logger.error("问答异常: %s", e)
        return f"抱歉，回答生成失败: {e}"


# ═══════════════════════════════════════════════════════════
# 3. 卡片修改
# ═══════════════════════════════════════════════════════════

async def modify_card(card_id: str, instruction: str, progress_callback=None) -> Optional[dict]:
    card = await card_service.get_card(card_id)
    if not card:
        return None
    prompt = f"""当前卡片:\n标题: {card.title}\n内容: {card.content}\n案例: {'; '.join(card.examples)}\n问题: {'; '.join(card.questions)}\n分类: {card.category}\n\n修改指令: {instruction}"""
    try:
        result = _parse_llm_json(llm_invoke(SYSTEM_MODIFY, prompt))
        if not result:
            return None
        from bobanana.models import CardUpdate
        update = {}
        for f in ["title", "aliases", "content", "examples", "questions", "category"]:
            if f in result and result[f] is not None:
                update[f] = result[f]
        updated = await card_service.update_card(card.id, CardUpdate(**update))
        return updated.model_dump() if updated else None
    except Exception as e:
        logger.error("修改失败: %s", e)
        return None
