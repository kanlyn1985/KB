from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from enterprise_agent_kb.api_server import _hygiene_loop_snapshot
from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.closed_loop_store import _runtime_code_version
from enterprise_agent_kb.db import connect
from enterprise_agent_kb.derived_state import check_derived_state
from enterprise_agent_kb.derived_state_rebuild import rebuild_derived_state
from enterprise_agent_kb.retrieval import ensure_fts_schema, search_knowledge_base_expanded
from enterprise_agent_kb.run_governance import prune_stale_runs
from enterprise_agent_kb.workspace_doctor import run_workspace_doctor


SCHEMA_PATH = Path("src/enterprise_agent_kb/schema.sql")


@pytest.mark.unit
def test_residual_stale_fts_is_detected_and_contained_by_retrieval_guard(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_fact(connection, "FACT-CURRENT", "OBC 输入过压保护")
        ensure_fts_schema(connection)
        connection.execute(
            """
            INSERT INTO facts_fts(result_id, doc_id, page_no, searchable_text)
            VALUES ('FACT-ORPHAN', 'DOC-1', 1, 'stale orphan row')
            """
        )
        connection.commit()
        _write_old_stamp(paths.logs / "fts_index.stamp", paths.db_file)

        stale_check = check_derived_state(paths.root, state_id="facts_fts", connection=connection)[0]
        assert stale_check.status == "stale"
        assert stale_check.missing_count == 1
        assert stale_check.orphan_count == 1

        hits = search_knowledge_base_expanded(
            paths.root,
            "输入过压",
            limit=5,
            connection=connection,
            result_types={"fact"},
        )

        assert hits[0]["result_id"] == "FACT-CURRENT"
        assert _facts_fts_ids(connection) == ["FACT-CURRENT"]
        fresh_check = check_derived_state(paths.root, state_id="facts_fts", connection=connection)[0]
        assert fresh_check.status == "fresh"
    finally:
        connection.close()


@pytest.mark.unit
def test_residual_structural_orphans_are_visible_in_doctor_and_hygiene_loop(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_structural_orphans(connection)
        connection.commit()
    finally:
        connection.close()

    doctor = run_workspace_doctor(paths.root, scope="all")
    hygiene = _hygiene_loop_snapshot(paths.root)
    issue_ids = {issue.issue_id for issue in doctor.issues}
    hygiene_issue_ids = {str(issue.get("issue_id")) for issue in hygiene["issues"]}

    expected = {
        "graph_missing_src_entity",
        "graph_missing_dst_entity",
        "edge_evidence_missing_edge",
        "edge_evidence_missing_evidence",
        "wiki_missing_entity",
        "wiki_missing_source_fact",
        "wiki_missing_source_doc",
        "source_unit_fact_missing_unit",
        "source_unit_fact_missing_fact",
        "source_unit_evidence_missing_unit",
        "source_unit_evidence_missing_evidence",
    }
    assert expected.issubset(issue_ids)
    assert expected.issubset(hygiene_issue_ids)
    assert hygiene["issue_count"] == len(doctor.issues)
    assert hygiene["issue_summary"] == doctor.summary
    assert hygiene["status"] in {"warn", "fail"}
    assert "workspace-doctor --scope all --json" in hygiene["artifacts"]["workspace_doctor"]

    connection = connect(paths.db_file)
    try:
        assert _count(connection, "graph_edges") == 1
        assert _count(connection, "wiki_pages") == 1
        assert _count(connection, "source_unit_fact_map") == 1
        assert _count(connection, "source_unit_evidence_map") == 1
    finally:
        connection.close()

    dry_run = rebuild_derived_state(paths.root, scope="all", dry_run=True)
    assert dry_run.summary["planned"] == 4
    connection = connect(paths.db_file)
    try:
        assert _count(connection, "graph_edges") == 1
        assert _count(connection, "wiki_pages") == 1
        assert _count(connection, "source_unit_fact_map") == 1
        assert _count(connection, "source_unit_evidence_map") == 1
    finally:
        connection.close()

    executed = rebuild_derived_state(paths.root, scope="all")

    assert executed.status == "ok"
    assert executed.summary["unsupported"] == 0
    assert [item.scope for item in executed.items] == ["graph", "wiki", "coverage", "fts"]
    connection = connect(paths.db_file)
    try:
        assert _count(connection, "graph_edges") == 0
        assert _count(connection, "wiki_pages") == 0
        assert _count(connection, "source_unit_fact_map") == 0
        assert _count(connection, "source_unit_evidence_map") == 0
    finally:
        connection.close()


@pytest.mark.unit
def test_residual_stale_runs_are_dry_run_visible_and_execute_is_scoped(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    current = _runtime_code_version()
    connection = connect(paths.db_file)
    try:
        _insert_retrieval_run(connection, "RET-OLD", "old-code")
        _insert_retrieval_run(connection, "RET-UNKNOWN", "")
        _insert_retrieval_run(connection, "RET-CURRENT", current)
        _insert_eval_run(connection, "EVAL-OLD", "suite-a", "old-code")
        _insert_eval_result(connection, "EVAL-OLD", "CASE-OLD")
        _insert_eval_run(connection, "EVAL-UNKNOWN", "suite-a", "")
        _insert_eval_result(connection, "EVAL-UNKNOWN", "CASE-UNKNOWN")
        _insert_eval_run(connection, "EVAL-CURRENT", "suite-a", current)
        _insert_eval_result(connection, "EVAL-CURRENT", "CASE-CURRENT")
        _insert_golden_case(connection, "CASE-OLD")
        _insert_repair_task(connection, "TASK-OLD")
        connection.commit()
    finally:
        connection.close()

    dry_run = prune_stale_runs(paths.root, dry_run=True)
    hygiene = _hygiene_loop_snapshot(paths.root)

    assert dry_run.summary["retrieval_runs"] == 2
    assert dry_run.summary["eval_runs"] == 2
    assert dry_run.summary["eval_results"] == 2
    assert dry_run.summary["deleted_retrieval_runs"] == 0
    assert hygiene["stale_run_summary"]["retrieval_runs"] == 2
    assert hygiene["prune_plan"]["dry_run"] is True
    assert "prune-stale-runs --keep-current-code-version --dry-run" in hygiene["next_actions"]

    connection = connect(paths.db_file)
    try:
        assert _count(connection, "retrieval_runs") == 3
        assert _count(connection, "eval_runs") == 3
        assert _count(connection, "eval_results") == 3
    finally:
        connection.close()

    executed = prune_stale_runs(paths.root, dry_run=False)

    assert executed.summary["deleted_retrieval_runs"] == 2
    assert executed.summary["deleted_eval_runs"] == 2
    assert executed.summary["deleted_eval_results"] == 2
    connection = connect(paths.db_file)
    try:
        assert _ids(connection, "retrieval_runs", "run_id") == ["RET-CURRENT"]
        assert _ids(connection, "eval_runs", "eval_run_id") == ["EVAL-CURRENT"]
        assert _ids(connection, "eval_results", "eval_run_id") == ["EVAL-CURRENT"]
        assert _count(connection, "golden_cases") == 1
        assert _count(connection, "repair_tasks") == 1
    finally:
        connection.close()


def _insert_structural_orphans(connection) -> None:
    connection.execute(
        """
        INSERT INTO graph_edges(
            edge_id, src_entity_id, relation, dst_entity_id, version_scope,
            condition_scope, confidence, edge_status, created_at, updated_at
        )
        VALUES ('EDGE-ORPHAN', 'ENT-MISSING-SRC', 'related_to', 'ENT-MISSING-DST', NULL, NULL, 1.0, 'active', 'now', 'now')
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
        VALUES ('WPAGE-ORPHAN', 'term', 'Orphan', 'orphan', 'ENT-MISSING', '["FACT-MISSING"]', '["DOC-MISSING"]', 'ready', 'wiki.md', 'now')
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


def _insert_fact(connection, fact_id: str, object_value: str) -> None:
    connection.execute(
        """
        INSERT INTO facts(
            fact_id, fact_type, subject_entity_id, predicate, object_value,
            object_entity_id, qualifiers_json, confidence, fact_status,
            source_doc_id, created_at, updated_at
        )
        VALUES (?, 'term_definition', NULL, 'defines', ?, NULL, '{"page_no": 1}', 1.0, 'active', 'DOC-1', 'now', 'now')
        """,
        (fact_id, object_value),
    )


def _insert_retrieval_run(connection, run_id: str, code_version: str) -> None:
    connection.execute(
        """
        INSERT INTO retrieval_runs(
            run_id, query, query_type, doc_scope, retrieved_evidence_ids_json,
            reranked_ids_json, scores_json, code_version, metadata_json, created_at
        )
        VALUES (?, 'q', 'definition', 'global', '[]', '[]', '{}', ?, '{}', ?)
        """,
        (run_id, code_version, _old_time()),
    )


def _insert_eval_run(connection, eval_run_id: str, suite_id: str, code_version: str) -> None:
    connection.execute(
        """
        INSERT INTO eval_runs(
            eval_run_id, suite_id, started_at, finished_at, config_hash,
            code_version, result_summary_json, status
        )
        VALUES (?, ?, ?, ?, NULL, ?, '{}', 'passed')
        """,
        (eval_run_id, suite_id, _old_time(), _old_time(), code_version),
    )


def _insert_eval_result(connection, eval_run_id: str, case_id: str) -> None:
    connection.execute(
        """
        INSERT INTO eval_results(
            eval_run_id, case_id, passed, failure_reason,
            retrieved_items_json, answer_text, metrics_json, created_at
        )
        VALUES (?, ?, 1, NULL, '[]', '', '{}', ?)
        """,
        (eval_run_id, case_id, _old_time()),
    )


def _insert_golden_case(connection, case_id: str) -> None:
    connection.execute(
        """
        INSERT INTO golden_cases(
            case_id, doc_id, assert_mode, query, must_hit_json, negative_expected_json,
            expected_pages_json, expected_sections_json, expected_evidence_shape,
            status, source, metadata_json, created_at, updated_at
        )
        VALUES (?, 'DOC-1', 'context_contains', 'q', '[]', '[]', '[]', '[]', NULL, 'active', 'test', '{}', ?, ?)
        """,
        (case_id, _old_time(), _old_time()),
    )


def _insert_repair_task(connection, task_id: str) -> None:
    connection.execute(
        """
        INSERT INTO repair_tasks(
            task_id, reason, module, action, priority, status, case_ids_json,
            query_types_json, impact_count, source_eval_run_id, metadata_json,
            first_seen_at, last_seen_at
        )
        VALUES (?, 'reason', 'retrieval', 'fix', 1, 'open', '[]', '[]', 1, NULL, '{}', ?, ?)
        """,
        (task_id, _old_time(), _old_time()),
    )


def _write_old_stamp(stamp_path: Path, db_path: Path) -> None:
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text("ok", encoding="utf-8")
    old_time = db_path.stat().st_mtime - 10
    os.utime(stamp_path, (old_time, old_time))


def _old_time(days: int = 30) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")


def _facts_fts_ids(connection) -> list[str]:
    rows = connection.execute("SELECT result_id FROM facts_fts ORDER BY result_id").fetchall()
    return [str(row["result_id"]) for row in rows]


def _count(connection, table_name: str) -> int:
    return int(connection.execute(f"SELECT count(*) FROM {table_name}").fetchone()[0])


def _ids(connection, table_name: str, column_name: str) -> list[str]:
    rows = connection.execute(f"SELECT {column_name} FROM {table_name} ORDER BY {column_name}").fetchall()
    return [str(row[column_name]) for row in rows]
