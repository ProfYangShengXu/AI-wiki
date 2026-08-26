"""执行层工具 — 所有功能定义 JSON Schema + 执行函数。"""

import json as _json
import logging
import re
import typing
from pathlib import Path

from pydantic import Field, create_model

from bobanana.models import CardCreate, CardUpdate
from bobanana.service.card_service import card_service
from bobanana.tools import llm_invoke, web_search

logger = logging.getLogger(__name__)


def _uploads_dir() -> Path:
    from bobanana.config import UPLOAD_DIR
    return UPLOAD_DIR


def _list_uploads() -> list[str]:
    """列出 uploads 目录中的文件名(供 agent 定位已上传文档)。"""
    try:
        d = _uploads_dir()
        if not d.exists():
            return []
        return sorted(p.name for p in d.iterdir() if p.is_file())
    except Exception:
        return []


def _resolve_uploaded_file(hint: str):
    """在 uploads 目录按文件名/关键词模糊匹配已上传文件。

    返回匹配的 Path 或 None。hint 可能是完整文件名、storage_name 或文件名片段。
    """
    from pathlib import Path
    hint = (hint or "").strip().lower()
    if not hint:
        return None
    d = _uploads_dir()
    if not d.exists():
        return None
    try:
        files = [p for p in d.iterdir() if p.is_file()]
    except Exception:
        return None
    # 1) 精确匹配
    for p in files:
        if p.name.lower() == hint:
            return p
    # 2) 文件名包含 hint
    for p in files:
        if hint in p.name.lower():
            return p
    # 3) hint 包含文件名
    for p in files:
        if p.name.lower() in hint:
            return p
    return None

# ═══════════════════════════════════════════════════════════
# 工具 Schema 定义 (Function Calling 格式)
# ═══════════════════════════════════════════════════════════

