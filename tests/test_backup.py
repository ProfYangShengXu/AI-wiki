"""备份 / 恢复 / 迁移 测试 (Phase 2 §4)。"""

import zipfile

import pytest
from fastapi.testclient import TestClient

from bobanana.app import app


@pytest.fixture
def backup_dir(tmp_path, monkeypatch):
    """把备份输出目录与数据源目录全部重定向到 tmp_path,绝不触碰生产路径。"""
    from bobanana import backup
    fake_dir = tmp_path / "backups"
    fake_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(backup, "BACKUP_DIR", fake_dir)
    # backup.py 以 `from bobanana.config import ...` 方式缓存了模块级常量,
    # 因此必须直接替换 backup 模块自身的引用,而不是 config 的。
    chroma_dir = tmp_path / "chroma_db"
    uploads_dir = tmp_path / "uploads"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    (chroma_dir / "mastery.json").write_text('{"x": {"attempts": 1}}', encoding="utf-8")
    monkeypatch.setattr(backup, "CHROMA_DB_DIR", chroma_dir)
    monkeypatch.setattr(backup, "UPLOAD_DIR", uploads_dir)
    return fake_dir


def test_create_backup_zip_valid(backup_dir):
    from bobanana.backup import create_backup, list_backups
    path = create_backup()
    assert path.exists() and path.suffix == ".zip"
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        assert any("backup_manifest.json" in n for n in names)
        manifest = zf.read([n for n in names if n.endswith("backup_manifest.json")][0])
        assert b"collection_count" in manifest or b"collections" in manifest
    backups = list_backups()
    assert len(backups) >= 1
    assert backups[0]["name"] == path.name


def test_create_backup_named(backup_dir):
    from bobanana.backup import create_backup
    path = create_backup(name="my-test-backup")
    assert path.name == "my-test-backup.zip" or path.name.startswith("my-test-backup")


def test_list_backups_empty(backup_dir):
    from bobanana.backup import list_backups
    assert isinstance(list_backups(), list)


def test_restore_dry_run_unknown_404(backup_dir):
    c = TestClient(app)
    resp = c.post("/api/backup/restore/nonexistent.zip", json={"dry_run": True})
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "SW-BACKUP-404"


def test_restore_dry_run_plan(backup_dir):
    from bobanana.backup import create_backup
    path = create_backup()
    c = TestClient(app)
    resp = c.post(f"/api/backup/restore/{path.name}", json={"dry_run": True})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "plan" in data or "files" in data or "collection_count" in data


def test_backup_routes_endpoints(backup_dir):
    c = TestClient(app)
    r1 = c.post("/api/backup/create")
    assert r1.status_code == 200
    assert r1.json()["data"]["name"].endswith(".zip")
    r2 = c.get("/api/backup/list")
    assert r2.status_code == 200
    assert any(b["name"] == r1.json()["data"]["name"] for b in r2.json()["data"]["backups"])


def test_real_restore_roundtrip(backup_dir, tmp_path):
    """备份 → 删除数据 → 恢复 → 数据回来。"""
    from bobanana import backup
    chroma_dir = backup.CHROMA_DB_DIR
    marker = chroma_dir / "marker.txt"
    marker.write_text("hello", encoding="utf-8")

    path = backup.create_backup()
    marker.unlink()
    assert not marker.exists()

    result = backup.restore_backup(path.name)
    assert result["restored"], result
    assert marker.exists()
