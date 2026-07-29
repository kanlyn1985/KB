"""ContextPack — primary Agent-facing output of kb-ontology."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kb_ontology.judgement.models import Judgement
from kb_ontology.query.frame import HitEntity, QueryFrame, QueryResult


@dataclass(frozen=True)
class ContextPack:
    """Structured knowledge + judgement for the Agent (not a final NL answer)."""

    query_frame: QueryFrame
    intent: str
    hits: list[HitEntity] = field(default_factory=list)
    related: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    knowledge_gaps: list[str] = field(default_factory=list)
    judgement: Judgement | None = None
    recommended_answer_strategy: str = "answer_with_evidence"
    query_result_meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_frame": self.query_frame.to_dict(),
            "intent": self.intent,
            "hits": [h.to_dict() for h in self.hits],
            "related": list(self.related),
            "evidence": list(self.evidence),
            "warnings": list(self.warnings),
            "knowledge_gaps": list(self.knowledge_gaps),
            "judgement": self.judgement.to_dict() if self.judgement else None,
            "recommended_answer_strategy": self.recommended_answer_strategy,
            "query_result_meta": dict(self.query_result_meta),
            "hit_count": len(self.hits),
            "evidence_sufficient": (
                self.judgement.status == "sufficient" if self.judgement else False
            ),
        }

    @property
    def is_empty(self) -> bool:
        return len(self.hits) == 0


def assemble_context_pack(
    result: QueryResult,
    judgement: Judgement,
) -> ContextPack:
    """Merge template result + judgement into the Agent ContextPack."""
    warnings = list(result.warnings)
    for reason in judgement.reasons:
        if reason not in warnings:
            # Keep pack warnings focused; structural reasons live in judgement.
            pass
    for amb in judgement.ambiguities:
        flag = f"ambiguity:{amb}"
        if flag not in warnings:
            warnings.append(flag)
    for conf in judgement.conflicts:
        if conf not in warnings:
            warnings.append(conf)

    # Dedupe evidence dicts by id.
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket in (result.evidence, *(h.evidence for h in result.hits)):
        for item in bucket:
            if not isinstance(item, dict):
                continue
            eid = str(item.get("id") or "")
            if eid and eid in seen:
                continue
            if eid:
                seen.add(eid)
            evidence.append(item)

    gaps = list(dict.fromkeys(list(judgement.knowledge_gaps)))

    return ContextPack(
        query_frame=result.frame,
        intent=result.intent,
        hits=list(result.hits),
        related=list(result.related),
        evidence=evidence,
        warnings=warnings,
        knowledge_gaps=gaps,
        judgement=judgement,
        recommended_answer_strategy=judgement.recommended_strategy,
        query_result_meta={
            "template_id": result.template_id,
            "empty_reason": result.empty_reason,
            "template_meta": dict(result.meta),
            "judgement_score": judgement.score,
            "judgement_status": judgement.status,
            "used_llm_judgement": judgement.used_llm,
        },
    )
