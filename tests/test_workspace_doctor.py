from __future__ import annotations

import json
import sys
from pathlib import Path

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.cli import build_parser, main
from enterprise_agent_kb.closed_loop_store import sync_source_units_from_matrix
from enterprise_agent_kb.db import connect
from enterprise_agent_kb.workspace_doctor import (
    format_workspace_doctor_report,
    run_workspace_doctor,
)


SCHEMA_PATH = Path("src/enterprise_agent_kb/schema.sql")


def test_workspace_doctor_reports_missing_fts_without_creating_tables(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        assert not _table_exists(connection, "facts_fts")

        report = run_workspace_doctor(paths.root, scope="fts")

        assert report.status == "fail"
        assert {check.state_id for check in report.derived_state_checks} == {
            "facts_fts",
            "evidence_fts",
            "wiki_fts",
            "wiki_chunks_fts",
        }
        assert any(issue.issue_id == "derived_state_facts_fts_missing" for issue in report.issues)
        assert not _table_exists(connection, "facts_fts")
    finally:
        connection.close()


def test_workspace_doctor_reports_missing_database_for_specific_scope(tmp_path: Path) -> None:
    report = run_workspace_doctor(tmp_path / "missing-kb", scope="fts")

    assert report.status == "fail"
    assert report.derived_state_checks == ()
    assert [issue.issue_id for issue in report.issues] == ["workspace_root_missing"]


def test_workspace_doctor_reports_orphans_and_stale_runs(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        connection.execute(
            """
            INSERT INTO graph_edges(
                edge_id, src_entity_id, relation, dst_entity_id, version_scope,
                condition_scope, confidence, edge_status, created_at, updated_at
            )
            VALUES ('EDGE-1', 'ENT-MISSING-SRC', 'related_to', 'ENT-MISSING-DST', NULL, NULL, 1.0, 'active', 'now', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO edge_evidence_map(edge_id, evidence_id)
            VALUES ('EDGE-MISSING', 'EVID-MISSING')
            """
        )
        connection.execute(
            """
            INSERT INTO wiki_pages(
                page_id, page_type, title, slug, entity_id, source_fact_ids_json,
                source_doc_ids_json, trust_status, file_path, updated_at
            )
            VALUES ('WPAGE-1', 'term', 'Term', 'term', 'ENT-MISSING', '["FACT-MISSING"]', '["DOC-MISSING"]', 'ready', 'wiki.md', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO source_unit_fact_map(unit_id, fact_id, doc_id, support_type, created_at)
            VALUES ('UNIT-MISSING', 'FACT-MISSING', 'DOC-MISSING', 'primary', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO source_unit_evidence_map(unit_id, evidence_id, doc_id, support_type, created_at)
            VALUES ('UNIT-MISSING', 'EVID-MISSING', 'DOC-MISSING', 'primary', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO retrieval_runs(
                run_id, query, query_type, doc_scope, retrieved_evidence_ids_json,
                reranked_ids_json, scores_json, code_version, metadata_json, created_at
            )
            VALUES ('RET-OLD', 'q', 'definition', 'global', '[]', '[]', '{}', 'old-code', '{}', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO eval_runs(
                eval_run_id, suite_id, started_at, finished_at, config_hash,
                code_version, result_summary_json, status
            )
            VALUES ('EVAL-OLD', 'suite', 'now', NULL, NULL, 'old-code', '{}', 'passed')
            """
        )
        connection.commit()
    finally:
        connection.close()

    report = run_workspace_doctor(paths.root, scope="all")
    issue_ids = {issue.issue_id for issue in report.issues}

    assert report.status == "fail"
    assert "graph_missing_src_entity" in issue_ids
    assert "graph_missing_dst_entity" in issue_ids
    assert "edge_evidence_missing_edge" in issue_ids
    assert "edge_evidence_missing_evidence" in issue_ids
    assert "wiki_missing_entity" in issue_ids
    assert "wiki_missing_source_fact" in issue_ids
    assert "wiki_missing_source_doc" in issue_ids
    assert "source_unit_fact_missing_unit" in issue_ids
    assert "source_unit_fact_missing_fact" in issue_ids
    assert "source_unit_evidence_missing_unit" in issue_ids
    assert "source_unit_evidence_missing_evidence" in issue_ids
    assert "retrieval_runs_stale_code_version" in issue_ids
    assert "eval_runs_stale_code_version" in issue_ids


def test_workspace_doctor_text_report_contains_actions(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    report = run_workspace_doctor(paths.root, scope="fts")

    text = format_workspace_doctor_report(report)

    assert "Workspace doctor: fail" in text
    assert "Derived state:" in text
    assert "rebuild-derived-state --scope fts" in text


def test_workspace_doctor_run_actions_use_public_prune_command(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        connection.execute(
            """
            INSERT INTO retrieval_runs(
                run_id, query, query_type, doc_scope, retrieved_evidence_ids_json,
                reranked_ids_json, scores_json, code_version, metadata_json, created_at
            )
            VALUES ('RET-OLD', 'q', 'definition', 'global', '[]', '[]', '{}', 'old-code', '{}', 'now')
            """
        )
        connection.commit()
    finally:
        connection.close()

    report = run_workspace_doctor(paths.root, scope="runs")
    actions = [action for issue in report.issues for action in issue.recommended_actions]

    assert (
        "prune-stale-runs --keep-current-code-version --keep-latest-code-versions 3 --dry-run"
        in actions
    )
    issue = next(item for item in report.issues if item.issue_id == "retrieval_runs_stale_code_version")
    assert issue.details["current_count"] == 0
    assert issue.details["stale_count"] == 1


def test_workspace_doctor_reports_weak_definition_source_units(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        connection.execute(
            """
            INSERT INTO documents(
                doc_id, source_filename, source_type, mime_type, sha256, file_size,
                page_count, language, version_label, source_path, ingest_time,
                update_time, parse_status, quality_status, is_active
            )
            VALUES ('DOC-WEAK', 'doc.pdf', 'pdf', 'application/pdf', 'sha', 100, 1, 'zh', NULL, 'doc.pdf', 'now', 'now', 'parsed', 'ok', 1)
            """
        )
        sync_source_units_from_matrix(
            connection,
            "DOC-WEAK",
            [
                {
                    "unit_id": "SU-WEAK-DEF",
                    "unit_type": "definition_unit",
                    "page_no": 1,
                    "canonical_title": "山博轩，杨郁",
                    "canonical_key": "山博轩，杨郁",
                    "content_role": "definition",
                    "source_text": "山博轩，杨郁 物理层为车网交互的物理基础，即电动汽车、充电站、智能电网。",
                    "covered_by": {"fact_ids": ["FACT-WEAK"], "evidence_ids": ["EVID-WEAK"]},
                    "coverage_status": "covered",
                }
            ],
        )
        connection.commit()
    finally:
        connection.close()

    report = run_workspace_doctor(paths.root, scope="coverage")
    issue = next(item for item in report.issues if item.issue_id == "source_unit_weak_definition_shape")

    assert report.status == "warn"
    assert issue.details["unit_count"] == 1
    quality_summary = issue.details["quality_summary"]
    assert quality_summary["reason_counts"] == {"weak_definition_shape": 1}
    assert quality_summary["samples"]["weak_definition_shape"][0]["unit_id"] == "SU-WEAK-DEF"


def test_workspace_doctor_cli_parser_and_json_output(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    parser = build_parser()

    parsed = parser.parse_args(
        [
            "--root",
            str(paths.root),
            "workspace-doctor",
            "--scope",
            "fts",
            "--json",
        ]
    )
    assert parsed.command == "workspace-doctor"
    assert parsed.scope == "fts"
    assert parsed.json is True

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "eakb",
            "--root",
            str(paths.root),
            "workspace-doctor",
            "--scope",
            "fts",
            "--json",
        ],
    )
    main()

    output = json.loads(capsys.readouterr().out)
    assert output["scope"] == "fts"
    assert output["status"] == "fail"
    assert output["derived_state_checks"][0]["state_id"] == "facts_fts"


def _table_exists(connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type IN ('table', 'view') AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None
