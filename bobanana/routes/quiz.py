"""Quiz API — 生成题目 / AI评分 / 掌握度追踪。"""

import json as _json
import re
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from bobanana.models import ApiResponse
from bobanana.service.card_service import card_service
from bobanana.tools import llm_invoke

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/quiz", tags=["quiz"])

# ── 本地掌握度存储 (进程重启丢失，后续可持久化) ──────
_mastery: dict[str, dict] = {}  # card_id -> {total: int, score: int, attempts: int}


# ── Request / Response Models ──────────────────────────

class QuizAnswer(BaseModel):
    """用户提交的答案。"""
    question: str = ""
    answer: str = ""


class QuizSubmission(BaseModel):
    card_id: str
    answers: list[QuizAnswer]


class QuizResult(BaseModel):
    question: str
    answer: str
    score: int  # 0-10
    comment: str  # LLM 评分理由 + 详解
    reference: str = ""  # 参考答案


class ExamRequest(BaseModel):
    card_ids: list[str]


# ── 工具函数 ──────────────────────────────────────────

def _clean_json(raw: str) -> Optional[dict]:
    """清理 LLM JSON 响应。"""
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    m = re.search(r"(\{.*\})", clean, re.DOTALL)
    if m: clean = m.group(1)
    try: return _json.loads(clean)
    except Exception: return None


# ── 端点 ──────────────────────────────────────────────

@router.get("/mastery/{card_id}")
async def get_mastery(card_id: str):
    """获取某张卡片的掌握度。"""
    m = _mastery.get(card_id, {"attempts": 0, "score": 0})
    total = max(m.get("attempts", 0) * 10, 1)
    pct = round(m.get("score", 0) / total * 100)
    return {"status": "success", "data": {
        "card_id": card_id,
        "attempts": m.get("attempts", 0),
        "score": m.get("score", 0),
        "mastery_pct": min(pct, 100),
    }}


@router.get("/mastery/batch", response_model=ApiResponse)
async def get_batch_mastery(card_ids: str = ""):
    """批量获取掌握度。"""
    ids = [i.strip() for i in card_ids.split(",") if i.strip()]
    result = {}
    for cid in ids:
        m = _mastery.get(cid, {"attempts": 0, "score": 0})
        total = max(m.get("attempts", 0) * 10, 1)
        pct = round(m.get("score", 0) / total * 100)
        result[cid] = min(pct, 100)
    return ApiResponse(status="success", data={"mastery": result})


