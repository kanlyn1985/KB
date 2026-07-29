"""Judgement models for ontology query results (ADR-0003)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SufficiencyStatus = Literal["sufficient", "partial", "insufficient"]
AnswerStrategy = Literal[
    "answer_with_evidence",
    "answer_with_caveat",
    "clarify_ambiguity",
    "report_knowledge_gap",
    "refuse_insufficient",
]


@dataclass(frozen=True)
class Judgement:
    """Structural (+ optional semantic) assessment of a QueryResult.

    Structural fields are always filled by rules (zero LLM).
    Semantic fields are filled only when rules mark ``needs_semantic`` and an
    LLM client is available; otherwise they stay empty / rule-derived.
    """

    status: SufficiencyStatus
    score: float
    needs_semantic: bool = False
    has_target: bool = False
    hit_count: int = 0
    evidence_count: int = 0
    attribute_count: int = 0
    relation_count: int = 0
    missing_requirements: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    knowledge_gaps: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    recommended_strategy: AnswerStrategy = "answer_with_evidence"
    used_llm: bool = False
    semantic_notes: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
