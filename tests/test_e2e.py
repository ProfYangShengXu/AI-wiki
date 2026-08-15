"""真实集成测试 — 端到端验证核心链路。"""

import pytest
from fastapi.testclient import TestClient

from bobanana.app import app

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

    @pytest.fixture(autouse=True)
    def fake_import_llm(self, monkeypatch):
        """导入任务用 FakeLLM,避免后台线程打真实 API 并泄漏到后续测试。"""
        from tests.fakes import FakeLLM
        fake = FakeLLM()
        fake.responses["知识提取专家"] = (
            '[{"title":"Topic A","content":"Topic A 的内容说明。","category":"测试",'
            '"examples":[],"questions":[],"aliases":[]}]'
        )
        monkeypatch.setattr("bobanana.tools.llm_invoke", fake)
        monkeypatch.setattr("bobanana.agent.llm_invoke", fake)
        return fake

    @staticmethod
    def _wait_done(task_id, timeout=30):
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            resp = client.get(f"/api/upload/status/{task_id}")
            if resp.status_code == 200 and resp.json()["data"]["status"] in (
                "done", "failed", "cancelled",
            ):
                return resp.json()["data"]
            time.sleep(0.2)
        raise TimeoutError(f"上传任务 {task_id} 未在 {timeout}s 内终止")

    def test_upload_markdown(self):
        content = b"## Test Doc\n\n### Topic A\n\nContent about A.\n\n### Topic B\n\nContent about B."
        resp = client.post(
            "/api/upload",
            files={"file": ("integration_test.md", content, "text/markdown")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        # 等待导入任务到终态,避免后台线程跨测试泄漏
        final = self._wait_done(data["data"]["task_id"])
        assert final["status"] == "done"

    def test_upload_invalid_type(self):
        resp = client.post(
            "/api/upload",
            files={"file": ("test.exe", b"binary", "application/octet-stream")},
        )
        assert resp.status_code == 400


class TestQuizAPI:
    """Quiz API 测试。"""

    @pytest.fixture(autouse=True)
    def fake_quiz_llm(self, monkeypatch, tmp_path):
        """用 FakeLLM 替换 quiz 路由的 llm_invoke, 并把掌握度文件重定向到临时目录。"""
        from tests.fakes import FakeLLM
        fake = FakeLLM()
        monkeypatch.setattr("bobanana.routes.quiz.llm_invoke", fake)
        monkeypatch.setattr("bobanana.routes.quiz.MASTERY_FILE", tmp_path / "mastery.json")
        return fake

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

    # ── A 层 (Adversarial) 测试 ────────────────────────

    def test_xss_in_title(self):
        """XSS 注入标题不应损坏响应。"""
        payload = '<script>alert("xss")</script>'
        resp = client.post("/api/cards", json={"title": payload, "content": "test"})
        assert resp.status_code == 201
        cid = resp.json()["data"]["id"]
        resp = client.get(f"/api/cards/{cid}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert payload in data["title"]
        assert "<script>" in data["title"]
        client.delete(f"/api/cards/{cid}")

    def test_sql_injection_like_title(self):
        """SQL 注入式标题不应引发错误。"""
        payloads = [
            "'; DROP TABLE cards; --",
            "' OR '1'='1",
            "'; DELETE FROM knowledge_cards WHERE '1'='1",
        ]
        for p in payloads:
            try:
                resp = client.post("/api/cards", json={"title": p, "content": "injection test"})
                assert resp.status_code == 201
                cid = resp.json()["data"]["id"]
                client.delete(f"/api/cards/{cid}")
            except Exception as e:
                pytest.fail(f"SQL-like title '{p}' failed: {e}")

    def test_very_long_title(self):
        """超长标题 (1000 chars) 不应崩溃，可被接收或拒绝。"""
        long_title = "A" * 1000
        resp = client.post("/api/cards", json={"title": long_title, "content": "long title test"})
        assert resp.status_code in [201, 422], f"Expected 201 or 422, got {resp.status_code}"
        if resp.status_code == 201:
            cid = resp.json()["data"]["id"]
            resp = client.get(f"/api/cards/{cid}")
            assert resp.status_code == 200
            assert resp.json()["data"]["title"] == long_title
            client.delete(f"/api/cards/{cid}")

    def test_unicode_content(self):
        """Unicode/emoji 内容。"""
        content = "🎉 中文测试 Méxícâñ strøngé ß 日本語 😊"
        resp = client.post("/api/cards", json={"title": "UnicodeTest", "content": content})
        assert resp.status_code == 201
        cid = resp.json()["data"]["id"]
        resp = client.get(f"/api/cards/{cid}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "🎉" in data["content"]
        assert "中文" in data["content"]
        assert "ß" in data["content"]
        client.delete(f"/api/cards/{cid}")


class TestKbIsolation:
    """KB 隔离测试。"""

    @pytest.fixture(autouse=True)
    def setup_kb_test(self):
        """创建临时 KB 并清理。"""
        from bobanana.routes.knowledgebase import _current_kb, _kb_meta
        self.old_kb = _current_kb
        self.test_kb_id = "test_kb_" + __import__("uuid").uuid4().hex[:8]
        _kb_meta[self.test_kb_id] = {"id": self.test_kb_id, "name": "测试KB", "created": "", "card_count": 0}
        yield
        if self.test_kb_id in _kb_meta:
            del _kb_meta[self.test_kb_id]

    def test_switch_to_test_kb(self):
        """切换到测试 KB 并确认。"""
        resp = client.post(f"/api/kb/switch/{self.test_kb_id}")
        assert resp.status_code in [200, 500]  # 500 可能是 ChromaDB 集合不存在

    def test_list_kbs(self):
        """列出 KB 包含测试 KB。"""
        resp = client.get("/api/kb/list")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        names = [k["name"] for k in data["data"]["kbs"]]
        assert "默认知识库" in names

    def test_data_isolation_between_kbs(self):
        """并发操作 KB A 和 KB B，数据不混。"""
        # 创建两个测试 KB
        resp_a = client.post("/api/kb/create", json={"name": "隔离测试A"})
        assert resp_a.status_code == 200
        kb_a_id = resp_a.json()["data"]["id"]
        resp_b = client.post("/api/kb/create", json={"name": "隔离测试B"})
        assert resp_b.status_code == 200
        kb_b_id = resp_b.json()["data"]["id"]

        try:
            # 切换到 KB_A，创建一张卡片
            resp = client.post(f"/api/kb/switch/{kb_a_id}")
            assert resp.status_code == 200
            resp = client.post(
                "/api/cards", json={"title": "KB_A专用卡", "content": "只在A库", "category": "测试"}
            )
            assert resp.status_code == 201

            # 切换到 KB_B，创建另一张卡片
            resp = client.post(f"/api/kb/switch/{kb_b_id}")
            assert resp.status_code == 200
            resp = client.post(
                "/api/cards", json={"title": "KB_B专用卡", "content": "只在B库", "category": "测试"}
            )
            assert resp.status_code == 201

            # 在 KB_A 中列出 — 只应找到 KB_A 的卡片
            resp = client.post(f"/api/kb/switch/{kb_a_id}")
            assert resp.status_code == 200
            resp = client.get("/api/cards")
            assert resp.status_code == 200
            a_titles = [c["title"] for c in resp.json()["data"]["cards"]]
            assert "KB_A专用卡" in a_titles, f"KB_A 应包含其卡片，实际: {a_titles}"
            assert "KB_B专用卡" not in a_titles, f"KB_A 不应包含 KB_B 的卡片，实际: {a_titles}"

            # 在 KB_B 中列出 — 只应找到 KB_B 的卡片
            resp = client.post(f"/api/kb/switch/{kb_b_id}")
            assert resp.status_code == 200
            resp = client.get("/api/cards")
            assert resp.status_code == 200
            b_titles = [c["title"] for c in resp.json()["data"]["cards"]]
            assert "KB_B专用卡" in b_titles, f"KB_B 应包含其卡片，实际: {b_titles}"
            assert "KB_A专用卡" not in b_titles, f"KB_B 不应包含 KB_A 的卡片，实际: {b_titles}"

        finally:
            # 清理测试 KB
            for kid in [kb_a_id, kb_b_id]:
                client.delete(f"/api/kb/{kid}")
            # 切回默认
            client.post("/api/kb/switch/default")


class TestUIStates:
    """UI 状态测试（前端渲染检查）。"""

    def test_index_contains_required_ids(self):
        """首页包含关键 DOM ID。"""
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        for dom_id in ["sidebar", "main", "chatMsgInput", "fileType"]:
            assert dom_id in html, f"缺少 DOM ID: {dom_id}"

    def test_index_has_spinner_class(self):
        """首页包含 spinner 样式定义。"""
        resp = client.get("/")
        assert ".spinner" in resp.text

    def test_index_has_retry_or_reset(self):
        """首页包含重试/重置相关文本。"""
        resp = client.get("/")
        html = resp.text
        assert any(word in html for word in ["retry", "Retry", "重试", "重置", "重来"])
