from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TargetObject:
    """Domain-linked target object from a user query."""

    object_id: str
    object_type: str
    canonical_name: str
    matched_text: str
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QueryAmbiguity:
    """Ambiguity found before retrieval."""

    term: str
    possible_objects: list[str]
    reason: str
    clarification: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QueryFrame:
    """Canonical query understanding output.

    QueryFrame is the contract between semantic understanding and retrieval. It
    replaces ad-hoc query strings with a stable machine-consumable frame.
    """

    original_query: str
    domain: str | None
    intent: str
    intent_confidence: float
    normalized_query: str
    target_topic: str
    target_objects: list[TargetObject] = field(default_factory=list)
    slots: dict[str, Any] = field(default_factory=dict)
    missing_slots: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    must_terms: list[str] = field(default_factory=list)
    should_terms: list[str] = field(default_factory=list)
    negative_terms: list[str] = field(default_factory=list)
    preferred_fact_types: list[str] = field(default_factory=list)
    required_evidence_shapes: list[str] = field(default_factory=list)
    retrieval_channels: list[str] = field(default_factory=list)
    ambiguity: list[QueryAmbiguity] = field(default_factory=list)
    answer_contract: str | None = None
    answer_strategy: str = "answer_with_evidence"
    used_llm: bool = False
    quality_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["target_objects"] = [item.to_dict() for item in self.target_objects]
        payload["ambiguity"] = [item.to_dict() for item in self.ambiguity]
        return payload
