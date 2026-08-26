"""Quiz 路由补充测试:merge 融合回卡片、exam 组卷、generate/grade 兜底。"""

import json

import pytest
from fastapi.testclient import TestClient

from bobanana.app import app
from bobanana.models import CardCreate
from bobanana.service.card_service import card_service


@pytest.fixture(autouse=True)
def isolated_quiz_db(tmp_path, monkeypatch):
    """generate 现在会写 quiz 卡片, 用独立 SQLite 避免污染真实 DATA_DIR。"""
    from bobanana import quiz_store
    monkeypatch.setattr(quiz_store, "DB_PATH", tmp_path / "quiz_cards.db")
    quiz_store.init_db()


@pytest.fixture
def quiz_env(monkeypatch):
    from tests.fakes import FakeLLM
    fake = FakeLLM()
    fake.responses["综合简答题"] = json.dumps([
        {"question": "综合题1", "ref_answer": "答案1", "related_cards": ["与门"]},
    ], ensure_ascii=False)
    fake.responses["知识融合"] = json.dumps({
        "content": "融合后的内容:与门是所有输入为1时输出为1的逻辑门,常见误区是把与门和或门混淆。",
        "examples": ["新案例A"], "aliases": ["AND门"],
    }, ensure_ascii=False)
    fake.responses["出题专家"] = json.dumps([
        {"question": "题目1", "ref_answer": "参考1"},
        {"question": "题目2", "ref_answer": "参考2"},
    ], ensure_ascii=False)
    monkeypatch.setattr("bobanana.routes.quiz.llm_invoke", fake)
    return fake


@pytest.fixture
def client():
    c = TestClient(app)
    yield c
    c.close()


def _create_card(title="与门"):
    card = card_service.create_card_sync(CardCreate(
        title=title, category="数字逻辑", content=f"{title}:所有输入为1时输出为1。",
        source_file="test",
    ))
    return card["id"]


def test_generate_quiz(quiz_env, client):
    cid = _create_card()
    r = client.post(f"/api/quiz/generate/{cid}")
    assert r.status_code == 200
    assert len(r.json()["data"]["questions"]) >= 2


def test_grade_quiz(quiz_env, client):
    cid = _create_card()
    fake = quiz_env
    fake.responses["评分老师"] = json.dumps([
        {"score": 9, "comment": "正确", "reference": "参考"},
    ], ensure_ascii=False)
    r = client.post("/api/quiz/grade", json={
        "card_id": cid, "answers": [{"question": "Q", "answer": "A"}],
    })
    assert r.status_code == 200
    assert r.json()["data"]["max_score"] == 10


def test_merge_quiz_to_card(quiz_env, client):
    cid = _create_card()
    r = client.post(f"/api/quiz/merge/{cid}", json={
        "card_id": cid, "answers": [{"question": "Q", "answer": "A"}],
    })
    assert r.status_code == 200
    card = r.json()["data"]["card"]
    assert "融合后的内容" in card["content"]


def test_exam(quiz_env, client):
    cid = _create_card()
    r = client.post("/api/quiz/exam", json={"card_ids": [cid]})
    assert r.status_code == 200
    assert len(r.json()["data"]["questions"]) >= 1


def test_exam_no_cards(quiz_env, client):
    r = client.post("/api/quiz/exam", json={"card_ids": []})
    assert r.status_code == 400


def test_merge_missing_card(quiz_env, client):
    r = client.post("/api/quiz/merge/nonexistent", json={
        "card_id": "nonexistent", "answers": [],
    })
    assert r.status_code == 404
