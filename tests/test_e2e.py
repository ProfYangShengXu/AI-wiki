"""真实集成测试 — 端到端验证核心链路。"""

import pytest
import json
from fastapi.testclient import TestClient

from bobanana.app import app
from bobanana.database import db_manager
from bobanana.config import CHROMA_DB_DIR

TEST_COLLECTION = "test_e2e_cards"


@pytest.fixture(autouse=True)
def init_db():
    """初始化 ChromaDB + 隔离测试集合。"""
    import chromadb
    if db_manager._client is None:
        db_manager._client = chromadb.PersistentClient(
            path=str(CHROMA_DB_DIR),
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
    try:
        db_manager._client.delete_collection(TEST_COLLECTION)
    except Exception:
        pass
    test_col = db_manager._client.create_collection(
        name=TEST_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )
    old_col = db_manager._collection
    db_manager._collection = test_col
    yield
    db_manager._collection = old_col
    try:
        db_manager._client.delete_collection(TEST_COLLECTION)
    except Exception:
        pass


client = TestClient(app)


class TestCardLifecycle:
    """知识卡片完整生命周期测试。"""

    def test_create_card_minimal(self):
        """最简创建。"""
        resp = client.post("/api/cards", json={"title": "最小卡片"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "success"
        assert data["data"]["title"] == "最小卡片"
        assert data["data"]["id"] is not None

    def test_create_card_full(self):
        """完整创建。"""
        resp = client.post("/api/cards", json={
            "title": "测试卡片",
            "aliases": ["别名1", "别名2"],
            "content": "详细内容",
            "examples": ["例子1", "例子2"],
            "questions": ["问题1"],
            "category": "集成测试",
        })
        assert resp.status_code == 201
        card = resp.json()["data"]
        assert len(card["aliases"]) == 2
        assert len(card["examples"]) == 2
        assert len(card["questions"]) == 1
        assert card["category"] == "集成测试"

    def test_create_and_read(self):
        """创建后读取。"""
        resp = client.post("/api/cards", json={"title": "读写测试", "content": "读写"})
        cid = resp.json()["data"]["id"]

        resp = client.get(f"/api/cards/{cid}")
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "读写测试"

    def test_create_and_update(self):
        """创建后修改。"""
        resp = client.post("/api/cards", json={"title": "旧标题"})
        cid = resp.json()["data"]["id"]

        resp = client.put(f"/api/cards/{cid}", json={"title": "新标题", "content": "新内容"})
        assert resp.status_code == 200

        resp = client.get(f"/api/cards/{cid}")
        assert resp.json()["data"]["title"] == "新标题"
        assert resp.json()["data"]["content"] == "新内容"

    def test_create_and_delete(self):
        """创建后删除。"""
        resp = client.post("/api/cards", json={"title": "待删除"})
        cid = resp.json()["data"]["id"]

        resp = client.delete(f"/api/cards/{cid}")
        assert resp.status_code == 200

        resp = client.get(f"/api/cards/{cid}")
        assert resp.status_code == 404

    def test_list_cards(self):
        """列表查询。"""
        for i in range(5):
            client.post("/api/cards", json={
                "title": f"列表{i}", "category": "A" if i % 2 == 0 else "B"
            })
        resp = client.get("/api/cards?limit=50")
        assert resp.json()["data"]["total"] >= 5

    def test_filter_by_category(self):
        """按分类过滤。"""
        client.post("/api/cards", json={"title": "分类A", "category": "CatX"})
        client.post("/api/cards", json={"title": "分类B", "category": "CatX"})
        client.post("/api/cards", json={"title": "分类C", "category": "CatY"})

        resp = client.get("/api/cards?category=CatX")
        assert resp.json()["data"]["total"] == 2


class TestSearchAndCategories:
    """搜索 + 分类测试。"""

    def test_search(self):
        client.post("/api/cards", json={"title": "机器学习", "content": "ML内容", "category": "AI"})
        resp = client.get("/api/cards/search?q=机器学习")
        assert resp.status_code == 200
        assert len(resp.json()["data"]["cards"]) >= 1
        assert resp.json()["data"]["cards"][0]["title"] == "机器学习"

    def test_categories_list(self):
        client.post("/api/cards", json={"title": "T1", "category": "测试分类X"})
        client.post("/api/cards", json={"title": "T2", "category": "测试分类Y"})
        resp = client.get("/api/categories")
        assert resp.status_code == 200
        cats = resp.json()["data"]["categories"]
        assert "测试分类X" in cats or len(cats) >= 1


class TestUpload:
    """文件上传测试。"""

    def test_upload_markdown(self):
        content = b"## Test Doc\n\n### Topic A\n\nContent about A.\n\n### Topic B\n\nContent about B."
        resp = client.post(
            "/api/upload",
            files={"file": ("integration_test.md", content, "text/markdown")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_upload_invalid_type(self):
        resp = client.post(
            "/api/upload",
            files={"file": ("test.exe", b"binary", "application/octet-stream")},
        )
        assert resp.status_code == 400


class TestQuizAPI:
    """Quiz API 测试。"""

    @pytest.fixture(autouse=True)
    def create_test_card(self):
        """创建用于 Quiz 的测试卡片。"""
        resp = client.post("/api/cards", json={
            "title": "QuizTest",
            "content": "这是测试内容，用于验证Quiz功能。",
            "category": "QuizCategory"
        })
        self.test_card_id = resp.json()["data"]["id"]
        yield
        client.delete(f"/api/cards/{self.test_card_id}")

    def test_generate_quiz(self):
        """生成 Quiz 题目。"""
        resp = client.post(f"/api/quiz/generate/{self.test_card_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert len(data["data"]["questions"]) >= 2

    def test_grade_quiz(self):
        """评分 Quiz。"""
        resp = client.post("/api/quiz/grade", json={
            "card_id": self.test_card_id,
            "answers": [
                {"question": "什么是QuizTest？", "answer": "一种测试方法"}
            ]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["data"]["total_score"] >= 0
        assert data["data"]["max_score"] == 10

    def test_mastery(self):
        """掌握度查询。"""
        # 先评分提升掌握度
        client.post("/api/quiz/grade", json={
            "card_id": self.test_card_id,
            "answers": [{"question": "Q", "answer": "完美答案"}]
        })
        resp = client.get(f"/api/quiz/mastery/{self.test_card_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "mastery_pct" in data["data"]


class TestErrorHandling:
    """错误处理测试。"""

    def test_404_card(self):
        resp = client.get("/api/cards/nonexistent")
        assert resp.status_code == 404

    def test_404_endpoint(self):
        resp = client.get("/api/notexist")
        assert resp.status_code == 404

    def test_405_method(self):
        resp = client.put("/api/categories")
        assert resp.status_code == 405

    def test_422_invalid_create(self):
        resp = client.post("/api/cards", json={"title": ""})
        assert resp.status_code >= 400

    def test_create_exam(self):
        """组卷测试。"""
        resp = client.post("/api/quiz/exam", json={
            "card_ids": [self.test_card_id] if hasattr(self, 'test_card_id') else []
        })
        assert resp.status_code in [200, 400]
