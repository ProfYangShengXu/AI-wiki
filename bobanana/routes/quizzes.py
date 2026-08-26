"""Quiz 卡片 API — 永久保存的测验条目(Quiz 页 + Agent 共用)。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from bobanana import quiz_store
from bobanana.models import ApiResponse

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


class QuizQuestionPayload(BaseModel):
    question: str = ""
    ref_answer: str = ""
    user_answer: str = ""
    score: int | None = None
    comment: str = ""


class QuizCardCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    card_ids: list[str] = Field(default_factory=list)
    questions: list[QuizQuestionPayload] = Field(default_factory=list)
    source: str = "agent"


class QuizCardUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    card_ids: list[str] | None = None
    questions: list[QuizQuestionPayload] | None = None
    status: str | None = None
    submitted: bool | None = None
    user_edited: bool | None = None


@router.get("", response_model=ApiResponse)
async def list_quizzes(card_id: str = ""):
    """列出 quiz 卡片(可按关联卡片过滤)。"""
    quizzes = quiz_store.list_quiz_cards(card_id=card_id or None, limit=500)
    return ApiResponse(status="success", data={"quizzes": quizzes})


@router.get("/{quiz_id}", response_model=ApiResponse)
async def get_quiz(quiz_id: str):
    quiz = quiz_store.get_quiz_card(quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail=f"Quiz「{quiz_id[:8]}」不存在")
    return ApiResponse(status="success", data=quiz)


@router.post("", response_model=ApiResponse, status_code=201)
async def create_quiz(data: QuizCardCreate):
    """新建 quiz 卡片(Agent 入库 / 前端手动保存共用)。"""
    questions = [q.model_dump() for q in data.questions]
    quiz = quiz_store.create_quiz_card(
        title=data.title.strip(),
        card_ids=data.card_ids,
        questions=questions,
        source=data.source,
    )
    return ApiResponse(
        status="success",
        message="Quiz 已保存",
        data=quiz,
    )


@router.put("/{quiz_id}", response_model=ApiResponse)
async def update_quiz(quiz_id: str, data: QuizCardUpdate):
    """更新 quiz 卡片(编辑题目/答案/状态, 支持中途修改)。"""
    payload = data.model_dump(exclude_unset=True)
    if "questions" in payload:
        payload["questions"] = [q.model_dump() for q in data.questions or []]
    quiz = quiz_store.update_quiz_card(quiz_id, **payload)
    if not quiz:
        raise HTTPException(status_code=404, detail=f"Quiz「{quiz_id[:8]}」不存在")
    return ApiResponse(
        status="success",
        message="Quiz 已更新",
        data=quiz,
    )


@router.delete("/{quiz_id}", response_model=ApiResponse)
async def delete_quiz(quiz_id: str):
    ok = quiz_store.delete_quiz_card(quiz_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Quiz「{quiz_id[:8]}」不存在")
    return ApiResponse(status="success", message="Quiz 已删除", data={"deleted": True})
