from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb.doc_diagnostics import build_document_diagnostics
from test_helpers import resolve_doc_id_by_filename


WORKSPACE = Path("knowledge_base")


def test_doc7_diagnostics_exposes_core_metrics() -> None:
    doc_id = resolve_doc_id_by_filename("QC_T 1036", "逆变器")
    diagnostics = build_document_diagnostics(WORKSPACE, doc_id)

    assert diagnostics["doc_id"] == doc_id
    assert diagnostics["counts"]["page_count"] >= 20
    assert diagnostics["counts"]["evidence_count"] >= 10
    assert diagnostics["counts"]["fact_count"] >= 50
    assert diagnostics["coverage"]["answerability_score"] > 0
    assert "metadata_coverage" in diagnostics["coverage"]
    assert "text_coverage_rate" in diagnostics["coverage"]
    assert "uncovered_counts" in diagnostics["coverage"]
    assert diagnostics["artifacts"]["coverage_summary_path"].endswith(".summary.json")
    assert diagnostics["artifacts"]["coverage_report_path"].endswith(".coverage_report.md")
    assert "warnings" in diagnostics
