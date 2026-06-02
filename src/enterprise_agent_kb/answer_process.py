from __future__ import annotations

import json
import re

from .evidence_shapes import is_test_method_query, looks_like_test_method_blob
from .answer_subgraph import _prioritize_subgraph_facts
from .answer_query_parsing import _is_timing_query, _is_activity_process_query, _special_appendix_c_requested


"""Process/timing intent answer generation and fact selection."""


def _select_process_answer_facts(
    facts: list[dict[str, object]],
    knowledge_subgraph: dict[str, object] | None,
    query: str = "",
) -> list[dict[str, object]]:
    ranked = _prioritize_subgraph_facts(facts, knowledge_subgraph)
    if is_test_method_query(query):
        test_methods = [
            item for item in ranked
            if str(item.get("fact_type") or "") == "process_fact"
            and looks_like_test_method_blob(
                query,
                json.dumps(item.get("object_value"), ensure_ascii=False)
                if isinstance(item.get("object_value"), (dict, list))
                else str(item.get("object_value") or ""),
            )
        ]
        if test_methods:
            primary_group = _test_method_group_key(test_methods[0])
            if primary_group:
                grouped = [item for item in test_methods if _test_method_group_key(item) == primary_group]
                if grouped:
                    return grouped
            return test_methods[:6]

    if _is_timing_query(query):
        timing_items = [item for item in ranked if _matches_timing_answer_shape(query, item)]
        if timing_items:
            ranked = timing_items

    def process_score(item: dict[str, object]) -> tuple[float, float]:
        confidence = float(item.get("confidence") or 0.0)
        bonus = float(item.get("_subgraph_bonus") or 0.0)
        fact_type = str(item.get("fact_type") or "")
        payload = item.get("object_value")
        blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
        if fact_type == "transition_fact":
            bonus += 5.0
        elif fact_type == "process_fact":
            bonus += 4.0
        elif fact_type == "table_requirement":
            bonus += 1.0
        if _is_timing_query(query) and "表 A.7" in blob:
            bonus += 8.0
        elif _is_timing_query(query) and "表 C.3" in blob and not _special_appendix_c_requested(query):
            bonus -= 2.0
        if any(token in blob for token in ("前言", "前    言", "目 次", "目次")):
            bonus -= 10.0
        return (bonus + confidence, confidence)

    transitions = sorted((item for item in ranked if item.get("fact_type") == "transition_fact"), key=process_score, reverse=True)
    processes = sorted((item for item in ranked if item.get("fact_type") == "process_fact"), key=process_score, reverse=True)
    others = sorted(
        (item for item in ranked if item.get("fact_type") not in {"transition_fact", "process_fact"}),
        key=process_score,
        reverse=True,
    )
    if _is_activity_process_query(query) and not _is_timing_query(query):
        return processes + others + transitions
    return transitions + processes + others


def _matches_timing_answer_shape(query: str, item: dict[str, object]) -> bool:
    payload = item.get("object_value")
    blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
    normalized = re.sub(r"\s+", "", blob)
    if _special_appendix_c_requested(query):
        return "表C.3" in normalized or "状态转换" in normalized or "控制导引电路状态转换" in normalized
    return (
        "表A.7" in normalized
        or "控制时序" in normalized
        or ("状态转换" in normalized and "表C.3" not in normalized)
    )


def _test_method_group_key(item: dict[str, object]) -> str:
    payload = item.get("object_value")
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("process_name") or payload.get("title") or "").strip()
