"""Comparison intent answer-fact selection."""

from __future__ import annotations

from .answer_subgraph import _prioritize_subgraph_facts


def _select_comparison_answer_facts(
    facts: list[dict[str, object]],
    knowledge_subgraph: dict[str, object] | None,
) -> list[dict[str, object]]:
    ranked = _prioritize_subgraph_facts(facts, knowledge_subgraph)

    def comparison_score(item: dict[str, object]) -> tuple[float, float]:
        confidence = float(item.get("confidence") or 0.0)
        bonus = float(item.get("_subgraph_bonus") or 0.0)
        fact_type = str(item.get("fact_type") or "")
        if fact_type == "comparison_relation":
            bonus += 5.0
        elif fact_type in {"term_definition", "concept_definition"}:
            bonus += 2.0
        return (bonus + confidence, confidence)

    return sorted(ranked, key=comparison_score, reverse=True)
