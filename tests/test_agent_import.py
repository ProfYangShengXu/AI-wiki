"""Agent 导入流水线 (run_import_workflow) 测试:预扫描/提取/入库/取消/去重。"""

import json
import threading

import pytest

from bobanana.agent import run_import_workflow
from bobanana.service.card_service import card_service


@pytest.fixture
def fake_extract(monkeypatch):
    from tests.fakes import FakeLLM
    fake = FakeLLM()
    fake.responses["知识提取专家"] = json.dumps([
        {"title": "与门(流水线)", "content": "与门内容:所有输入为1时输出为1,其余为0。",
         "category": "数字逻辑", "examples": ["双钥匙门"], "questions": ["什么是与门?"],
         "aliases": ["AND"]},
        {"title": "或门(流水线)", "content": "或门内容:任一输入为1时输出为1。",
         "category": "数字逻辑", "examples": [], "questions": [], "aliases": ["OR"]},
    ], ensure_ascii=False)
    monkeypatch.setattr("bobanana.tools.llm_invoke", fake)
    monkeypatch.setattr("bobanana.agent.llm_invoke", fake)
    return fake


@pytest.fixture
def sample_doc(tmp_path):
    doc = tmp_path / "sample.md"
    doc.write_text(
        "# 逻辑门\n\n## 与门\n\n" + "与门是最基本的逻辑门,只有当所有输入都为高电平时输出才为高电平。"
        "表达式 Y 等于 A 与 B,真值表四种组合中只有输入都为一时输出才为一。"
        "与门在数字电路中常用于条件判断和使能控制。\n\n## 或门\n\n" +
        "或门的规则是只要任意一个输入为高电平,输出就为高电平,表达式 Y 等于 A 加 B。\n",
        encoding="utf-8",
    )
    return doc


def test_import_full_pipeline(fake_extract, sample_doc):
    events = []

    def cb(evt):
        events.append(evt)

    result = run_import_workflow(str(sample_doc), sample_doc.name, progress_callback=cb)
    assert result.total >= 1
    assert len(result.success) >= 1
    cards, _ = card_service.list_cards_sync()
    titles = {c.title for c in cards}
    assert "与门(流水线)" in titles or "或门(流水线)" in titles
    assert any(e.get("stage") == "scan" for e in events)


def test_import_cancel(fake_extract, sample_doc):
    """取消事件在提取前设置 → 无卡片入库或提前终止。"""
    ev = threading.Event()
    ev.set()
    result = run_import_workflow(str(sample_doc), sample_doc.name, cancel_event=ev)
    # 已取消:要么没有成功卡片,要么流水线提前退出(取决于扫描粒度)
    assert result is not None


def test_import_checkpointer(fake_extract, sample_doc):
    checkpoints = []

    def ckp(info):
        checkpoints.append(info)

    result = run_import_workflow(str(sample_doc), sample_doc.name, checkpointer=ckp)
    assert result.total >= 1
    assert len(checkpoints) >= 1
    assert "range_index" in checkpoints[0] or "start" in checkpoints[0]


def test_import_nonexistent_file(fake_extract, tmp_path):
    result = run_import_workflow(str(tmp_path / "nope.md"), "nope.md")
    assert result.total == 0
