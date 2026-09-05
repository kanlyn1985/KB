from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvidenceRef:
    """Reference back to source evidence."""

    evidence_id: str
    document_id: str | None = None
    page_no: int | None = None
    support_type: str = "supports"
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ObjectProjection:
    """Ontology-lite object projected from evidence/facts/entities."""

    object_id: str
    domain: str
    object_type: str
    canonical_name: str
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    confidence: float = 0.0
    status: str = "candidate"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_refs"] = [item.to_dict() for item in self.evidence_refs]
        return payload


@dataclass(frozen=True)
class ObjectRelation:
    """Ontology-lite relation projected between objects."""

    relation_id: str
    domain: str
    relation_type: str
    source_object_id: str
    target_object_id: str
    properties: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    confidence: float = 0.0
    status: str = "candidate"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_refs"] = [item.to_dict() for item in self.evidence_refs]
        return payload
