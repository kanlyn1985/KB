from __future__ import annotations

from enterprise_agent_kb.answer_policy import select_answer_policy
from enterprise_agent_kb.query_rewrite import rewrite_query


def test_definition_query_maps_to_definition_policy() -> None:
    rewritten = rewrite_query("V2G是怎么定义的")
    assert select_answer_policy(rewritten.query_type) == "definition"


def test_standard_query_maps_to_standard_policy() -> None:
    rewritten = rewrite_query("QC/T 1036—2016 的实施日期是什么？")
    assert select_answer_policy(rewritten.query_type) == "lifecycle_lookup"


def test_empty_query_maps_to_no_answer_policy() -> None:
    rewritten = rewrite_query("")
    assert select_answer_policy(rewritten.query_type) == "no_answer_candidate"


def test_type_enumeration_query_maps_to_comparison_policy() -> None:
    rewritten = rewrite_query("V2X有哪些类型")
    assert select_answer_policy(rewritten.query_type) == "comparison"
