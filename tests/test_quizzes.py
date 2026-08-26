"""Quiz 卡片 API 测试: CRUD + 生成入库 + 评分写回。"""

import json

import pytest
from fastapi.testclient import TestClient

from bobanana import quiz_store
from bobanana.app import app
from bobanana.models import CardCreate
from bobanana.service.card_service import card_service


@pytest.fixture(autouse=True)
def isolated_quiz_db(tmp_path, monkeypatch):
    """每个测试独立 SQLite, 不污染真实 DATA_DIR。"""
    monkeypatch.setattr(quiz_store, "DB_PATH", tmp_path / "quiz_cards.db")
    quiz_store.init_db()


@pytest.fixture
def client():
    c = TestClient(app)
    yield c
    c.close()


@pytest.fixture
def quiz_env(monkeypatch):
    from tests.fakes import FakeLLM
    fake = FakeLLM()
    fake.responses["出题专家"] = json.dumps([
        {"question": "题目1", "ref_answer": "参考1"},
        {"question": "题目2", "ref_answer": "参考2"},
    ], ensure_ascii=False)
    fake.responses["评分老师"] = json.dumps([
        {"score": 9, "comment": "正确", "reference": "参考"},
    ], ensure_ascii=False)
    monkeypatch.setattr("bobanana.routes.quiz.llm_invoke", fake)
    return fake


def _create_card(title="与门"):
    card = card_service.create_card_sync(CardCreate(
        title=title, category="数字逻辑", content=f"{title}:所有输入为1时输出为1。",
        source_file="test",
    ))
    return card["id"]


def test_quiz_card_crud(client):
    # 创建
    r = client.post("/api/quizzes", json={
        "title": "测试Quiz", "card_ids": [], "source": "manual",
        "questions": [{"question": "Q1", "ref_answer": "A1"}],
    })
    assert r.status_code == 201
    quiz = r.json()["data"]
    qid = quiz["id"]
    assert quiz["submitted"] is False
    assert quiz["status"] == "draft"
    assert quiz["created_at"]

    # 列表
    r = client.get("/api/quizzes")
    assert r.status_code == 200
    assert any(q["id"] == qid for q in r.json()["data"]["quizzes"])

    # 读取
    r = client.get(f"/api/quizzes/{qid}")
    assert r.status_code == 200
    assert r.json()["data"]["title"] == "测试Quiz"

    # 更新(中途修改: 编辑题目 + 用户答案 + 编辑态)
    r = client.put(f"/api/quizzes/{qid}", json={
        "questions": [{"question": "Q1改", "ref_answer": "A1", "user_answer": "我的答案"}],
        "user_edited": True,
    })
    assert r.status_code == 200
    q = r.json()["data"]
    assert q["questions"][0]["question"] == "Q1改"
    assert q["questions"][0]["user_answer"] == "我的答案"
    assert q["user_edited"] is True
    assert q["updated_at"] >= q["created_at"]

    # 不存在 → 404 detail 透传
    r = client.get("/api/quizzes/nonexistent")
    assert r.status_code == 404
    assert "不存在" in r.json()["message"]

    # 删除
    r = client.delete(f"/api/quizzes/{qid}")
    assert r.status_code == 200
    r = client.get(f"/api/quizzes/{qid}")
    assert r.status_code == 404


def test_generate_persists_quiz(quiz_env, client):
    """Quiz 页生成 → 自动保存为 quiz 卡片(永久)。"""
    cid = _create_card()
    r = client.post(f"/api/quiz/generate/{cid}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["quiz_id"]
    quiz = quiz_store.get_quiz_card(data["quiz_id"])
    assert quiz is not None
    assert quiz["card_ids"] == [cid]
    assert len(quiz["questions"]) == 2
    assert quiz["source"] == "quizpage"


def test_grade_writes_back_quiz(quiz_env, client):
    """评分 → 写回 quiz 卡片(提交状态 + 答案 + 评分)。"""
    cid = _create_card()
    r = client.post(f"/api/quiz/generate/{cid}")
    qid = r.json()["data"]["quiz_id"]

    r = client.post("/api/quiz/grade", json={
        "card_id": cid, "quiz_id": qid,
        "answers": [{"question": "题目1", "answer": "我的答案1"},
                    {"question": "题目2", "answer": "我的答案2"}],
    })
    assert r.status_code == 200

    quiz = quiz_store.get_quiz_card(qid)
    assert quiz["submitted"] is True
    assert quiz["status"] == "graded"
    q0 = quiz["questions"][0]
    assert q0["user_answer"] == "我的答案1"
    assert q0["score"] == 9
    assert q0["comment"] == "正确"
