"""Smoke tests for the closed_loop_store submodules.

Each submodule was extracted from the historical 2692-line monolith; these
tests verify the public surface and a few representative behaviors. They run
without requiring a built KB (use in-memory sqlite where DB is needed).
"""
from __future__ import annotations

import sqlite3

import pytest

from enterprise_agent_kb.closed_loop_store import (
    _helpers,
    _runtime,
    _source_units,
    _golden_cases,
    _retrieval_eval_runs,
    _repair_tasks,
    _failure_diagnostics,
)


# ---- _helpers -----------------------------------------------------------

def test_helpers_public_functions() -> None:
    for name in (
        "_ratio", "_mean_metric", "re_sub_whitespace", "_normalize_text",
        "_pytest_output_counts", "_safe_json", "_json_list", "_optional_text",
        "_as_int", "_safe_float", "_clip", "_json_object", "_string_ids",
        "_text_values", "_stable_id", "_suggested_actions",
    ):
        assert callable(getattr(_helpers, name)), f"missing: {name}"


def test_stable_id_is_deterministic() -> None:
    a = _helpers._stable_id("X", "doc1", 1, "q1")
    b = _helpers._stable_id("X", "doc1", 1, "q1")
    c = _helpers._stable_id("X", "doc1", 1, "q2")
    assert a == b
    assert a != c
    assert a.startswith("X-")


def test_suggested_actions_unknown() -> None:
    result = _helpers._suggested_actions("totally_made_up_failure")
    assert isinstance(result, list)
    assert len(result) > 0


# ---- _runtime -----------------------------------------------------------

def test_runtime_short_hash() -> None:
    h1 = _runtime._short_hash("foo")
    h2 = _runtime._short_hash("foo")
    h3 = _runtime._short_hash("bar")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == _runtime.SHORT_HASH_LENGTH


def test_runtime_code_version() -> None:
    version = _runtime._runtime_code_version()
    assert isinstance(version, str)
    assert version  # non-empty


# ---- _source_units ------------------------------------------------------

def _in_memory_db() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    return connection


def test_source_units_module_loads() -> None:
    assert callable(_source_units.sync_source_units_from_matrix)
    assert callable(_source_units.ensure_source_unit_mapping_tables)
    assert callable(_source_units.backfill_source_unit_mappings_from_metadata)


