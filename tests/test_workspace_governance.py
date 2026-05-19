from __future__ import annotations

import json
import sys
from pathlib import Path

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.cli import build_parser, main
from enterprise_agent_kb.db import connect
from enterprise_agent_kb.derived_state_rebuild import rebuild_derived_state
from enterprise_agent_kb.workspace_governance import (
    format_workspace_governance_report,
    run_workspace_governance,
)


SCHEMA_PATH = Path("src/enterprise_agent_kb/schema.sql")


def test_workspace_governance_classifies_wiki_orphans_as_safe_to_auto_fix(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        connection.execute(
            """
            INSERT INTO wiki_pages(
                page_id, page_type, title, slug, entity_id, source_fact_ids_json,
                source_doc_ids_json, trust_status, file_path, updated_at
            )
            VALUES ('WPAGE-ORPHAN', 'term', 'Term', 'term', NULL, '["FACT-MISSING"]', '[]', 'ready', 'wiki.md', 'now')
            """
        )
        connection.commit()
    finally:
        connection.close()

    report = run_workspace_governance(paths.root, scope="wiki")
    step = report.steps[0]

    assert report.status == "planned"
    assert step.issue_id == "wiki_missing_source_fact"
    assert step.category == "safe_to_auto_fix"
    assert step.command == "rebuild-derived-state --scope wiki"
    assert step.executable is False


def test_workspace_governance_execute_safe_rebuilds_only_safe_derived_state(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        connection.execute(
            """
            INSERT INTO wiki_pages(
                page_id, page_type, title, slug, entity_id, source_fact_ids_json,
                source_doc_ids_json, trust_status, file_path, updated_at
            )
            VALUES ('WPAGE-ORPHAN', 'term', 'Term', 'term', NULL, '["FACT-MISSING"]', '[]', 'ready', 'wiki.md', 'now')
            """
        )
        connection.commit()
    finally:
        connection.close()

    report = run_workspace_governance(paths.root, scope="wiki", execute_safe=True)

    assert report.summary["executed"] == 1
    assert report.steps[0].executed is True
    assert report.doctor_after is not None
    assert report.doctor_after.status == "ok"


def test_workspace_governance_refreshes_fts_after_structural_reconcile(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        connection.execute(
            """
            INSERT INTO wiki_pages(
                page_id, page_type, title, slug, entity_id, source_fact_ids_json,
                source_doc_ids_json, trust_status, file_path, updated_at
            )
            VALUES ('WPAGE-ORPHAN', 'term', 'Term', 'term', NULL, '["FACT-MISSING"]', '[]', 'ready', 'wiki.md', 'now')
            """
        )
        connection.commit()
    finally:
        connection.close()
    rebuild_derived_state(paths.root, scope="fts")

    report = run_workspace_governance(paths.root, scope="all", execute_safe=True)
    after_issue_ids = {issue.issue_id for issue in report.doctor_after.issues} if report.doctor_after else set()

    assert report.doctor_after is not None
    assert "wiki_missing_source_fact" not in after_issue_ids
    assert "derived_state_wiki_fts_stale" not in after_issue_ids
    assert report.steps[0].result["dependent_fts_refresh"]["status"] == "ok"


def test_workspace_governance_keeps_run_pruning_as_historical_dry_run(tmp_path: Path) -> None:
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

    report = run_workspace_governance(paths.root, scope="runs", execute_safe=True)
    step = report.steps[0]

    assert report.summary["historical_residue"] == 1
    assert report.summary["executed"] == 0
    assert step.category == "historical_residue"
    assert step.executable is False
    assert "--dry-run" in step.command


def test_workspace_governance_text_report_contains_categories(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    report = run_workspace_governance(paths.root, scope="fts")

    text = format_workspace_governance_report(report)

    assert "Workspace governance:" in text
    assert "safe_to_auto_fix" in text
    assert "rebuild-derived-state --scope fts" in text


def test_workspace_governance_cli_parser_and_json_output(tmp_path: Path, monkeypatch, capsys) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    parser = build_parser()

    parsed = parser.parse_args(
        [
            "--root",
            str(paths.root),
            "workspace-governance",
            "--scope",
            "fts",
            "--json",
        ]
    )
    assert parsed.command == "workspace-governance"
    assert parsed.scope == "fts"
    assert parsed.json is True

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "eakb",
            "--root",
            str(paths.root),
            "workspace-governance",
            "--scope",
            "fts",
            "--json",
        ],
    )
    main()

    output = json.loads(capsys.readouterr().out)
    assert output["scope"] == "fts"
    assert output["steps"][0]["category"] == "safe_to_auto_fix"
