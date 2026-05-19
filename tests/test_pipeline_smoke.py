from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.pipeline import PipelineEvent, run_file_pipeline, run_file_pipeline_with_progress
from enterprise_agent_kb.ingestion_acceptance import validate_document_ingestion
from enterprise_agent_kb.answer_api import answer_query
from enterprise_agent_kb.cli import build_parser
from enterprise_agent_kb.config import AppPaths
from enterprise_agent_kb.db import connect


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
    assert result.ingestion_acceptance["failed_count"] == 0
    assert str(result.ingestion_acceptance["json_path"]).endswith(".ingestion_acceptance.json")
    acceptance = validate_document_ingestion(
        workspace,
        result.doc_id,
        min_text_coverage=0.5,
        min_semantic_coverage=0.2,
    )
    assert acceptance.status in {"passed", "warn"}
    assert acceptance.failed_count == 0
    assert (workspace / "acceptance_reports" / f"{result.doc_id}.ingestion_acceptance.json").exists()

    answer = answer_query(workspace, "什么是控制导引电路？", limit=6)
    assert "控制导引电路 control pilot circuit" in answer["direct_answer"]
    assert "信号传输或通信的电路" in answer["direct_answer"]


@pytest.mark.unit
def test_cli_parser_contains_current_commands() -> None:
    parser = build_parser()
    commands = parser._subparsers._group_actions[0].choices.keys()

    assert "build-file" in commands
    assert "validate-document-ingestion" in commands
    assert "answer-query" in commands
    assert "agent-query" in commands


@pytest.mark.unit
def test_file_pipeline_emits_stage_progress_events(tmp_path: Path) -> None:
    schema_path = Path(__file__).resolve().parents[1] / "src" / "enterprise_agent_kb" / "schema.sql"
    workspace = tmp_path / "knowledge_base"
    initialize_workspace(workspace, schema_path)
    source = tmp_path / "sample.md"
    source.write_text(
        "\n".join(
            [
                "# 示例标准文档",
                "",
                "GB/T 12345—2026",
                "",
                "代替 GB/T 12345—2020",
                "",
                "2026-01-01 发布",
                "",
                "2026-06-01 实施",
                "",
                "## 3 术语和定义",
                "#### 3.1.1",
                "## 控制导引电路 control pilot circuit",
                "设计用于电动汽车和供电设备之间信号传输或通信的电路。",
            ]
        ),
        encoding="utf-8",
    )
    events: list[PipelineEvent] = []

    result = run_file_pipeline_with_progress(
        workspace,
        source,
        progress_callback=events.append,
    )

    assert result.doc_id.startswith("DOC-")
    completed_stages = [event.stage for event in events if event.status == "completed"]
    assert completed_stages[:3] == ["register", "parse", "quality"]
    assert "ingestion_acceptance" in completed_stages
    parse_event = next(event for event in events if event.stage == "parse" and event.status == "completed")
    assert parse_event.detail["page_count"] == 1
    paths = AppPaths.from_root(workspace)
    connection = connect(paths.db_file)
    try:
        parse_view_count = connection.execute(
            "SELECT count(*) FROM parse_views WHERE doc_id = ?",
            (result.doc_id,),
        ).fetchone()[0]
        selection_count = connection.execute(
            "SELECT count(*) FROM page_parse_selection WHERE doc_id = ?",
            (result.doc_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    assert parse_view_count == result.page_count
    assert selection_count == result.page_count


@pytest.mark.unit
def test_build_commands_support_progress_flag() -> None:
    parser = build_parser()

    parsed = parser.parse_args(["build-file", "--file", "sample.md", "--progress"])

    assert parsed.command == "build-file"
    assert parsed.progress is True
