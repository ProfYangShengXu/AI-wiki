"""API 路由集成测试 — 使用 FastAPI TestClient。"""

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import TestClient as StarletteTestClient

from bobanana.app import app
from bobanana.database import db_manager
from bobanana.config import CHROMA_DB_DIR

TEST_COLLECTION = "test_route_cards"


@pytest.fixture(autouse=True)
def init_db():
    """每个测试前后初始化 ChromaDB + 隔离测试集合。"""
    import chromadb
    # 若未初始化，直接创建客户端
    if db_manager._client is None:
        db_manager._client = chromadb.PersistentClient(
            path=str(CHROMA_DB_DIR),
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
    # 清理旧测试集合
    try:
        db_manager._client.delete_collection(TEST_COLLECTION)
    except Exception:
        pass
    # 创建测试集合
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


class TestRoot:
    def test_root_returns_html(self):
        resp = client.get("/")
        assert resp.status_code == 200


class TestHealth:
    def test_health(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "cards_count" in data


class TestCardsAPI:
    def test_list_cards_empty(self):
        resp = client.get("/api/cards")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["data"]["cards"] == []

    def test_create_and_get_card(self):
        resp = client.post("/api/cards", json={
            "title": "测试CPU",
            "content": "CPU 是中央处理器",
            "examples": ["Intel i7"],
            "questions": ["CPU 是什么？"],
            "category": "硬件",
        })
        assert resp.status_code == 201
        card = resp.json()["data"]
        assert card["title"] == "测试CPU"
        assert len(card["examples"]) == 1
        card_id = card["id"]

        # Get by ID
        resp = client.get(f"/api/cards/{card_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "测试CPU"

        # Update
        resp = client.put(f"/api/cards/{card_id}", json={"content": "CPU 是中央处理单元"})
        assert resp.status_code == 200

        # Delete
        resp = client.delete(f"/api/cards/{card_id}")
        assert resp.status_code == 200

        # Verify deleted
        resp = client.get(f"/api/cards/{card_id}")
        assert resp.status_code == 404

    def test_search(self):
        client.post("/api/cards", json={
            "title": "Python语言", "content": "Python 是一种编程语言", "category": "编程",
        })
        resp = client.get("/api/cards/search?q=Python")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["cards"]) >= 1


class TestCategoriesAPI:
    def test_categories(self):
        client.post("/api/cards", json={
            "title": "测试分类", "content": "test", "category": "测试分类A",
        })
        resp = client.get("/api/categories")
        assert resp.status_code == 200
        assert "测试分类A" in resp.json()["data"]["categories"]


class TestUploadAPI:
    def test_upload_text_file(self):
        content = b"## Test\n\nThis is test content."
        resp = client.post(
            "/api/upload",
            files={"file": ("test_upload.md", content, "text/markdown")},
        )
        assert resp.status_code == 200

    def test_upload_invalid_extension(self):
        resp = client.post(
            "/api/upload",
            files={"file": ("test.exe", b"fake", "application/octet-stream")},
        )
        assert resp.status_code == 400


class TestErrorHandling:
    def test_404(self):
        resp = client.get("/api/nonexistent")
        assert resp.status_code == 404

    def test_405(self):
        resp = client.put("/api/categories")
        assert resp.status_code == 405

    def test_invalid_card_id(self):
        resp = client.get("/api/cards/nonexistent-id")
        assert resp.status_code == 404
