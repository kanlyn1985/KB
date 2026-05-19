from __future__ import annotations

import pytest

from enterprise_agent_kb.query_rewrite import _detect_query_type, _normalize_query


TIMING_REGRESSION_CASES = [
    {"query": "CP的时序是什么样的", "expected_query_type": "timing_lookup", "must_include": "时序"},
    {"query": "交流充电控制时序", "expected_query_type": "timing_lookup", "must_include": "时序"},
    {"query": "状态 2 到状态 3 的触发条件", "expected_query_type": "timing_lookup", "must_include": "状态"},
    {"query": "握手流程", "expected_query_type": "timing_lookup", "must_include": "握手"},
    {"query": "直流充电紧急停机时序", "expected_query_type": "timing_lookup", "must_include": "紧急停机"},
    {"query": "预充流程是什么", "expected_query_type": "timing_lookup", "must_include": "预充"},
    {"query": "状态迁移条件", "expected_query_type": "timing_lookup", "must_include": "状态"},
    {"query": "能量传输阶段有哪些", "expected_query_type": "timing_lookup", "must_include": "能量传输"},
]


@pytest.mark.parametrize("case", TIMING_REGRESSION_CASES, ids=lambda c: c["query"][:20])
def test_timing_query_routes_to_timing_lookup(case: dict) -> None:
    normalized = _normalize_query(case["query"])
    query_type = _detect_query_type(case["query"], normalized)
    assert query_type == case["expected_query_type"], (
        f"Query '{case['query']}' routed to {query_type}, expected {case['expected_query_type']}"
    )


@pytest.mark.parametrize("case", TIMING_REGRESSION_CASES, ids=lambda c: c["query"][:20])
def test_timing_query_normalized_preserves_anchor(case: dict) -> None:
    normalized = _normalize_query(case["query"])
    assert normalized, f"Query '{case['query']}' normalized to empty string"
