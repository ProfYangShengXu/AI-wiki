"""API 路由集成测试 — 使用 FastAPI TestClient。"""

from fastapi.testclient import TestClient

from bobanana.app import app

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
        # 手动创建卡片保留自定义分类(支持分类手动 CRUD)
        client.post("/api/cards", json={
            "title": "测试分类", "content": "test", "category": "测试分类A",
        })
        resp = client.get("/api/categories")
        assert resp.status_code == 200
        cats = resp.json()["data"]["categories"]
        # 自定义分类被保留
        assert "测试分类A" in cats

    def test_category_rename_delete(self):
        # 分类重命名/删除/新建
        client.post("/api/cards", json={
            "title": "卡1", "content": "c1", "category": "临时分类",
        })
        # 重命名
        resp = client.put("/api/categories", json={
            "old_name": "临时分类", "new_name": "新分类",
        })
        assert resp.status_code == 200
        cats = client.get("/api/categories").json()["data"]["categories"]
        assert "临时分类" not in cats and "新分类" in cats
        # 删除(名称走 body) → 卡片归入通用
        resp = client.request("DELETE", "/api/categories", json={"name": "新分类"})
        assert resp.status_code == 200
        cats = client.get("/api/categories").json()["data"]["categories"]
        assert "新分类" not in cats
        # 新建
        resp = client.post("/api/categories", json={"name": "新建分类"})
        assert resp.status_code == 201
        cats = client.get("/api/categories").json()["data"]["categories"]
        assert "新建分类" in cats
        # 删除已不存在的分类 → 404, detail 透传具体分类名
        resp = client.request("DELETE", "/api/categories", json={"name": "不存在分类"})
        assert resp.status_code == 404
        assert "不存在分类" in resp.json()["message"]

    def test_category_rename_conflict(self):
        # 重命名到已存在的分类名 → 400, 不静默合并
        client.post("/api/cards", json={
            "title": "卡A", "content": "a", "category": "分类A",
        })
        client.post("/api/cards", json={
            "title": "卡B", "content": "b", "category": "分类B",
        })
        resp = client.put("/api/categories", json={
            "old_name": "分类A", "new_name": "分类B",
        })
        assert resp.status_code == 400
        assert "已存在" in resp.json()["message"]
        # 两个分类都还在, 未被合并
        cats = client.get("/api/categories").json()["data"]["categories"]
        assert "分类A" in cats and "分类B" in cats

    def test_category_delete_general_forbidden(self):
        # 「通用」不可删除
        resp = client.request("DELETE", "/api/categories", json={"name": "通用"})
        assert resp.status_code == 400
        assert "不可删除" in resp.json()["message"]

    def test_category_delete_slash_name(self):
        # 含斜杠分类名: 走 body 删除正常(路径参数时代会 404 接口不存在)
        resp = client.post("/api/categories", json={"name": "斜杠/分类"})
        assert resp.status_code == 201
        resp = client.request("DELETE", "/api/categories", json={"name": "斜杠/分类"})
        assert resp.status_code == 200
        cats = client.get("/api/categories").json()["data"]["categories"]
        assert "斜杠/分类" not in cats


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
        # PATCH 未注册 → 方法不允许(405)
        resp = client.patch("/api/categories")
        assert resp.status_code == 405

    def test_invalid_card_id(self):
        resp = client.get("/api/cards/nonexistent-id")
        assert resp.status_code == 404
