from __future__ import annotations

from pathlib import Path

import pytest

from enterprise_agent_kb.answer_api import answer_query
from enterprise_agent_kb.agent_tools import run_agent_query
from enterprise_agent_kb.query_api import build_query_context
from test_helpers import resolve_doc_id_by_filename


WORKSPACE = Path("knowledge_base")


@pytest.mark.integration
@pytest.mark.benchmark
def test_query_context_standard_doc3_returns_expected_fact() -> None:
    context = build_query_context(WORKSPACE, "GB/T 18487.1—2023", limit=6)

    assert context["hit_count"] > 0
    assert any(doc["doc_id"] == "DOC-000003" for doc in context["documents"])
    assert any(
        fact["fact_type"] == "document_standard"
        and fact["object_value"].get("value") == "GB/T 18487.1—2023"
        for fact in context["facts"]
    )


@pytest.mark.integration
@pytest.mark.benchmark
def test_query_context_standard_doc4_returns_expected_fact() -> None:
    doc_id = resolve_doc_id_by_filename("18487.5", ".pdf")
    context = build_query_context(WORKSPACE, "GB/T 18487.5—2024", limit=6)

    assert context["hit_count"] > 0
    assert any(doc["doc_id"] == doc_id for doc in context["documents"])
    assert any(
        fact["fact_type"] == "document_standard"
        and fact["object_value"].get("value") == "GB/T 18487.5—2024"
        for fact in context["facts"]
    ) or any(
        item["doc_id"] == doc_id and "GB/T18487.5—2024" in item["normalized_text"]
        for item in context["evidence"]
    )


@pytest.mark.integration
@pytest.mark.benchmark
def test_answer_query_prefers_doc3_for_doc3_standard_question() -> None:
    answer = answer_query(WORKSPACE, "GBT 18487.1-2023 的标准号和实施日期是什么？", limit=6)

    assert "GB/T 18487.1—2023" in answer["direct_answer"]
    assert "2024-04-01" in answer["direct_answer"]
    assert answer["supporting_facts"]
    assert answer["supporting_facts"][0]["fact_type"] == "document_standard"
    assert answer["supporting_facts"][0]["object"]["value"] == "GB/T 18487.1—2023"


@pytest.mark.integration
@pytest.mark.benchmark
def test_answer_query_prefers_doc4_for_doc4_standard_question() -> None:
    answer = answer_query(WORKSPACE, "GB/T 18487.5—2024", limit=6)

    assert "GB/T 18487.5—2024" in answer["direct_answer"]
    assert answer["supporting_facts"]
    assert answer["supporting_facts"][0]["fact_type"] == "document_standard"
    assert answer["supporting_facts"][0]["object"]["value"] == "GB/T 18487.5—2024"


@pytest.mark.integration
@pytest.mark.benchmark
def test_agent_query_returns_definition_first_for_control_pilot() -> None:
    result = run_agent_query(WORKSPACE, "什么是控制导引电路？", limit=6)
    final_answer = result.final_answer

    assert "控制导引电路 control pilot circuit" in final_answer["direct_answer"]
    assert final_answer["supporting_facts"]
    assert final_answer["supporting_facts"][0]["fact_type"] == "term_definition"
    assert "信号传输或通信的电路" in final_answer["supporting_facts"][0]["object"]["definition"]
