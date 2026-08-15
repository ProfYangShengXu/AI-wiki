"""冲覆盖率补充测试:card_service 扩展、database 旧接口、tools 解析、任务状态持久化。"""


import pytest

from bobanana import tools
from bobanana.database import db_manager
from bobanana.models import CardCreate, CardUpdate
from bobanana.service.card_service import card_service


def _mk(title="与门", category="数字逻辑", **kw):
    kw.setdefault("content", f"{title}的内容说明。" * 3)
    return card_service.create_card_sync(CardCreate(
        title=title, category=category, **kw,
    ))


def test_card_service_update_delete_roundtrip():
    created = _mk(aliases=["AND"], examples=["例子"])
    cid = created["id"]
    updated = card_service.update_card_sync(cid, CardUpdate(title="与门2"))
    assert updated is not None and updated.title == "与门2"
    card = card_service.get_card_sync(cid)
    assert card.title == "与门2"
    assert card_service.delete_card_sync(cid) is True
    assert card_service.get_card_sync(cid) is None


def test_card_service_batch_import_sync():
    result = card_service.batch_import_sync([
        CardCreate(title="批量1", category="批量", content="批量1的内容说明。"),
        CardCreate(title="批量2", category="批量", content="批量2的内容说明。"),
    ])
    assert result.total == 2
    assert len(result.success) == 2


def test_card_service_deduplicate_sync():
    _mk("重复A", content="完全相同的内容说明文本。" * 5)
    _mk("重复B", content="完全相同的内容说明文本。" * 5)
    result = card_service.deduplicate_sync(threshold=0.9)
    assert isinstance(result, dict)
    assert "merged" in result and "deleted" in result


def test_card_service_get_categories():
    _mk("分类甲", category="分类测试X")
    cats = card_service.get_categories_sync()
    assert "分类测试X" in cats


def test_database_search_cards_legacy_interface():
    _mk("旧接口卡")
    results = db_manager.search_cards([0.1] * 384, top_k=5)
    assert isinstance(results, list)


def test_database_update_mastery_metadata():
    created = _mk("掌握度卡")
    cid = created["id"]
    db_manager.update_mastery_metadata(cid, attempts=2, score=18)
    card = db_manager.get_card(cid)
    assert card.mastery_attempts >= 2
    assert card.mastery_score >= 18


def test_database_try_persist():
    db_manager._try_persist()


def test_tools_parse_markdown_text():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.txt"
        p.write_text("纯文本内容。" * 40, encoding="utf-8")
        pages = tools.parse_document(str(p))
        assert pages and pages[0]["text"]


def test_tools_parse_docx_fixture():
    pages = tools.parse_document("docs/eval/fixtures/docx_stack_queue.docx")
    assert len(pages) >= 1
    assert any("栈" in (p["text"] or "") for p in pages)


def test_tools_parse_pdf_fixture():
    pages = tools.parse_document("docs/eval/fixtures/pdf_diode.pdf")
    assert len(pages) >= 1
    assert any("二极管" in (p["text"] or "") for p in pages)


def test_tools_parse_llm_json_array():
    from bobanana import tools_schema
    assert tools_schema._parse_json_array('[{"a":1},{"b":2}]') == [{"a": 1}, {"b": 2}]
    assert tools_schema._parse_json_array("```json\n[{\"a\":1}]\n```") == [{"a": 1}]
    assert tools_schema._parse_json_array("垃圾文本") == []


def test_tools_scan_result_defaults():
    r = tools.ScanResult()
    assert r.total_pages == 0
    assert r.valid_ranges == []
    assert r.language == "zh"
    assert r.skipped_pages == []
    assert r.pages == []


def test_import_tasks_state_roundtrip(tmp_path, monkeypatch):
    from bobanana import import_tasks
    monkeypatch.setattr(import_tasks, "IMPORT_TASKS_DIR", tmp_path / "tasks")
    mgr = import_tasks.ImportTaskManager()
    task_id = mgr.create_task("/tmp/x.md", "x.md", kb_id="kb1", file_type="course")
    # 内存任务与磁盘状态一致
    state = mgr.get_task(task_id)
    assert state["filename"] == "x.md"
    assert state["kb_id"] == "kb1"
    # 从磁盘重建(清内存后)
    mgr._tasks.pop(task_id, None)
    state2 = mgr.get_task(task_id)
    assert state2 is not None and state2["task_id"] == task_id
    # list_tasks 含该任务
    assert any(t["task_id"] == task_id for t in mgr.list_tasks())


def test_app_misc_endpoints():
    from fastapi.testclient import TestClient

    from bobanana.app import app
    c = TestClient(app)
    r1 = c.get("/")
    assert r1.status_code == 200
    r2 = c.get("/api/openapi.yaml")
    assert r2.status_code == 200
    assert "openapi" in r2.text
    r3 = c.get("/api/logs")
    assert r3.status_code == 200
    assert r3.json()["status"] == "success"