@router.post("/generate/{card_id}")
async def generate_quiz(card_id: str):
    """生成 3-5 道简答题。"""
    card = await card_service.get_card(card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")

    loop = asyncio.get_event_loop()

    def _gen():
        prompt = f"""你是严格的出题专家。根据以下知识点生成 3-5 道简答题(每题需用一句话清晰回答,考察理解深度)。

知识点: {card.title}
内容: {card.content[:1000]}
案例: {'; '.join(card.examples[:2])}

返回 JSON 数组,每题格式:
[
  {{"question": "题目", "ref_answer": "参考答案(一句话)"}},
  ...
]"""
        return llm_invoke("你是出题专家。只返回 JSON 数组。", prompt)

    try:
        raw = await loop.run_in_executor(None, _gen)
        clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
        m = re.search(r"(\[.*\])", clean, re.DOTALL)
        if m: clean = m.group(1)
        questions = _json.loads(clean)
        if not isinstance(questions, list):
            raise ValueError("非数组")
        return ApiResponse(status="success", data={"card_id": card_id, "questions": questions})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败: {e}")


@router.post("/grade")
async def grade_quiz(submission: QuizSubmission):
    """LLM 评分简答题。"""
    card = await card_service.get_card(submission.card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")

    loop = asyncio.get_event_loop()

    def _grade():
        qa_list = ""
        for i, a in enumerate(submission.answers):
            qa_list += f"Q{i+1}: {a.question}\nA{i+1}: {a.answer}\n\n"

        prompt = f"""你是严肃的评分老师。根据以下知识点，对学生的答案进行严格评分(0-10分, 10=完全正确无遗漏)。

知识点: {card.title}
知识内容: {card.content[:500]}

学生答案:
{qa_list}

返回 JSON 数组，每题一个对象:
[
  {{"score": 8, "comment": "得分理由和详解(50-150字)", "reference": "更完整的参考答案(简要)"}},
  ...
]

要求:
1. 严格评分, 不全对就是 5-8 分, 完全跑题 0-3 分
2. comment 必须包含评分理由 + 知识补充
3. 只返回 JSON 数组"""
        return llm_invoke("你是评分老师。只返回 JSON 数组。", prompt)

    try:
        raw = await loop.run_in_executor(None, _grade)
        clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
        m = re.search(r"(\[.*\])", clean, re.DOTALL)
        if m: clean = m.group(1)
        results = _json.loads(clean)

        # 计算总分
        total_score = 0
        max_score = len(results) * 10
        graded = []
        for i, r in enumerate(results):
            sc = min(10, max(0, int(r.get("score", 5))))
            total_score += sc
            graded.append(QuizResult(
                question=submission.answers[i].question if i < len(submission.answers) else "",
                answer=submission.answers[i].answer if i < len(submission.answers) else "",
                score=sc,
                comment=r.get("comment", ""),
                reference=r.get("reference", ""),
            ))

        # 更新掌握度
        m = _mastery.setdefault(submission.card_id, {"attempts": 0, "score": 0})
        m["attempts"] += 1
        m["score"] = max(m["score"], total_score)  # 保留最高分
        mastery_pct = min(round(total_score / max_score * 100), 100)

        return ApiResponse(status="success", data={
            "card_id": submission.card_id,
            "results": [r.model_dump() for r in graded],
            "total_score": total_score,
            "max_score": max_score,
            "mastery_pct": mastery_pct,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"评分失败: {e}")


@router.post("/merge/{card_id}")
async def merge_quiz_to_card(card_id: str, submission: QuizSubmission):
    """将 Quiz 的 Q&A 和评分反馈合并回知识卡片。"""
    card = await card_service.get_card(card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")

    loop = asyncio.get_event_loop()

    def _merge():
        qa_text = "\n".join([
            f"Q: {a.question}\nA: {a.answer}" for a in submission.answers
        ])
        prompt = f"""你是知识融合专家。将以下 Quiz 问答内容融合进知识卡片中。

原卡片:
标题: {card.title}
分类: {card.category}
内容: {card.content[:800]}
案例: {'; '.join(card.examples[:3])}

Quiz 问答:
{qa_text}

请返回改进后的卡片 JSON:
{{
  "content": "融合后的完整内容(保留原结构,补充 Quiz 中的知识点和常见误区,400-800字)",
  "examples": ["新案例1", "新案例2"],
  "aliases": ["别名..."]
}}"""
        return llm_invoke("你是知识编辑。只返回 JSON。", prompt)

    try:
        raw = await loop.run_in_executor(None, _merge)
        parsed = _clean_json(raw)
        if not parsed or not isinstance(parsed, dict):
            raise HTTPException(status_code=500, detail="LLM 合并失败")

        from bobanana.models import CardUpdate
        update_data = {
            "content": parsed.get("content", card.content),
            "examples": parsed.get("examples", card.examples),
        }
        if parsed.get("aliases"):
            update_data["aliases"] = parsed["aliases"]

        updated = await card_service.update_card(card_id, CardUpdate(**update_data))
        return ApiResponse(status="success", data={"card": updated.model_dump()})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"合并失败: {e}")


@router.post("/exam")
async def create_exam(req: ExamRequest):
    """智能组卷：从选中的卡片生成综合试卷。"""
    cards = []
    for cid in req.card_ids:
        c = await card_service.get_card(cid)
        if c:
            cards.append(c)

    if not cards:
        raise HTTPException(status_code=400, detail="无有效卡片")

    loop = asyncio.get_event_loop()

    def _gen_exam():
        topics = "\n".join([f"- {c.title}: {c.content[:200]}" for c in cards[:10]])
        prompt = f"""你是出题专家。根据以下知识点组卷, 生成 5-8 道综合简答题(考察跨知识点联系)。

知识点列表:
{topics}

返回 JSON 数组:
[
  {{"question": "综合题", "ref_answer": "参考答案(2-3句话)", "related_cards": ["知识点1", "知识点2"]}},
  ...
]"""
        return llm_invoke("你是组卷专家。只返回 JSON 数组。", prompt)

    try:
        raw = await loop.run_in_executor(None, _gen_exam)
        clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
        m = re.search(r"(\[.*\])", clean, re.DOTALL)
        if m: clean = m.group(1)
        questions = _json.loads(clean)

        # 批量提升掌握度
        for c in cards:
            m = _mastery.setdefault(c.id, {"attempts": 0, "score": 0})
            m["attempts"] += 1
            m["score"] = min(m["score"] + 3, 10 * m["attempts"])

        return ApiResponse(status="success", data={
            "questions": questions,
            "card_ids": req.card_ids,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"组卷失败: {e}")
