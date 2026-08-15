"""测试替身：避免单元测试依赖真实 LLM / Embedding / 网络。"""

from __future__ import annotations

import hashlib
import json
import re

# ── Quiz 默认响应 ──────────────────────────────────────────
# 供 FakeLLM 在无显式覆盖时, 对「出题专家 / 评分老师」prompt 返回合法 JSON。

QUIZ_QUESTION_DEFAULTS: list[dict] = [
    {
        "question": "请用自己的话概括该知识点的核心概念。",
        "ref_answer": "该知识点的核心概念是对其本质的一句话准确概括。",
    },
    {
        "question": "请举一个能说明该知识点的实际应用案例。",
        "ref_answer": "一个贴近实际的案例可以直观说明该知识点的应用场景。",
    },
    {
        "question": "该知识点与哪些前置或后续知识存在联系？",
        "ref_answer": "它与若干前置知识和后续知识存在递进或对比关系。",
    },
]

GRADE_ITEM_DEFAULT: dict = {
    "score": 8,
    "comment": "回答基本正确、要点完整，可再补充细节以更全面。",
    "reference": "更完整、更严谨的参考答案。",
}


def _count_answers(user_prompt: str) -> int:
    """按评分 prompt 中「A1: / A2: ...」行数估算答案条数, 至少 1。"""
    n = len(re.findall(r"(?m)^A\d+:", user_prompt))
    return n if n > 0 else 1


class FakeLLM:
    """按 prompt 关键字返回预置 JSON 的 LLM 替身。

    优先使用显式传入的 responses 字典; 未命中时对 Quiz 场景提供默认响应:
    - prompt 含「出题专家」→ 返回 3 题的 JSON 数组 [{question, ref_answer}];
    - prompt 含「评分老师」→ 返回与答案数匹配的 [{score, comment, reference}]。
    """

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system_prompt: str, user_prompt: str, timeout_sec: int | None = None) -> str:
        self.calls.append((system_prompt, user_prompt))
        for keyword, response in self.responses.items():
            if keyword in user_prompt or keyword in system_prompt:
                return response
        # Quiz 默认响应 (无显式覆盖时)
        if "出题专家" in system_prompt or "出题专家" in user_prompt:
            return json.dumps(QUIZ_QUESTION_DEFAULTS, ensure_ascii=False)
        if "评分老师" in system_prompt or "评分老师" in user_prompt:
            return json.dumps(
                [dict(GRADE_ITEM_DEFAULT) for _ in range(_count_answers(user_prompt))],
                ensure_ascii=False,
            )
        return "[]"


class FakeEmbeddings:
    """确定性哈希向量，维度可配置。"""

    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.calls: list[str] = []

    def __call__(self, text: str) -> list[float]:
        self.calls.append(text)
        vector = []
        for index in range(self.dimension):
            digest = hashlib.sha256(f"{index}:{text}".encode()).digest()
            value = (digest[0] / 255.0) * 2.0 - 1.0
            vector.append(value)
        norm = max(1e-9, sum(v * v for v in vector) ** 0.5)
        return [v / norm for v in vector]


def fake_llm_json_array(items: list[dict]) -> str:
    return json.dumps(items, ensure_ascii=False)


def patch_llm(monkeypatch, responses: dict[str, str]) -> FakeLLM:
    fake = FakeLLM(responses)
    monkeypatch.setattr("bobanana.tools.llm_invoke", fake)
    monkeypatch.setattr("bobanana.agent.llm_invoke", fake)
    monkeypatch.setattr("bobanana.agent_react.llm_invoke", fake)
    monkeypatch.setattr("bobanana.routes.cards.llm_invoke", fake)
    monkeypatch.setattr("bobanana.routes.quiz.llm_invoke", fake)
    return fake


def patch_embeddings(monkeypatch, dimension: int = 384) -> FakeEmbeddings:
    fake = FakeEmbeddings(dimension)
    monkeypatch.setattr("bobanana.tools.embed_text", fake)
    monkeypatch.setattr("bobanana.service.card_service.embed_text", fake)
    return fake