def test_backup_corrupted_zip(tmp_path, monkeypatch):
    from bobanana import backup
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    fake_dir = tmp_path / "backups"
    fake_dir.mkdir(parents=True, exist_ok=True)
    bad = fake_dir / "swkb-bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(Exception):  # noqa: B017
        backup.restore_backup("swkb-bad.zip")


def test_backup_find_backup(tmp_path, monkeypatch):
    from bobanana import backup
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    assert backup._find_backup("nonexistent.zip") is None


def test_bootstrap_env_file_helpers(tmp_path):
    from bobanana.routes import bootstrap
    env = tmp_path / ".env"
    env.write_text('# 注释\nLLM_TEMPERATURE="0.1"\n', encoding="utf-8")
    lines = bootstrap._read_env_file(env)
    assert len(lines) >= 2
    bootstrap._write_env_file(env, {"LLM_TEMPERATURE": "0.3", "NEW_KEY": "v"})
    content = env.read_text(encoding="utf-8")
    assert "LLM_TEMPERATURE=\"0.3\"" in content
    assert "NEW_KEY=\"v\"" in content
    assert "# 注释" in content  # 注释保留


def test_bootstrap_mask_key():
    from bobanana.routes.bootstrap import _mask_key
    assert _mask_key("sk-dummy1234567890abcdef123456") == "sk-...3456"
    assert _mask_key("short") == "...hort"




def test_settings_batch_save(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from bobanana.app import app
    from bobanana.routes import settings as settings_mod
    monkeypatch.setattr(settings_mod, "ENV_PATH", tmp_path / ".env")
    (tmp_path / ".env").write_text('LLM_TEMPERATURE="0.1"\n', encoding="utf-8")
    c = TestClient(app)
    r = c.post("/api/settings/batch", json=[
        {"key": "LLM_TEMPERATURE", "value": "0.4"},
        {"key": "LLM_MAX_TOKENS", "value": "8192"},
    ])
    assert r.status_code == 200
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "LLM_TEMPERATURE=0.4" in content
    assert "LLM_MAX_TOKENS=8192" in content
    c.close()


def test_quiz_clean_json():
    from bobanana.routes.quiz import _clean_json
    assert _clean_json('```json\n{"a":1}\n```') == {"a": 1}
    assert _clean_json("垃圾") is None


def test_quiz_mastery_helpers(tmp_path, monkeypatch):
    from bobanana.routes import quiz as quiz_mod
    monkeypatch.setattr(quiz_mod, "MASTERY_FILE", tmp_path / "mastery.json")
    # 空文件场景
    (tmp_path / "mastery.json").write_text("{bad json", encoding="utf-8")
    assert quiz_mod._load_mastery() == {}


def test_backup_internal_helpers(tmp_path, monkeypatch):
    from pathlib import Path

    from bobanana import backup
    assert backup._is_excluded(Path(".env")) is True
    assert backup._is_excluded(Path("logs/app.log")) is True
    assert backup._is_excluded(Path("chroma_db/x")) is False
    import zipfile
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("hello", encoding="utf-8")
    zpath = tmp_path / "t.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        backup._zip_dir(zf, src, "arc")
    with zipfile.ZipFile(zpath) as zf:
        assert "arc/a.txt" in zf.namelist()


def test_errors_sw_raise_and_helpers():
    from bobanana import errors
    assert errors.status_for_code("SW-CARD-404") == 404
    assert errors.status_for_code("SW-BOOTSTRAP-TIMEOUT") == 504
    assert errors.status_for_code("SW-UNKNOWN-X") == 500
    assert errors.generic_code_for_status(418) == "SW-GENERIC-418"
    assert errors.generic_code_for_status(500) == "SW-GENERIC-500"
    with pytest.raises(errors.SWError) as exc:
        errors.sw_raise("SW-CARD-404", "卡片不存在")
    assert exc.value.status_code == 404
    assert exc.value.to_dict()["error_code"] == "SW-CARD-404"


def test_import_tasks_utc_now():
    from bobanana import import_tasks
    ts = import_tasks.utc_now_iso()
    assert ts.endswith("+00:00") or "T" in ts


def test_errors_status_for_unknown_suffix():
    from bobanana import errors
    # 覆盖 _NON_NUMERIC_STATUS 回退分支
    assert errors.status_for_code("SW-TEST-WHATEVER") == 500


def test_quiz_merge_card_llm_failure(tmp_path, monkeypatch):
    """merge 端点 LLM 返回垃圾 → 500(SW-GENERIC-500 包装)。"""
    from fastapi.testclient import TestClient

    from bobanana.app import app
    from bobanana.models import CardCreate
    from bobanana.routes import quiz as quiz_mod
    from bobanana.service.card_service import card_service
    monkeypatch.setattr(quiz_mod, "MASTERY_FILE", tmp_path / "mastery.json")
    monkeypatch.setattr("bobanana.routes.quiz.llm_invoke", lambda *a, **k: "不是JSON")
    cid = card_service.create_card_sync(CardCreate(title="融合卡", content="内容" * 10))["id"]
    c = TestClient(app)
    r = c.post(f"/api/quiz/merge/{cid}", json={"card_id": cid, "answers": []})
    assert r.status_code == 500
    c.close()
