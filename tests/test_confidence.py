from __future__ import annotations

from enterprise_agent_kb.confidence import compute_confidence_score


def test_confidence_higher_with_fact_and_evidence_support() -> None:
    high = compute_confidence_score(
        answer_mode="definition",
        direct_answer="V2G: ...",
        supporting_facts=[{"confidence": 0.92}],
        supporting_evidence=[{"confidence": 0.9}],
        warnings=[],
    )
    low = compute_confidence_score(
        answer_mode="general_search",
        direct_answer="没有找到足够的结构化结果。",
        supporting_facts=[],
        supporting_evidence=[],
        warnings=[],
    )
    assert high > low


def test_confidence_reduced_by_warnings() -> None:
    without_warning = compute_confidence_score(
        answer_mode="standard_lookup",
        direct_answer="标准号是 QC/T 1036—2016。",
        supporting_facts=[{"confidence": 0.8}],
        supporting_evidence=[],
        warnings=[],
    )
    with_warning = compute_confidence_score(
        answer_mode="standard_lookup",
        direct_answer="标准号是 QC/T 1036—2016。",
        supporting_facts=[{"confidence": 0.8}],
        supporting_evidence=[],
        warnings=["DOC-000007 质量状态为 review_required"],
    )
    assert with_warning < without_warning
