"""执行层工具 — 所有功能定义 JSON Schema + 执行函数。"""

import asyncio
import json as _json
import re
import logging
from typing import Any, Callable, Optional

from bobanana.service.card_service import card_service
from bobanana.models import CardCreate, CardUpdate
from bobanana.tools import llm_invoke, web_search

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# 工具 Schema 定义 (Function Calling 格式)
# ═══════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "search_knowledge",
        "description": "搜索知识库，根据关键词查找相关的知识卡片。返回卡片标题、内容和来源出处。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "list_categories",
        "description": "列出知识库中所有分类。",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "get_card",
        "description": "获取指定知识卡片的完整内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id_or_title": {"type": "string", "description": "卡片ID或标题"}
            },
            "required": ["card_id_or_title"]
        }
    },
    {
        "name": "create_card",
        "description": "创建一张新的知识卡片。如果只给标题不给内容，系统会自动用 AI 填充详细内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "知识点标题"},
                "category": {"type": "string", "description": "分类", "default": "未分类"},
                "content": {"type": "string", "description": "详细内容（可选，不填则AI自动生成）"},
                "examples": {"type": "array", "items": {"type": "string"}, "description": "案例列表"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "update_card",
        "description": "修改已有知识卡片的内容、标题或分类。",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id_or_title": {"type": "string", "description": "要修改的卡片ID或标题"},
                "title": {"type": "string", "description": "新标题"},
                "content": {"type": "string", "description": "新内容"},
                "category": {"type": "string", "description": "新分类"},
                "examples": {"type": "array", "items": {"type": "string"}, "description": "新案例列表"}
            },
            "required": ["card_id_or_title"]
        }
    },
    {
        "name": "delete_card",
        "description": "删除一张知识卡片。",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id_or_title": {"type": "string", "description": "要删除的卡片ID或标题"}
            },
            "required": ["card_id_or_title"]
        }
    },
    {
        "name": "upload_document",
        "description": "上传文档(PDF/Word/MD)导入知识库。接受文件路径。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文档路径（由用户指定或前端上传后传入）"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "start_quiz",
        "description": "为指定的知识卡片生成 Quiz 测验题。",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id_or_title": {"type": "string", "description": "卡片ID或标题"}
            },
            "required": ["card_id_or_title"]
        }
    },
    {
        "name": "grade_quiz",
        "description": "对用户的 Quiz 答案进行 AI 评分。",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string", "description": "卡片ID"},
                "answers": {"type": "array", "items": {"type": "object", "properties": {
                    "question": {"type": "string"}, "answer": {"type": "string"}
                }}, "description": "用户答案列表"}
            },
            "required": ["card_id", "answers"]
        }
    },
    {
        "name": "create_exam",
        "description": "从多个分类中选择卡片生成综合试卷。",
        "parameters": {
            "type": "object",
            "properties": {
                "category_names": {"type": "array", "items": {"type": "string"}, "description": "要组卷的分类名称列表"},
                "topic": {"type": "string", "description": "考试主题（可选）"}
            },
            "required": ["category_names"]
        }
    },
    {
        "name": "get_mastery",
        "description": "查看某张卡片的掌握度。",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id_or_title": {"type": "string", "description": "卡片ID或标题"}
            },
            "required": ["card_id_or_title"]
        }
    },
    {
        "name": "web_search_enrich",
        "description": "网络搜索补充知识（仅在知识库信息不足时使用）。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"}
            },
            "required": ["query"]
        }
    }
]


# ═══════════════════════════════════════════════════════════
# 工具执行函数
# ═══════════════════════════════════════════════════════════

def _search_knowledge(query: str) -> dict:
    """搜索知识库。"""
    cards = card_service.search_cards_sync(query, top_k=5)
    results = [c.model_dump() for c, _ in cards]
    return {"query": query, "count": len(results), "results": results[:5]}


def _find_card(card_id_or_title: str):
    """根据 ID 或标题模糊查找卡片。"""
    # 先尝试 ID
    card = card_service.get_card_sync(card_id_or_title)
    if card: return card
    # 再搜索标题
    cards, _ = card_service.list_cards_sync(limit=1000)
    for c in cards:
        if card_id_or_title.lower() in c.title.lower():
            return c
    return None