TOOLS: list[dict] = [
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
        "description": "修改已有知识卡片的内容、标题、分类、别名或案例。",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id_or_title": {"type": "string", "description": "要修改的卡片ID或标题"},
                "title": {"type": "string", "description": "新标题"},
                "content": {"type": "string", "description": "新内容"},
                "category": {"type": "string", "description": "新分类"},
                "aliases": {"type": "array", "items": {"type": "string"}, "description": "新别名列表"},
                "examples": {"type": "array", "items": {"type": "string"}, "description": "新案例列表"}
            },
            "required": ["card_id_or_title"]
        }
    },
    {
        "name": "delete_card",
        "description": "删除一张知识卡片。",
        "approval_required": True,
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
        "description": "导入文档(PDF/Word/MD/TXT)到知识库。传入文件名即可(会自动在 uploads 目录匹配已上传文件), 不要编造完整路径。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文档文件名或路径(前端上传后的文件名)"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "start_quiz",
        "description": "为指定的知识卡片生成 Quiz 测验题, 并作为 quiz 卡片永久保存到 Quiz 页(返回 quiz_id 供后续读取/评分)。",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id_or_title": {"type": "string", "description": "卡片ID或标题"}
            },
            "required": ["card_id_or_title"]
        }
    },
    {
        "name": "read_quiz",
        "description": "读取已保存的 quiz 卡片内容(题目/参考答案/用户答案/评分/提交状态/创建时间)。传 quiz_id 精确读取; 传 card_id_or_title 按关联卡片筛选; 都不传则列出全部 quiz。",
        "parameters": {
            "type": "object",
            "properties": {
                "quiz_id": {"type": "string", "description": "quiz 卡片 ID(可选)"},
                "card_id_or_title": {"type": "string", "description": "关联知识卡片 ID 或标题(可选)"}
            },
            "required": []
        }
    },
    {
        "name": "grade_quiz",
        "description": "对用户的 Quiz 答案进行 AI 评分, 并写回 quiz 卡片(提交状态+答案+评分, 若该卡只有一个 quiz 可不传 quiz_id)。",
        "parameters": {
            "type": "object",
            "properties": {
                "quiz_id": {"type": "string", "description": "quiz 卡片 ID(可选, 该卡有多个 quiz 时建议传)"},
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
                "category_names": {"type": "array", "items": {"type": "string"},
                                 "description": "要组卷的分类名称列表"},
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

        elif tool_name == "upload_document":
            from pathlib import Path
            file_path = str(params.get("file_path") or "")
            p = Path(file_path)
            if not p.is_file():
                # 容错: 在 uploads 目录按文件名/关键词模糊搜索
                resolved = _resolve_uploaded_file(file_path)
                if resolved is None:
                    return {
                        "error": f"文件不存在: {file_path}。请先在前端上传文档, 或提供 uploads 目录中的文件名",
                        "uploads": _list_uploads(),
                    }
                p = resolved
            from bobanana.agent import run_import_workflow
            result = run_import_workflow(str(p), p.name)
            return {
                "status": "imported",
                "file": p.name,
                "imported": len(result.success),
                "failed": len(result.failed),
                "cards": [c.title for c in result.success],
                "errors": [f.get("reason") for f in result.failed],
            }

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
返回: {{"title","aliases","content(400-600字含比喻+关联)",
"examples":["string"],"questions":["string"],"category":"{category}"}}"""
                    raw = llm_invoke("只返回 JSON。", prompt, timeout_sec=30)
                    parsed = _clean_json(raw)
                    if parsed and isinstance(parsed, dict) and "error" not in parsed:
                        content = parsed.get("content", "")
                        llm_examples = parsed.get("examples", [])
                        if not examples and llm_examples:
                            examples = [
                                str(e) if isinstance(e, str)
                                else str(e.get(list(e.keys())[0], e)) if isinstance(e, dict)
                                else str(e)
                                for e in llm_examples
                            ]
                except Exception as e:
                    logger.warning("LLM auto-fill failed: %s", e)

            # 确保 examples 是字符串列表
            safe_examples = []
            for example in (examples or []):
                if isinstance(example, str):
                    safe_examples.append(example)
                elif isinstance(example, dict):
                    safe_examples.append(str(example.get(list(example.keys())[0], example)))
                else:
                    safe_examples.append(str(example))

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
            for f in ["title", "content", "category", "aliases", "examples"]:
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
            # 永久保存为 quiz 卡片(Quiz 页可见)
            from bobanana import quiz_store
            quiz = quiz_store.create_quiz_card(
                title=card.title,
                card_ids=[card.id],
                questions=qs,
                source="agent",
            )
            return {
                "quiz_id": quiz["id"],
                "card_id": card.id,
                "card_title": card.title,
                "questions": qs,
                "saved": True,
            }

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
            # 掌握度落库(与 Quiz 页一致, 重启不丢)
            from bobanana.routes.quiz import _mastery, _save_mastery
            m = _mastery.setdefault(card.id, {"attempts": 0, "score": 0})
            m["attempts"] += 1
            total = sum(r.get("score", 5) for r in results) if results else 0
            m["score"] = max(m["score"], total)
            m["max_score"] = max(int(m.get("max_score") or 0), len(results) * 10)
            _save_mastery(_mastery)
            # 写回 quiz 卡片(提交状态 + 答案 + 评分)
            from bobanana import quiz_store
            target_quiz = None
            quiz_id = params.get("quiz_id") or ""
            if quiz_id:
                target_quiz = quiz_store.get_quiz_card(quiz_id)
            else:
                linked = quiz_store.list_quiz_cards(card_id=card.id)
                if len(linked) == 1:
                    target_quiz = linked[0]
            if target_quiz:
                answers_map = {a["question"]: a["answer"] for a in params["answers"]}
                qlist = target_quiz.get("questions") or []
                res_map = {r.get("question", ""): r for r in (results or [])}
                merged = []
                for q in qlist:
                    qq = dict(q)
                    qq["user_answer"] = answers_map.get(q.get("question", ""), qq.get("user_answer", ""))
                    r = res_map.get(q.get("question", ""))
                    if r:
                        qq["score"] = r.get("score", qq.get("score"))
                        qq["comment"] = r.get("comment", qq.get("comment", ""))
                        qq["ref_answer"] = r.get("reference", qq.get("ref_answer", ""))
                    merged.append(qq)
                quiz_store.update_quiz_card(
                    target_quiz["id"], questions=merged,
                    submitted=True, status="graded",
                )
            return {
                "quiz_id": target_quiz["id"] if target_quiz else "",
                "results": results, "total": total, "max_score": len(results)*10,
                "saved": bool(target_quiz),
            }

        elif tool_name == "read_quiz":
            from bobanana import quiz_store
            quiz_id = params.get("quiz_id") or ""
            card_hint = params.get("card_id_or_title") or ""
            if quiz_id:
                q = quiz_store.get_quiz_card(quiz_id)
                if not q:
                    return {"error": f"未找到 quiz: {quiz_id[:8]}"}
                return q
            if card_hint:
                card = _find_card(card_hint)
                if not card:
                    return {"error": f"未找到卡片: {card_hint}"}
                quizzes = quiz_store.list_quiz_cards(card_id=card.id)
                if not quizzes:
                    return {"error": f"卡片「{card.title}」暂无 quiz", "card_id": card.id}
                return {"card_id": card.id, "card_title": card.title, "quizzes": quizzes}
            quizzes = quiz_store.list_quiz_cards()
            return {
                "count": len(quizzes),
                "quizzes": [
                    {"id": q["id"], "title": q["title"], "status": q["status"],
                     "submitted": q["submitted"], "created_at": q["created_at"],
                     "card_ids": q["card_ids"], "question_count": len(q.get("questions") or [])}
                    for q in quizzes
                ],
            }

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
            if not card: return {"error": "未找到卡片"}
            from bobanana.routes.quiz import _mastery
            m = _mastery.get(card.id, {"attempts": 0, "score": 0})
            from bobanana.routes.quiz import _mastery_percent
            pct = _mastery_percent(m)
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

def _clean_json(raw: str) -> dict | None:
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    m = re.search(r"(\{.*\})", clean, re.DOTALL)
    if m: clean = m.group(1)
    try: return _json.loads(clean)
    except Exception: return None


def _parse_json_array(raw: str) -> list:
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    m = re.search(r"(\[.*\])", clean, re.DOTALL)
    if m: clean = m.group(1)
    try:
        result = _json.loads(clean)
        return result if isinstance(result, list) else [result]
    except Exception: return []


# ═══════════════════════════════════════════════════════════
# 工具参数 Pydantic 模型 (Phase 2: 结构化校验)
# ═══════════════════════════════════════════════════════════

def _schema_type_to_py(prop: dict) -> typing.Any:
    """将 JSON Schema 的 type 映射为 Python 类型。"""
    t = prop.get("type", "string")
    if t == "string":
        return str
    if t == "integer":
        return int
    if t == "number":
        return float
    if t == "boolean":
        return bool
    if t == "array":
        items = prop.get("items") or {}
        return list[_schema_type_to_py(items)]  # type: ignore[misc]  # 运行时动态构造 List[元素类型]
    if t == "object":
        return dict
    return typing.Any


def _build_model_for_tool(tool: dict):
    """根据工具 JSON Schema 生成 Pydantic 模型。"""
    params = tool.get("parameters") or {}
    properties = params.get("properties") or {}
    required = set(params.get("required") or [])

    fields = {}
    for name, prop in properties.items():
        py_type = _schema_type_to_py(prop)
        description = prop.get("description", "")
        if name in required:
            fields[name] = (py_type, Field(..., description=description))
        else:
            default = prop.get("default", None)
            fields[name] = (py_type, Field(default=default, description=description))

    model_name = "Tool_" + tool["name"]
    return create_model(model_name, **fields)


# 工具名 → Pydantic 模型
TOOL_PYDANTIC_MODELS: dict[str, type] = {
    t["name"]: _build_model_for_tool(t) for t in TOOLS
}


def validate_tool_args(tool_name: str, params) -> tuple:
    """校验工具参数, 返回 (ok, model|error)。

    - ok=True 时返回 (True, Pydantic 模型实例);
    - ok=False 时返回 (False, 错误信息字符串)。
    """
    model = TOOL_PYDANTIC_MODELS.get(tool_name)
    if model is None:
        return False, f"未知工具: {tool_name}"
    try:
        data = params if isinstance(params, dict) else {}
        validated = model(**data)
        return True, validated
    except Exception as e:
        return False, str(e)


def tool_requires_approval(tool_name: str) -> bool:
    """判断工具是否需要审批。"""
    for t in TOOLS:
        if t["name"] == tool_name:
            return bool(t.get("approval_required", False))
    return False
