from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.unit
def test_delivery_scripts_exist() -> None:
    assert Path("launch.ps1").exists()
    assert Path("start_demo.bat").exists()


@pytest.mark.unit
def test_demo_page_exists() -> None:
    demo_path = Path("examples/demo.html")
    assert demo_path.exists()
    content = demo_path.read_text(encoding="utf-8")
    assert "企业级知识库工作台" in content
    assert "/answer-query" in content
    assert "当前任务" in content
    assert "文档详情" in content
    assert "docSearch" in content
    assert "parseFilter" in content
    assert "qualityFilter" in content
    assert "queryScope" in content
    assert 'value="global">全库' in content
    assert 'value="document">当前文档' in content
    assert 'if (queryScope === "document" && state.selectedDocId)' in content
    assert "renderAnswerView" in content
    assert "Direct Answer" in content
    assert "依据事实" in content
    assert "queryText:" in content
    assert "function setQueryText" in content
    assert 'setQueryText(queryText.value, "lab")' in content
    assert 'setQueryText(event.target.value, "global")' in content
    assert "renderGoldenResult" in content
    assert "覆盖召回" in content
    assert "答案质量" in content
    assert "renderCards" in content
    assert "<details>" in content
