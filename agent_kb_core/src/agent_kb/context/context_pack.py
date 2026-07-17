from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agent_kb.projection.models import ObjectProjection, ObjectRelation
from agent_kb.query.query_frame import QueryFrame
from agent_kb.retrieval.cards import RetrievalCard


@dataclass(frozen=True)
class ContextEvidence:
    evidence_id: str
    document_id: str | None
    page_no: int | None
    snippet: str
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContextFact:
    fact_id: str
    fact_type: str
    subject: str | None
    predicate: str
    object_value: Any
    qualifiers: dict[str, Any] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnswerContract:
    contract_id: str
    intent: str
    required_sections: list[str] = field(default_factory=list)
    optional_sections: list[str] = field(default_factory=list)
    output_policy: str = "evidence_grounded"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentContextPack:
    """Structured context supplied to an agent before final answer generation."""

    query_frame: QueryFrame
    answer_contract: AnswerContract | None = None
    target_objects: list[ObjectProjection] = field(default_factory=list)
    object_relations: list[ObjectRelation] = field(default_factory=list)
    retrieval_cards: list[RetrievalCard] = field(default_factory=list)
    facts: list[ContextFact] = field(default_factory=list)
    evidence: list[ContextEvidence] = field(default_factory=list)
    hidden_context: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    knowledge_gaps: list[str] = field(default_factory=list)
    recommended_answer_strategy: str = "answer_with_evidence"

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_frame": self.query_frame.to_dict(),
            "answer_contract": self.answer_contract.to_dict() if self.answer_contract else None,
            "target_objects": [item.to_dict() for item in self.target_objects],
            "object_relations": [item.to_dict() for item in self.object_relations],
            "retrieval_cards": [item.to_dict() for item in self.retrieval_cards],
            "facts": [item.to_dict() for item in self.facts],
            "evidence": [item.to_dict() for item in self.evidence],
            "hidden_context": list(self.hidden_context),
            "warnings": list(self.warnings),
            "knowledge_gaps": list(self.knowledge_gaps),
            "recommended_answer_strategy": self.recommended_answer_strategy,
        }
