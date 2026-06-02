"""Tests for quality_gate module."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from enterprise_agent_kb.config import AppPaths
from enterprise_agent_kb.db import connect
from enterprise_agent_kb.quality_gate import (
    QualityGateResult,
    QualityWeights,
    compute_quality_gate,
)
from enterprise_agent_kb.quality import read_coverage_rates, read_contract_status


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "src" / "enterprise_agent_kb" / "schema.sql"


def _init_workspace(root: Path) -> AppPaths:
    """Initialize a minimal workspace with schema."""
    from enterprise_agent_kb.bootstrap import initialize_workspace
    return initialize_workspace(root, SCHEMA_PATH)


def _seed_document(db_file: Path, doc_id: str) -> None:
    """Insert a minimal document row."""
    conn = connect(db_file)
    try:
        conn.execute(
            """
            INSERT INTO documents(
                doc_id, source_filename, source_type, mime_type, sha256, file_size,
                page_count, language, version_label, source_path, ingest_time,
                update_time, parse_status, quality_status, is_active
            )
            VALUES (?, 'test.pdf', 'pdf', 'application/pdf', 'abc', 100,
                    1, 'zh', 'v1', 'test.pdf', '2026-01-01T00:00:00Z',
                    '2026-01-01T00:00:00Z', 'parsed', 'passed', 1)
            """,
            (doc_id,),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_page(db_file: Path, doc_id: str, page_no: int = 1) -> None:
    """Insert a minimal page row."""
    conn = connect(db_file)
    try:
        conn.execute(
            """
            INSERT INTO pages(page_id, doc_id, page_no, page_status, risk_level, created_at, updated_at)
            VALUES (?, ?, ?, 'ready', 'low', 'now', 'now')
            """,
            (f"PAGE-{page_no}", doc_id, page_no),
        )
        conn.commit()
    finally:
        conn.close()


def _write_normalized_json(root: Path, doc_id: str) -> None:
    """Write a minimal normalized JSON file."""
    paths = AppPaths.from_root(root)
    normalized_path = paths.normalized / f"{doc_id}.json"
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_path.write_text(
        json.dumps({"doc_id": doc_id, "pages": [], "page_count": 0, "block_count": 0}),
        encoding="utf-8",
    )


def _write_coverage_summary(root: Path, doc_id: str, test_rate: float = 0.0) -> None:
    """Write a coverage summary JSON file."""
    paths = AppPaths.from_root(root)
    summary_path = paths.coverage_reports / f"{doc_id}.summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps({
            "doc_id": doc_id,
            "source_unit_count": 10,
            "text_coverage_rate": 1.0,
            "semantic_coverage_rate": 1.0,
            "object_coverage_rate": 1.0,
            "test_coverage_rate": test_rate,
        }),
        encoding="utf-8",
    )


def _write_acceptance_report(root: Path, doc_id: str, active: int = 6, failed: int = 0) -> None:
    """Write a minimal ingestion acceptance report."""
    report_dir = root / "acceptance_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{doc_id}.ingestion_acceptance.json"
    report_path.write_text(
        json.dumps({
            "knowledge_contracts": {
                "active_contract_count": active,
                "failed_count": failed,
            },
        }),
        encoding="utf-8",
    )


def test_quality_weights_defaults() -> None:
    """QualityWeights defaults sum to 1.0."""
    w = QualityWeights()
    assert abs(w.parse_quality + w.knowledge_completeness + w.test_coverage + w.contract_compliance - 1.0) < 0.001


def test_quality_weights_custom() -> None:
    """QualityWeights can be customized."""
    w = QualityWeights(parse_quality=0.5, knowledge_completeness=0.2, test_coverage=0.2, contract_compliance=0.1)
    assert w.parse_quality == 0.5


def test_read_coverage_rates_missing_file(tmp_path: Path) -> None:
    """read_coverage_rates returns defaults when file is missing."""
    result = read_coverage_rates(tmp_path, "DOC-NONEXIST")
    assert result["test_coverage_rate"] == 0.0
    assert result["text_coverage_rate"] == 0.0


def test_read_contract_status_missing_file(tmp_path: Path) -> None:
    """read_contract_status returns defaults when file is missing."""
    result = read_contract_status(tmp_path, "DOC-NONEXIST")
    assert result["pass_rate"] == 0.0
    assert result["failed_count"] == 0


def test_read_coverage_rates_with_data(tmp_path: Path) -> None:
    """read_coverage_rates reads test_coverage_rate from summary file."""
    _write_coverage_summary(tmp_path, "DOC-COV", test_rate=0.75)
    result = read_coverage_rates(tmp_path, "DOC-COV")
    assert result["test_coverage_rate"] == 0.75


def test_read_contract_status_with_data(tmp_path: Path) -> None:
    """read_contract_status computes from DB (source of truth)."""
    paths = _init_workspace(tmp_path / "kb")
    # Insert a document and the required facts so the standard_metadata
    # contract (required=True) activates and passes.
    conn = connect(paths.db_file)
    try:
        conn.execute(
            "INSERT INTO documents(doc_id, source_filename, source_type, mime_type, sha256, file_size, "
            "page_count, language, version_label, source_path, ingest_time, update_time, "
            "parse_status, quality_status, is_active) "
            "VALUES(?, 't.pdf', 'pdf', 'application/pdf', 'abc', 100, 1, 'zh', 'v1', 't.pdf', "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', 'parsed', 'passed', 1)",
            ("DOC-CONT",),
        )
        # Insert facts for the standard_metadata contract's fact_types
        conn.execute(
            "INSERT INTO facts(fact_id, fact_type, predicate, object_value, fact_status, source_doc_id, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'now', 'now')",
            ("f1", "document_standard", "has_standard", "GB/T 12345", "active", "DOC-CONT"),
        )
        conn.execute(
            "INSERT INTO facts(fact_id, fact_type, predicate, object_value, fact_status, source_doc_id, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'now', 'now')",
            ("f2", "document_title", "has_title", "Test Title", "active", "DOC-CONT"),
        )
        conn.commit()
    finally:
        conn.close()

    result = read_contract_status(paths.root, "DOC-CONT")
    # standard_metadata contract is required and should be active + passed
    assert result["active_count"] >= 1
    assert result["failed_count"] == 0


def test_compute_quality_gate_blocked(tmp_path: Path) -> None:
    """compute_quality_gate returns blocked when blocked_count > 0."""
    paths = _init_workspace(tmp_path / "kb")
    doc_id = "DOC-GATE-BLOCK"
    _seed_document(paths.db_file, doc_id)
    _seed_page(paths.db_file, doc_id, page_no=1)
    # Write a normalized file with a page that triggers blocked status
    # (text_blocks=0 and has_ocr_markdown=True)
    normalized_path = paths.normalized / f"{doc_id}.json"
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_path.write_text(
        json.dumps({
            "doc_id": doc_id,
            "pages": [
                {
                    "page_no": 1,
                    "blocks": [
                        {"block_type": "ocr_markdown", "text": ""},
                    ],
                },
            ],
            "page_count": 1,
            "block_count": 1,
        }),
        encoding="utf-8",
    )
    _write_coverage_summary(paths.root, doc_id, test_rate=0.5)
    _write_acceptance_report(paths.root, doc_id, active=6, failed=0)

    result = compute_quality_gate(paths.root, doc_id)
    assert isinstance(result, QualityGateResult)
    assert result.gate_status == "blocked"
    assert result.blocked_count > 0


def test_compute_quality_gate_weights_affect_score(tmp_path: Path) -> None:
    """Custom weights change the overall score."""
    paths = _init_workspace(tmp_path / "kb")
    doc_id = "DOC-WEIGHTS"
    _seed_document(paths.db_file, doc_id)
    _seed_page(paths.db_file, doc_id)
    _write_normalized_json(paths.root, doc_id)
    _write_coverage_summary(paths.root, doc_id, test_rate=0.5)
    _write_acceptance_report(paths.root, doc_id, active=6, failed=0)

    result_default = compute_quality_gate(paths.root, doc_id)

    heavy_test = QualityWeights(parse_quality=0.1, knowledge_completeness=0.1, test_coverage=0.7, contract_compliance=0.1)
    result_heavy = compute_quality_gate(paths.root, doc_id, weights=heavy_test)

    # With test_coverage=0.5 and weight 0.7 vs 0.25, heavy should give different overall
    assert result_default.overall_score != result_heavy.overall_score