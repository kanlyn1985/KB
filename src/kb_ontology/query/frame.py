"""QueryFrame and QueryResult — contracts for template-based query execution.

QueryFrame is produced by understanding (rule or LLM). QueryResult is produced
by the deterministic template engine. Neither generates SQL via LLM (ADR-0004).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


# Initial intent set from docs/ARCHITECTURE.md §5.
KNOWN_INTENTS: frozenset[str] = frozenset(
    {
        "parameter_lookup",
        "definition",
        "relation_query",
        "hierarchy_traversal",
        "cross_entity",
        "attribute_search",
        "unknown",
    }
)


@dataclass(frozen=True)
class TargetEntityRef:
    """A resolved (or candidate) entity reference inside a QueryFrame."""

    entity_id: str = ""
    class_name: str = ""
    canonical_name: str = ""
    matched_text: str = ""
    confidence: float = 0.0
    role: str = "primary"  # primary | secondary | source | target

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_resolved(self) -> bool:
        return bool(self.entity_id)


@dataclass(frozen=True)
class QueryAmbiguity:
    """Ambiguity detected before or during template execution."""

    term: str
    candidates: list[str] = field(default_factory=list)
    reason: str = ""
    clarification: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QueryFrame:
    """Canonical query understanding output for ontology template execution.

    LLM (or rules) fill this frame; the template engine consumes it and must
    not invent free-form SQL.
    """

    original_query: str
    intent: str
    intent_confidence: float = 0.0
    domain: str | None = None
    normalized_query: str = ""
    target_entities: list[TargetEntityRef] = field(default_factory=list)
    target_attributes: list[str] = field(default_factory=list)
    relation_type: str | None = None
    attribute_value_query: str | None = None
    hierarchy_direction: str = "down"  # down | up
    max_depth: int = 5
    slots: dict[str, Any] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    ambiguity: list[QueryAmbiguity] = field(default_factory=list)
    used_llm: bool = False
    quality_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["target_entities"] = [t.to_dict() for t in self.target_entities]
        payload["ambiguity"] = [a.to_dict() for a in self.ambiguity]
        return payload

    def primary_entity(self) -> TargetEntityRef | None:
        for t in self.target_entities:
            if t.role in ("primary", "source") and t.is_resolved:
                return t
        for t in self.target_entities:
            if t.is_resolved:
                return t
        return self.target_entities[0] if self.target_entities else None

    def entity_by_role(self, role: str) -> TargetEntityRef | None:
        for t in self.target_entities:
            if t.role == role:
                return t
        return None


@dataclass(frozen=True)
class HitEntity:
    """An entity returned by a template, with optional attributes/relations."""

    entity: dict[str, Any]
    attributes: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    children: list[dict[str, Any]] = field(default_factory=list)
    matched_by: str = ""  # how this hit was selected

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QueryResult:
    """Deterministic output of the template engine (pre-judgement)."""

    intent: str
    template_id: str
    frame: QueryFrame
    hits: list[HitEntity] = field(default_factory=list)
    related: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    empty_reason: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "template_id": self.template_id,
            "frame": self.frame.to_dict(),
            "hits": [h.to_dict() for h in self.hits],
            "related": list(self.related),
            "evidence": list(self.evidence),
            "warnings": list(self.warnings),
            "empty_reason": self.empty_reason,
            "meta": dict(self.meta),
            "hit_count": len(self.hits),
        }

    @property
    def is_empty(self) -> bool:
        return len(self.hits) == 0
