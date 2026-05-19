from __future__ import annotations

from pathlib import Path

import pytest

from enterprise_agent_kb.answer_api import answer_query
from enterprise_agent_kb.pipeline import run_document_pipeline
from enterprise_agent_kb.query_api import build_query_context
from enterprise_agent_kb.generated_tests import generate_golden_tests_for_document
from test_helpers import resolve_doc_id_by_filename


WORKSPACE = Path("knowledge_base")


@pytest.mark.integration
def test_doc5_pipeline_regression() -> None:
    doc_id = resolve_doc_id_by_filename("40432", ".pdf")
    result = run_document_pipeline(WORKSPACE, doc_id)

    assert result.page_count >= 20
    assert result.evidence_count >= 10
    assert result.fact_count >= 3

    context = build_query_context(WORKSPACE, "GB/T 40432-2021", limit=6)
    assert context["hit_count"] > 0
    assert any(hit["doc_id"] == doc_id for hit in context["hits"])
    answer = answer_query(WORKSPACE, "GB/T 40432-2021 的标准号和实施日期是什么？", limit=6)
    assert "GB/T 40432—2021" in answer["direct_answer"]


@pytest.mark.integration
def test_doc6_pipeline_regression() -> None:
    doc_id = resolve_doc_id_by_filename("V2G", ".pdf")
    result = run_document_pipeline(WORKSPACE, doc_id)

    assert result.page_count >= 5
    assert result.evidence_count >= min(10, result.page_count)
    assert result.fact_count >= 2
    assert result.entity_count >= 2
    assert result.edge_count >= 1

    context = build_query_context(WORKSPACE, "ISO 15118", limit=6)
    assert context["hit_count"] > 0
    assert any(hit["doc_id"] == doc_id for hit in context["hits"])


@pytest.mark.integration
def test_doc7_pipeline_and_golden_regression() -> None:
    doc_id = resolve_doc_id_by_filename("QC_T 1036", "逆变器")
    result = run_document_pipeline(WORKSPACE, doc_id)

    assert result.page_count >= 20
    assert result.evidence_count >= 10
    assert result.fact_count >= 50

    context = build_query_context(WORKSPACE, "什么是汽车电源逆变器？", limit=6)
    assert context["hit_count"] > 0
    assert any(hit["doc_id"] == doc_id for hit in context["hits"])
    answer = answer_query(WORKSPACE, "什么是汽车电源逆变器？", limit=6)
    assert "汽车电源逆变器" in answer["direct_answer"]

    standard_answer = answer_query(WORKSPACE, "QC/T 1036—2016 的标准号和实施日期是什么？", limit=6)
    assert "QC/T 1036—2016" in standard_answer["direct_answer"]
    assert "2016-09-01" in standard_answer["direct_answer"]

    golden = generate_golden_tests_for_document(WORKSPACE, doc_id)
    assert golden["case_count"] >= 20
    assert golden["target_case_count"] >= 20
    assert golden["local_case_count"] >= 1
    assert golden["page_coverage_count"] >= 14
    assert len(golden["uncovered_pages"]) <= 1
