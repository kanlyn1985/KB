"""Standard lookup intent answer-fact selection."""

from __future__ import annotations

from .answer_query_parsing import _normalize_standard_code, _extract_standard_from_query
from .answer_subgraph import _prioritize_subgraph_facts


def _select_standard_answer_facts(
    facts: list[dict[str, object]],
    knowledge_subgraph: dict[str, object] | None,
    query: str,
) -> list[dict[str, object]]:
    ranked = _prioritize_subgraph_facts(facts, knowledge_subgraph)
    target_standard = _normalize_standard_code(_extract_standard_from_query(query))

    def standard_score(item: dict[str, object]) -> tuple[float, float]:
        confidence = float(item.get("confidence") or 0.0)
        bonus = float(item.get("_subgraph_bonus") or 0.0)
        fact_type = str(item.get("fact_type") or "")
        payload = item.get("object_value")
        payload_dict = payload if isinstance(payload, dict) else {}

        if fact_type == "document_standard":
            bonus += 6.0
            value = _normalize_standard_code(str(payload_dict.get("value") or ""))
            if target_standard and value == target_standard:
                bonus += 6.0
        elif fact_type == "document_lifecycle":
            bonus += 5.0
            if str(item.get("predicate") or "") == "effective_date":
                bonus += 1.5
        elif fact_type == "document_versioning":
            bonus += 4.0
        else:
            bonus -= 4.0
        return (bonus + confidence, confidence)

    ordered = sorted(ranked, key=standard_score, reverse=True)
    preferred = [
        item for item in ordered
        if str(item.get("fact_type") or "") in {"document_standard", "document_lifecycle", "document_versioning"}
    ]
    others = [
        item for item in ordered
        if str(item.get("fact_type") or "") not in {"document_standard", "document_lifecycle", "document_versioning"}
    ]
    return preferred + others
