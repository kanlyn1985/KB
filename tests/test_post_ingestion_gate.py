"""Tests for the post-ingestion quality gate.

WP4 (Sprint 1): the gate tests were previously bound to the production
``DOC-000001``, which is an *orphan* doc_id (14 dangling facts, 0 pages,
0 evidence, not in ``documents``). That made the gate's sanity_check fail
and coupled the tests to mutable production state (the gate also inserts
term_definition facts as a side effect).

Per the stabilization guide (WP4: "把测试数据和真实库差异隔离，避免测试
依赖污染主库"), the gate tests now run against an isolated tmp workspace
seeded with a minimal doc (1 page / 1 block / 1 evidence / 1 fact / 1
expected_points row). No production DB is touched; no LLM/subprocess is
invoked (expected_points already exists -> step 2 is a no-op).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


SCHEMA_PATH = ROOT / "src" / "enterprise_agent_kb" / "schema.sql"
MIGRATIONS_DIR = ROOT / "src" / "enterprise_agent_kb" / "migrations"

_NOW = "2026-06-24T00:00:00+00:00"


@pytest.fixture
def seeded_workspace(tmp_path: Path):
    """An isolated workspace with one minimal fully-searchable document."""
    from enterprise_agent_kb.bootstrap import initialize_workspace
    from enterprise_agent_kb.db import connect
    from enterprise_agent_kb.migrations import apply_pending_migrations

    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    conn = connect(paths.db_file)
    try:
        # Apply migrations (e.g. 001_expected_points) so the gate's
        # expected_points step has its table in a fresh workspace.
        apply_pending_migrations(conn, MIGRATIONS_DIR)
        conn.execute(
            """
            INSERT INTO documents (
                doc_id, source_filename, source_type, mime_type, sha256, file_size,
                page_count, language, version_label, source_path, ingest_time,
                update_time, parse_status, quality_status, is_active
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            ("DOC-TEST", "t.pdf", "pdf", "application/pdf", "sha", 1, 1, None,
             None, str(paths.raw / "t.pdf"), _NOW, _NOW, "parsed", "passed", 1),
        )
        conn.execute(
            """
            INSERT INTO pages (
                page_id, doc_id, page_no, width, height, parser_confidence,
                ocr_confidence, risk_level, page_status, screenshot_path,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            ("PAGE-1", "DOC-TEST", 1, None, None, 0.9, 0.9, "low", "ready",
             None, _NOW, _NOW),
        )
        conn.execute(
            """
            INSERT INTO blocks (
                block_id, page_id, doc_id, block_type, reading_order,
                text_content, raw_text, bbox_json, parser_confidence,
                ocr_confidence, risk_flags_json, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            ("BLK-1", "PAGE-1", "DOC-TEST", "ocr_markdown", 1,
             "# 范围\n本标准规定了车载诊断系统的通用要求。", "# 范围",
             None, 0.9, 0.9, "[]", _NOW, _NOW),
        )
        conn.execute(
            """
            INSERT INTO evidence (
                evidence_id, doc_id, page_id, block_id, block_type, raw_text,
                normalized_text, image_ref, table_ref, page_no, confidence,
                risk_level, evidence_status, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            ("EV-1", "DOC-TEST", "PAGE-1", "BLK-1", "ocr_markdown",
             "# 范围", "# 范围\n本标准规定了车载诊断系统的通用要求。", None,
             None, 1, 0.9, "low", "ready", _NOW, _NOW),
        )
        conn.execute(
            """
            INSERT INTO facts (
                fact_id, fact_type, subject_entity_id, predicate, object_value,
                object_entity_id, qualifiers_json, confidence, fact_status,
                source_doc_id, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            ("FACT-1", "requirement", None, "specifies",
             '{"text":"车载诊断系统通用要求"}', None,
             '{"page_no":1,"source":"fixture"}', 0.9, "ready", "DOC-TEST",
             _NOW, _NOW),
        )
        # Pre-existing expected_points row -> step 2 (regeneration) is a no-op,
        # avoiding any LLM/subprocess call. Empty points_json -> step 3
        # (term_definition_sync) inserts 0, keeping the test deterministic.
        conn.execute(
            """
            INSERT INTO expected_points (doc_id, version, point_count, points_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("DOC-TEST", "v1", 1, "[]", _NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return paths.root


def test_gate_runs_on_existing_doc(seeded_workspace) -> None:
    """Running the gate on a fully-ingested doc should pass and run all steps."""
    from enterprise_agent_kb.pipeline import run_post_ingestion_gate

    result = run_post_ingestion_gate(seeded_workspace, "DOC-TEST")
    assert result.passed is True
    step_names = [name for name, _, _ in result.steps]
    assert "fts_refresh" in step_names
    assert "expected_points_generation" in step_names
    assert "term_definition_sync" in step_names
    assert "sanity_check" in step_names


def test_gate_result_to_dict(seeded_workspace) -> None:
    """The gate result should serialize to a dict with passed + steps list."""
    from enterprise_agent_kb.pipeline import run_post_ingestion_gate

    result = run_post_ingestion_gate(seeded_workspace, "DOC-TEST")
    payload = result.to_dict()
    assert "passed" in payload
    assert "steps" in payload
    assert payload["passed"] is True
    assert all("name" in s and "passed" in s and "detail" in s
               for s in payload["steps"])


def test_gate_idempotent(seeded_workspace) -> None:
    """Running the gate twice should not introduce duplicates or fail."""
    from enterprise_agent_kb.pipeline import run_post_ingestion_gate

    r1 = run_post_ingestion_gate(seeded_workspace, "DOC-TEST")
    r2 = run_post_ingestion_gate(seeded_workspace, "DOC-TEST")
    assert r1.passed
    assert r2.passed
    # Idempotent: second run must not duplicate evidence/facts.
    from enterprise_agent_kb.db import connect
    from enterprise_agent_kb.config import AppPaths
    paths = AppPaths.from_root(seeded_workspace)
    conn = connect(paths.db_file)
    try:
        ev = conn.execute("SELECT COUNT(*) FROM evidence WHERE doc_id=?", ("DOC-TEST",)).fetchone()[0]
        fc = conn.execute("SELECT COUNT(*) FROM facts WHERE source_doc_id=?", ("DOC-TEST",)).fetchone()[0]
    finally:
        conn.close()
    assert ev == 1
    assert fc == 1


def test_pipeline_result_has_gate_field() -> None:
    """PipelineResult dataclass should have post_ingestion_gate field."""
    import dataclasses
    from enterprise_agent_kb.pipeline import PipelineResult

    fields = {f.name for f in dataclasses.fields(PipelineResult)}
    assert "post_ingestion_gate" in fields


def test_pipeline_result_default_gate_is_none() -> None:
    """PipelineResult.post_ingestion_gate defaults to None when not set."""
    from enterprise_agent_kb.pipeline import PipelineResult

    # Construct a minimal PipelineResult
    pr = PipelineResult(
        doc_id="TEST", registered=False, deduplicated=False,
        parser_engine="x", page_count=0, block_count=0,
        overall_score=0.0, evidence_count=0, fact_count=0,
        entity_count=0, wiki_page_count=0, edge_count=0,
        coverage_source_unit_count=0, coverage_text_rate=0.0,
        coverage_semantic_rate=0.0, coverage_object_rate=0.0,
        coverage_test_rate=0.0, coverage_uncovered_count=0,
        coverage_summary_path="", coverage_report_path="",
        ingestion_acceptance={},
    )
    assert pr.post_ingestion_gate is None
