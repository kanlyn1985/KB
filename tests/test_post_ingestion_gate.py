"""Integration tests for the post-ingestion quality gate.

These tests verify that the gate runs as part of the build pipeline
and populates PipelineResult.post_ingestion_gate correctly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture
def workspace():
    """Provide the workspace path."""
    return ROOT / "knowledge_base"


def test_gate_runs_on_existing_doc(workspace) -> None:
    """Running the gate on an existing doc should return a passed result
    (since DOC-000001 already has facts/evidence/expected_points)."""
    from enterprise_agent_kb.pipeline import run_post_ingestion_gate

    result = run_post_ingestion_gate(workspace, "DOC-000001")
    assert result.passed is True
    step_names = [name for name, _, _ in result.steps]
    assert "fts_refresh" in step_names
    assert "expected_points_generation" in step_names
    assert "term_definition_sync" in step_names
    assert "sanity_check" in step_names


def test_gate_result_to_dict(workspace) -> None:
    """The gate result should serialize to a dict with passed + steps list."""
    from enterprise_agent_kb.pipeline import run_post_ingestion_gate

    result = run_post_ingestion_gate(workspace, "DOC-000001")
    payload = result.to_dict()
    assert "passed" in payload
    assert "steps" in payload
    assert payload["passed"] is True
    assert all("name" in s and "passed" in s and "detail" in s
               for s in payload["steps"])


def test_gate_idempotent(workspace) -> None:
    """Running the gate twice should not introduce duplicates or fail."""
    from enterprise_agent_kb.pipeline import run_post_ingestion_gate

    r1 = run_post_ingestion_gate(workspace, "DOC-000001")
    r2 = run_post_ingestion_gate(workspace, "DOC-000001")
    assert r1.passed
    assert r2.passed


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
