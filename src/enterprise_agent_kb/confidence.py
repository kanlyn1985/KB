from __future__ import annotations


def compute_confidence_score(
    *,
    answer_mode: str,
    direct_answer: str,
    supporting_facts: list[dict[str, object]],
    supporting_evidence: list[dict[str, object]],
    warnings: list[str],
) -> float:
    score = 0.0

    if direct_answer and direct_answer != "没有找到足够的结构化结果。":
        score += 0.2

    if answer_mode in {"definition", "standard_lookup", "lifecycle_lookup", "timing_lookup", "test_method_lookup"}:
        score += 0.1

    score += min(len(supporting_facts) * 0.18, 0.4)
    score += min(len(supporting_evidence) * 0.08, 0.2)

    if supporting_facts:
        fact_confidence = sum(float(item.get("confidence") or 0) for item in supporting_facts) / max(len(supporting_facts), 1)
        score += min(fact_confidence * 0.15, 0.15)

    if supporting_evidence:
        evidence_confidence = sum(float(item.get("confidence") or 0) for item in supporting_evidence) / max(len(supporting_evidence), 1)
        score += min(evidence_confidence * 0.1, 0.1)

    if warnings:
        score -= min(len(warnings) * 0.12, 0.36)

    if not supporting_facts and not supporting_evidence:
        score -= 0.25

    return round(max(0.0, min(1.0, score)), 3)