def test_source_units_sync_inserts_rows() -> None:
    connection = _in_memory_db()
    connection.execute(
        """
        CREATE TABLE source_units (
            unit_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            page_no INTEGER,
            block_id TEXT,
            unit_type TEXT,
            text TEXT,
            normalized_text TEXT,
            canonical_title TEXT,
            canonical_key TEXT,
            content_role TEXT,
            quality_flags_json TEXT NOT NULL DEFAULT '[]',
            importance TEXT,
            expected_knowledge_type TEXT,
            status TEXT,
            metadata_json TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    rows = [
        {
            "unit_id": "U-1",
            "unit_type": "definition",
            "source_text": "CC 电阻是一种分流器。",
            "page_no": 12,
            "metadata": {"canonical_title": "CC 电阻"},
        },
        {
            "unit_id": "U-2",
            "unit_type": "requirement",
            "source_text": "过压保护阈值不应低于 100V。",
            "page_no": 18,
        },
    ]
    _source_units.sync_source_units_from_matrix(connection, "DOC-1", rows)
    count = connection.execute("SELECT COUNT(*) AS c FROM source_units").fetchone()["c"]
    assert count == 2


# ---- _golden_cases ------------------------------------------------------

def test_golden_cases_module_loads() -> None:
    assert callable(_golden_cases.sync_golden_cases)
    assert callable(_golden_cases.list_golden_cases)
    assert callable(_golden_cases.activate_golden_case_draft)
    assert callable(_golden_cases.draft_golden_case_from_failure)
    assert callable(_golden_cases.draft_golden_cases_from_eval_failures)


def test_golden_cases_sync_and_list_roundtrip() -> None:
    connection = _in_memory_db()
    connection.execute(
        """
        CREATE TABLE golden_cases (
            case_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            assert_mode TEXT,
            query TEXT,
            must_hit_json TEXT,
            negative_expected_json TEXT,
            expected_pages_json TEXT,
            expected_sections_json TEXT,
            expected_evidence_shape TEXT,
            status TEXT,
            source TEXT,
            metadata_json TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    cases = [
        {"case_id": "C-1", "query": "什么是 CC 电阻?", "must_hit": ["分流"], "assert_mode": "rich_answer"},
        {"case_id": "C-2", "query": "过压保护阈值?", "must_hit": ["100V"], "assert_mode": "constraint"},
    ]
    _golden_cases.sync_golden_cases(connection, "DOC-1", cases, source="unit_test")
    rows = _golden_cases.list_golden_cases(connection)
    assert len(rows) == 2
    case_ids = {row["case_id"] for row in rows}
    assert case_ids == {"C-1", "C-2"}


# ---- _retrieval_eval_runs ----------------------------------------------

def test_retrieval_eval_runs_module_loads() -> None:
    assert callable(_retrieval_eval_runs.record_retrieval_run)
    assert callable(_retrieval_eval_runs.record_eval_run)
    assert callable(_retrieval_eval_runs.list_eval_runs)
    assert callable(_retrieval_eval_runs.list_retrieval_runs)
    assert callable(_retrieval_eval_runs.get_eval_run_detail)
    assert callable(_retrieval_eval_runs.get_retrieval_run_detail)
    assert callable(_retrieval_eval_runs.compare_eval_runs)
    assert callable(_retrieval_eval_runs.load_golden_cases_from_file)


def test_retrieval_eval_runs_record_and_list() -> None:
    connection = _in_memory_db()
    connection.execute(
        """
        CREATE TABLE retrieval_runs (
            run_id TEXT PRIMARY KEY,
            query TEXT,
            query_type TEXT,
            doc_scope TEXT,
            retrieved_evidence_ids_json TEXT,
            reranked_ids_json TEXT,
            scores_json TEXT,
            code_version TEXT,
            metadata_json TEXT,
            created_at TEXT
        )
        """
    )
    rid = _retrieval_eval_runs.record_retrieval_run(
        connection,
        query="什么是 CC 电阻?",
        query_type="definition",
        doc_scope="DOC-1",
        retrieved_evidence_ids=["E-1", "E-2"],
        reranked_ids=["E-1"],
        scores={"relevance": 0.9},
    )
    assert rid is not None
    runs = _retrieval_eval_runs.list_retrieval_runs(connection)
    assert len(runs) == 1


# ---- _repair_tasks ------------------------------------------------------

def test_repair_tasks_module_loads() -> None:
    assert callable(_repair_tasks.list_repair_tasks)
    assert callable(_repair_tasks.update_repair_task_status)


def test_repair_tasks_priority() -> None:
    p1 = _repair_tasks._repair_task_priority("retrieval_miss")
    p2 = _repair_tasks._repair_task_priority("unknown")
    assert isinstance(p1, int)
    assert isinstance(p2, int)


# ---- _failure_diagnostics -----------------------------------------------

def test_failure_diagnostics_module_loads() -> None:
    assert callable(_failure_diagnostics.build_failure_analysis)


def test_failure_diagnostics_infer_type() -> None:
    result = _failure_diagnostics._infer_failure_type(
        failure_reason="retrieval returned no relevant docs",
        assert_mode="rich_answer",
        retrieved_items=[],
        metrics={},
        answer="",
    )
    assert isinstance(result, str)
    assert result  # non-empty


def test_noise_signals_detects_table_header() -> None:
    signals = _failure_diagnostics._noise_signals(["公共 header BASEPRACTICES"])
    assert "table_header_base_practices" in signals


# ---- end-to-end smoke ---------------------------------------------------

def test_package_reexports_match_legacy_api() -> None:
    """The package public API must still export the historical surface."""
    import enterprise_agent_kb.closed_loop_store as cls

    legacy_names = [
        "activate_golden_case_draft",
        "backfill_eval_run_scope_metadata",
        "backfill_source_unit_mappings_from_metadata",
        "build_failure_analysis",
        "compare_eval_runs",
        "draft_golden_case_from_failure",
        "draft_golden_cases_from_eval_failures",
        "ensure_source_unit_mapping_tables",
        "get_eval_run_detail",
        "get_retrieval_run_detail",
        "list_eval_runs",
        "list_golden_cases",
        "list_repair_tasks",
        "list_retrieval_runs",
        "load_golden_cases_from_file",
        "record_eval_run",
        "record_retrieval_run",
        "re_sub_whitespace",
        "sync_golden_cases",
        "sync_source_units_from_matrix",
        "update_repair_task_status",
        "utc_now",
    ]
    for name in legacy_names:
        assert hasattr(cls, name), f"missing public API: {name}"
        assert callable(getattr(cls, name)), f"not callable: {name}"
