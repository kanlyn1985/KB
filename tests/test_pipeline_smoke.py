from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.pipeline import run_file_pipeline
from enterprise_agent_kb.answer_api import answer_query
from enterprise_agent_kb.cli import build_parser


@pytest.mark.smoke
def test_markdown_pipeline_end_to_end() -> None:
    schema_path = Path(__file__).resolve().parents[1] / "src" / "enterprise_agent_kb" / "schema.sql"
    temp_path = Path.cwd() / f"test_runtime_{uuid.uuid4().hex}"
    temp_path.mkdir(parents=True, exist_ok=True)
    workspace = temp_path / "knowledge_base"
    initialize_workspace(workspace, schema_path)

    source = temp_path / "sample_standard.md"
    source.write_text(
        "\n".join(
            [
                "# 示例标准文档",
                "",
                "GB/T 99999.1—2025",
                "",
                "代替 GB/T 99999.1—2020",
                "",
                "2025-01-01 发布",
                "",
                "2025-06-01 实施",
                "",
                "## 3 术语和定义",
                "#### 3.1.1",
                "## 控制导引电路 control pilot circuit",
                "设计用于电动汽车和供电设备之间信号传输或通信的电路。",
            ]
        ),
        encoding="utf-8",
    )

    result = run_file_pipeline(workspace, source)

    assert result.doc_id.startswith("DOC-")
    assert result.page_count == 1
    assert result.fact_count >= 5
    assert result.entity_count >= 2
    assert result.coverage_source_unit_count >= 1
    assert (workspace / "coverage_reports" / f"{result.doc_id}.summary.json").exists()
    assert result.coverage_summary_path.endswith(f"{result.doc_id}.summary.json")
    assert result.coverage_report_path.endswith(f"{result.doc_id}.coverage_report.md")

    answer = answer_query(workspace, "什么是控制导引电路？", limit=6)
    assert "控制导引电路 control pilot circuit" in answer["direct_answer"]
    assert "信号传输或通信的电路" in answer["direct_answer"]


@pytest.mark.unit
def test_cli_parser_contains_current_commands() -> None:
    parser = build_parser()
    commands = parser._subparsers._group_actions[0].choices.keys()

    assert "build-file" in commands
    assert "answer-query" in commands
    assert "agent-query" in commands
