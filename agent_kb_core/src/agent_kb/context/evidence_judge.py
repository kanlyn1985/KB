from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agent_kb.context.context_pack import AgentContextPack


@dataclass(frozen=True)
class EvidenceJudgement:
    """Deterministic assessment of whether selected context can support an answer."""

    status: str
    score: float
    required_shapes: list[str] = field(default_factory=list)
    covered_shapes: list[str] = field(default_factory=list)
    missing_shapes: list[str] = field(default_factory=list)
    evidence_count: int = 0
    fact_count: int = 0
    bound_fact_count: int = 0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_REQUIRED_GROUPS: dict[str, list[set[str]]] = {
    "definition": [{"term_definition", "parameter_definition"}],
    "constraint_lookup": [{"parameter_constraint", "requirement_constraint", "table_row"}],
    "test_method": [{"test_method", "test_condition", "procedure"}],
    "procedure": [{"procedure", "process_step", "test_method"}],
    "comparison": [{"comparison", "relation_evidence"}],
    "evidence_lookup": [{"evidence", "source_unit", "document"}],
}


def judge_context_pack(context_pack: AgentContextPack) -> EvidenceJudgement:
    frame = context_pack.query_frame
    fact_types = {fact.fact_type for fact in context_pack.facts}
    evidence_ids = {item.evidence_id for item in context_pack.evidence}
    bound_fact_count = sum(
        1
        for fact in context_pack.facts
        if any(evidence_id in evidence_ids for evidence_id in fact.evidence_ids)
    )

    groups = _REQUIRED_GROUPS.get(frame.intent, [])
    required_shapes = sorted({shape for group in groups for shape in group})
    covered_shapes = sorted(fact_types & set(required_shapes))
    missing_groups = [group for group in groups if not (group & fact_types)]
    missing_shapes = sorted({shape for group in missing_groups for shape in group})

    if groups:
        shape_score = (len(groups) - len(missing_groups)) / len(groups)
    else:
        shape_score = 1.0 if context_pack.facts or context_pack.evidence else 0.0
    evidence_score = 1.0 if context_pack.evidence else 0.0
    binding_score = bound_fact_count / len(context_pack.facts) if context_pack.facts else 0.0
    object_score = 1.0 if context_pack.target_objects or frame.intent == "general_search" else 0.0

    score = round(
        0.45 * shape_score
        + 0.30 * evidence_score
        + 0.15 * binding_score
        + 0.10 * object_score,
        4,
    )

    reasons: list[str] = []
    if missing_shapes:
        reasons.append("required evidence shape is missing")
    if not context_pack.evidence:
        reasons.append("no source evidence was selected")
    if context_pack.facts and not bound_fact_count:
        reasons.append("selected facts are not bound to selected evidence")
    if frame.missing_slots:
        reasons.append("query contains unresolved required slots")
        score = min(score, 0.74)
    if frame.ambiguity:
        reasons.append("query contains unresolved domain ambiguity")
        score = min(score, 0.49)

    if score >= 0.75 and not missing_shapes:
        status = "sufficient"
    elif score >= 0.40:
        status = "partial"
    else:
        status = "insufficient"

    return EvidenceJudgement(
        status=status,
        score=score,
        required_shapes=required_shapes,
        covered_shapes=covered_shapes,
        missing_shapes=missing_shapes,
        evidence_count=len(context_pack.evidence),
        fact_count=len(context_pack.facts),
        bound_fact_count=bound_fact_count,
        reasons=reasons,
    )