def execute_tool(tool_name: str, params: dict) -> dict:
    """执行工具调用并返回结果。"""
    try:
        if tool_name == "search_knowledge":
            return _search_knowledge(params["query"])

        elif tool_name == "list_categories":
            cats = card_service.get_categories_sync()
            return {"categories": cats, "count": len(cats)}

        elif tool_name == "get_card":
            card = _find_card(params["card_id_or_title"])
            if not card:
                return {"error": f"未找到卡片: {params['card_id_or_title']}"}
            return {"card": card.model_dump()}

        elif tool_name == "create_card":
            title = params["title"]
            category = params.get("category", "未分类")
            content = params.get("content", "")
            examples = params.get("examples", [])

            if not content:
                try:
                    prompt = f"""为知识点生成完整卡片 JSON:
标题: {title}
分类: {category}
返回: {{"title","aliases","content(400-600字含比喻+关联)","examples":["string"],"questions":["string"],"category":"{category}"}}"""
                    raw = llm_invoke("只返回 JSON。", prompt, timeout_sec=30)
                    parsed = _clean_json(raw)
                    if parsed and isinstance(parsed, dict) and "error" not in parsed:
                        content = parsed.get("content", "")
                        llm_examples = parsed.get("examples", [])
                        if not examples and llm_examples:
                            examples = [str(e) if isinstance(e, str) else str(e.get(list(e.keys())[0], e)) if isinstance(e, dict) else str(e) for e in llm_examples]
                except Exception as e:
                    logger.warning("LLM auto-fill failed: %s", e)

            # 确保 examples 是字符串列表
            safe_examples = []
            for e in (examples or []):
                if isinstance(e, str):
                    safe_examples.append(e)
                elif isinstance(e, dict):
                    safe_examples.append(str(e.get(list(e.keys())[0], e)))
                else:
                    safe_examples.append(str(e))

            card = card_service.create_card_sync(CardCreate(
                title=title, category=category, content=content or "",
                examples=safe_examples, source_file="agent"
            ))
            return {"status": "created", "card": card}

        elif tool_name == "update_card":
            card = _find_card(params["card_id_or_title"])
            if not card:
                return {"error": f"未找到卡片: {params['card_id_or_title']}"}
            update = {}
            for f in ["title", "content", "category", "examples"]:
                if f in params and params[f] is not None:
                    update[f] = params[f]
            card = card_service.update_card_sync(card.id, CardUpdate(**update))
            return {"status": "updated", "card": card.model_dump() if card else None}

        elif tool_name == "delete_card":
            card = _find_card(params["card_id_or_title"])
            if not card:
                return {"error": f"未找到卡片: {params['card_id_or_title']}"}
            card_service.delete_card_sync(card.id)
            return {"status": "deleted", "title": card.title}

        elif tool_name == "start_quiz":
            card = _find_card(params["card_id_or_title"])
            if not card:
                return {"error": f"未找到卡片: {params['card_id_or_title']}"}
            prompt = f"""为知识点生成 3-5 道简答题:
知识点: {card.title}
内容: {card.content[:1000]}
返回 JSON 数组: [{{"question":"","ref_answer":""}}]"""
            raw = llm_invoke("只返回 JSON 数组。", prompt, timeout_sec=30)
            qs = _parse_json_array(raw)
            return {"card_id": card.id, "card_title": card.title, "questions": qs}

        elif tool_name == "grade_quiz":
            card = card_service.get_card_sync(params["card_id"])
            if not card: return {"error": "卡片不存在"}
            qa_list = "\n".join([f"Q: {a['question']}\nA: {a['answer']}" for a in params["answers"]])
            prompt = f"""严格评分(0-10分):
知识点: {card.title}
知识: {card.content[:300]}
答案:
{qa_list}
返回 JSON 数组: [{{"score":8,"comment":"理由","reference":"参考答案"}}]"""
            raw = llm_invoke("只返回 JSON 数组。", prompt, timeout_sec=30)
            results = _parse_json_array(raw)
            from bobanana.routes.quiz import _mastery
            m = _mastery.setdefault(card.id, {"attempts": 0, "score": 0})
            m["attempts"] += 1
            total = sum(r.get("score", 5) for r in results) if results else 0
            m["score"] = max(m["score"], total)
            return {"results": results, "total": total, "max_score": len(results)*10}

        elif tool_name == "create_exam":
            cats = params.get("category_names", [])[:10]
            cards = []
            for cn in cats:
                clist, _ = card_service.list_cards_sync(category=cn, limit=3)
                cards.extend(clist)
            if not cards: return {"error": "无有效卡片"}
            topics = "\n".join([f"- {c.title}: {c.content[:150]}" for c in cards[:10]])
            prompt = f"""根据知识点组卷，生成 5-8 道综合简答题:
{topics}
返回 JSON 数组: [{{"question":"","ref_answer":"","related_cards":[""]}}]"""
            raw = llm_invoke("只返回 JSON 数组。", prompt, timeout_sec=30)
            qs = _parse_json_array(raw)
            return {"questions": qs, "card_count": len(cards)}

        elif tool_name == "get_mastery":
            card = _find_card(params["card_id_or_title"])
            if not card: return {"error": f"未找到卡片"}
            from bobanana.routes.quiz import _mastery
            m = _mastery.get(card.id, {"attempts": 0, "score": 0})
            total = max(m["attempts"] * 10, 1)
            pct = min(round(m["score"] / total * 100), 100)
            return {"card_title": card.title, "mastery_pct": pct, "attempts": m["attempts"]}

        elif tool_name == "web_search_enrich":
            results = web_search(params["query"], top_k=3)
            return {"results": results}

        else:
            return {"error": f"未知工具: {tool_name}"}

    except Exception as e:
        logger.error("工具执行失败 %s: %s", tool_name, e)
        return {"error": str(e)}


# ── 辅助函数 ──────────────────────────────────────────

def _clean_json(raw: str) -> Optional[dict]:
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    m = re.search(r"(\{.*\})", clean, re.DOTALL)
    if m: clean = m.group(1)
    try: return _json.loads(clean)
    except: return None


def _parse_json_array(raw: str) -> list:
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    m = re.search(r"(\[.*\])", clean, re.DOTALL)
    if m: clean = m.group(1)
    try:
        result = _json.loads(clean)
        return result if isinstance(result, list) else [result]
    except: return []
