from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.cli import build_parser, main
from enterprise_agent_kb.closed_loop_store import _runtime_code_version, _source_tree_content_hash
from enterprise_agent_kb.db import connect
from enterprise_agent_kb.run_governance import prune_stale_runs


SCHEMA_PATH = Path("src/enterprise_agent_kb/schema.sql")


def test_prune_stale_runs_dry_run_is_readonly(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    current = _runtime_code_version()
    connection = connect(paths.db_file)
    try:
        _insert_retrieval_run(connection, "RET-OLD", "old-code", _old_time())
        _insert_retrieval_run(connection, "RET-UNKNOWN", "", _old_time())
        _insert_retrieval_run(connection, "RET-CURRENT", current, _old_time())
        _insert_eval_run(connection, "EVAL-OLD", "suite-a", "old-code", _old_time())
        _insert_eval_result(connection, "EVAL-OLD", "CASE-1")
        _insert_eval_run(connection, "EVAL-UNKNOWN", "suite-a", "", _old_time())
        _insert_eval_result(connection, "EVAL-UNKNOWN", "CASE-2")
        _insert_eval_run(connection, "EVAL-CURRENT", "suite-a", current, _old_time())
        _insert_eval_result(connection, "EVAL-CURRENT", "CASE-3")
        connection.commit()
    finally:
        connection.close()

    report = prune_stale_runs(paths.root, dry_run=True)

    assert report.summary["retrieval_runs"] == 2
    assert report.summary["eval_runs"] == 2
    assert report.summary["eval_results"] == 2
    assert report.summary["deleted_retrieval_runs"] == 0
    connection = connect(paths.db_file)
    try:
        assert _count(connection, "retrieval_runs") == 3
        assert _count(connection, "eval_runs") == 3
        assert _count(connection, "eval_results") == 3
    finally:
        connection.close()


def test_prune_stale_runs_deletes_candidates_and_keeps_current_and_unrelated_tables(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    current = _runtime_code_version()
    connection = connect(paths.db_file)
    try:
        _insert_retrieval_run(connection, "RET-OLD", "old-code", _old_time())
        _insert_retrieval_run(connection, "RET-CURRENT", current, _old_time())
        _insert_eval_run(connection, "EVAL-OLD", "suite-a", "old-code", _old_time())
        _insert_eval_result(connection, "EVAL-OLD", "CASE-1")
        _insert_eval_run(connection, "EVAL-CURRENT", "suite-a", current, _old_time())
        _insert_eval_result(connection, "EVAL-CURRENT", "CASE-2")
        _insert_golden_case(connection, "CASE-1")
        _insert_repair_task(connection, "TASK-1")
        connection.commit()
    finally:
        connection.close()

    archive_dir = tmp_path / "archives"
    report = prune_stale_runs(paths.root, archive_dir=archive_dir, dry_run=False)

    assert report.summary["deleted_retrieval_runs"] == 1
    assert report.summary["deleted_eval_runs"] == 1
    assert report.summary["deleted_eval_results"] == 1
    assert report.archive_path is not None
    archive = json.loads(Path(report.archive_path).read_text(encoding="utf-8"))
    assert [row["run_id"] for row in archive["retrieval_runs"]] == ["RET-OLD"]
    assert [row["eval_run_id"] for row in archive["eval_runs"]] == ["EVAL-OLD"]
    assert [row["eval_run_id"] for row in archive["eval_results"]] == ["EVAL-OLD"]
    connection = connect(paths.db_file)
    try:
        assert _ids(connection, "retrieval_runs", "run_id") == ["RET-CURRENT"]
        assert _ids(connection, "eval_runs", "eval_run_id") == ["EVAL-CURRENT"]
        assert _ids(connection, "eval_results", "eval_run_id") == ["EVAL-CURRENT"]
        assert _count(connection, "golden_cases") == 1
        assert _count(connection, "repair_tasks") == 1
    finally:
        connection.close()


def test_prune_stale_runs_suite_filter_only_applies_to_eval_runs(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_retrieval_run(connection, "RET-OLD", "old-code", _old_time())
        _insert_eval_run(connection, "EVAL-A", "suite-a", "old-code", _old_time())
        _insert_eval_result(connection, "EVAL-A", "CASE-A")
        _insert_eval_run(connection, "EVAL-B", "suite-b", "old-code", _old_time())
        _insert_eval_result(connection, "EVAL-B", "CASE-B")
        connection.commit()
    finally:
        connection.close()

    report = prune_stale_runs(
        paths.root,
        suite_id="suite-a",
        allow_without_current_baseline=True,
        dry_run=False,
    )

    retrieval_item = next(item for item in report.items if item.table == "retrieval_runs")
    assert retrieval_item.status == "skipped"
    assert report.summary["deleted_eval_runs"] == 1
    connection = connect(paths.db_file)
    try:
        assert _ids(connection, "retrieval_runs", "run_id") == ["RET-OLD"]
        assert _ids(connection, "eval_runs", "eval_run_id") == ["EVAL-B"]
        assert _ids(connection, "eval_results", "eval_run_id") == ["EVAL-B"]
    finally:
        connection.close()


def test_prune_stale_runs_older_than_filter_keeps_recent_candidates(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_retrieval_run(connection, "RET-OLD", "old-code", _old_time(days=30))
        _insert_retrieval_run(connection, "RET-RECENT", "old-code", _old_time(days=1))
        _insert_eval_run(connection, "EVAL-OLD", "suite-a", "old-code", _old_time(days=30))
        _insert_eval_run(connection, "EVAL-RECENT", "suite-a", "old-code", _old_time(days=1))
        connection.commit()
    finally:
        connection.close()

    report = prune_stale_runs(
        paths.root,
        older_than_days=10,
        allow_without_current_baseline=True,
        dry_run=False,
    )

    assert report.summary["deleted_retrieval_runs"] == 1
    assert report.summary["deleted_eval_runs"] == 1
    connection = connect(paths.db_file)
    try:
        assert _ids(connection, "retrieval_runs", "run_id") == ["RET-RECENT"]
        assert _ids(connection, "eval_runs", "eval_run_id") == ["EVAL-RECENT"]
    finally:
        connection.close()


def test_prune_stale_runs_can_keep_latest_code_versions(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_retrieval_run(connection, "RET-V1", "code-v1", _old_time(days=30))
        _insert_retrieval_run(connection, "RET-V2", "code-v2", _old_time(days=20))
        _insert_retrieval_run(connection, "RET-V3", "code-v3", _old_time(days=10))
        _insert_eval_run(connection, "EVAL-V1", "suite-a", "code-v1", _old_time(days=30))
        _insert_eval_run(connection, "EVAL-V2", "suite-a", "code-v2", _old_time(days=20))
        _insert_eval_run(connection, "EVAL-V3", "suite-a", "code-v3", _old_time(days=10))
        connection.commit()
    finally:
        connection.close()

    report = prune_stale_runs(paths.root, keep_latest_code_versions=2, dry_run=True)

    assert report.keep_latest_code_versions == 2
    retrieval_item = next(item for item in report.items if item.table == "retrieval_runs")
    eval_item = next(item for item in report.items if item.table == "eval_runs")
    assert retrieval_item.candidate_ids == ("RET-V1",)
    assert eval_item.candidate_ids == ("EVAL-V1",)


def test_prune_stale_runs_execute_blocks_without_current_baseline(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_retrieval_run(connection, "RET-OLD", "old-code", _old_time())
        _insert_eval_run(connection, "EVAL-OLD", "suite-a", "old-code", _old_time())
        _insert_eval_result(connection, "EVAL-OLD", "CASE-1")
        connection.commit()
    finally:
        connection.close()

    report = prune_stale_runs(paths.root, dry_run=False)

    assert report.status == "warn"
    assert report.archive_path is None
    assert report.summary["current_retrieval_runs"] == 0
    assert report.summary["current_eval_runs"] == 0
    assert report.summary["deleted_retrieval_runs"] == 0
    assert report.summary["deleted_eval_runs"] == 0
    assert {item.status for item in report.items} == {"blocked"}
    connection = connect(paths.db_file)
    try:
        assert _ids(connection, "retrieval_runs", "run_id") == ["RET-OLD"]
        assert _ids(connection, "eval_runs", "eval_run_id") == ["EVAL-OLD"]
        assert _ids(connection, "eval_results", "eval_run_id") == ["EVAL-OLD"]
    finally:
        connection.close()


def test_prune_stale_runs_execute_override_allows_no_current_baseline(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_retrieval_run(connection, "RET-OLD", "old-code", _old_time())
        connection.commit()
    finally:
        connection.close()

    report = prune_stale_runs(paths.root, allow_without_current_baseline=True, dry_run=False)

    assert report.status == "ok"
    assert report.summary["deleted_retrieval_runs"] == 1


def test_prune_stale_runs_cli_parser_and_json_output(tmp_path: Path, monkeypatch, capsys) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    parser = build_parser()

    default_parsed = parser.parse_args(["--root", str(paths.root), "prune-stale-runs"])
    assert default_parsed.dry_run is True

    parsed = parser.parse_args(
        [
            "--root",
            str(paths.root),
            "prune-stale-runs",
            "--suite-id",
            "suite-a",
            "--older-than-days",
            "7",
            "--keep-latest-code-versions",
            "2",
            "--archive-dir",
            str(tmp_path / "archives"),
            "--allow-without-current-baseline",
            "--keep-current-code-version",
            "--dry-run",
        ]
    )
    assert parsed.command == "prune-stale-runs"
    assert parsed.suite_id == "suite-a"
    assert parsed.older_than_days == 7
    assert parsed.keep_latest_code_versions == 2
    assert parsed.archive_dir == tmp_path / "archives"
    assert parsed.allow_without_current_baseline is True
    assert parsed.keep_current_code_version is True
    assert parsed.dry_run is True

    execute_parsed = parser.parse_args(["--root", str(paths.root), "prune-stale-runs", "--execute"])
    assert execute_parsed.dry_run is False

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "eakb",
            "--root",
            str(paths.root),
            "prune-stale-runs",
            "--dry-run",
        ],
    )
    main()

    output = json.loads(capsys.readouterr().out)
    assert output["dry_run"] is True
    assert output["summary"]["retrieval_runs"] == 0


def test_source_tree_content_hash_ignores_mtime(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    module = source_root / "module.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    first = _source_tree_content_hash(source_root)

    old_time = datetime.now(UTC).timestamp() - 1000
    module.touch()
    second = _source_tree_content_hash(source_root)
    module.write_text("VALUE = 2\n", encoding="utf-8")
    third = _source_tree_content_hash(source_root)

    assert first == second
    assert third != first


def _insert_retrieval_run(connection, run_id: str, code_version: str, created_at: str) -> None:
    connection.execute(
        """
        INSERT INTO retrieval_runs(
            run_id, query, query_type, doc_scope, retrieved_evidence_ids_json,
            reranked_ids_json, scores_json, code_version, metadata_json, created_at
        )
        VALUES (?, 'q', 'definition', 'global', '[]', '[]', '{}', ?, '{}', ?)
        """,
        (run_id, code_version, created_at),
    )


def _insert_eval_run(connection, eval_run_id: str, suite_id: str, code_version: str, started_at: str) -> None:
    connection.execute(
        """
        INSERT INTO eval_runs(
            eval_run_id, suite_id, started_at, finished_at, config_hash,
            code_version, result_summary_json, status
        )
        VALUES (?, ?, ?, ?, NULL, ?, '{}', 'passed')
        """,
        (eval_run_id, suite_id, started_at, started_at, code_version),
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


def _old_time(days: int = 30) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")


def _count(connection, table_name: str) -> int:
    return int(connection.execute(f"SELECT count(*) FROM {table_name}").fetchone()[0])


def _ids(connection, table_name: str, column_name: str) -> list[str]:
    rows = connection.execute(f"SELECT {column_name} FROM {table_name} ORDER BY {column_name}").fetchall()
    return [str(row[column_name]) for row in rows]
