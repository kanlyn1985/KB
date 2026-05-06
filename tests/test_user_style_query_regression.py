from __future__ import annotations

import json
from pathlib import Path

import pytest

from enterprise_agent_kb.answer_api import answer_query
from enterprise_agent_kb.query_api import build_query_context
from enterprise_agent_kb.query_rewrite import rewrite_query


WORKSPACE = Path("knowledge_base")
CASES_PATH = Path("tests/generated/user_style_query_regression_cases_2026-04-23.json")
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_user_style_queries_rewrite(case: dict[str, object]) -> None:
    rewritten = rewrite_query(str(case["query"]))

    assert rewritten.query_type == case["expected_query_type"]
    assert rewritten.target_topic == case["expected_target_topic"]

    protected_anchor = case.get("expected_protected_anchor")
    if protected_anchor:
        assert protected_anchor in rewritten.protected_anchor_terms


@pytest.mark.integration
@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_user_style_queries_end_to_end(case: dict[str, object]) -> None:
    query = str(case["query"])
    answer = answer_query(WORKSPACE, query, limit=6)

    assert answer["answer_mode"] == case["expected_answer_mode"]
    if "expected_fallback_reason_any" in case:
        assert answer["fallback_reason"] in case["expected_fallback_reason_any"]
    else:
        assert answer["fallback_reason"] == case["expected_fallback_reason"]

    for token in case.get("direct_answer_contains_all", []):
        assert token in answer["direct_answer"]

    expected_top_entity_type = case.get("expected_top_entity_type")
    expected_top_entity_name = case.get("expected_top_entity_name")
    expected_top_entity_name_contains = case.get("expected_top_entity_name_contains")

    if expected_top_entity_type or expected_top_entity_name or expected_top_entity_name_contains:
        context = build_query_context(WORKSPACE, query, limit=6)
        candidates = context["topic_resolution"]["candidate_entities"]
        assert candidates
        top = candidates[0]
        if expected_top_entity_type:
            assert top["entity_type"] == expected_top_entity_type
        if expected_top_entity_name:
            assert top["canonical_name"] == expected_top_entity_name
        if expected_top_entity_name_contains:
            assert expected_top_entity_name_contains in top["canonical_name"]
