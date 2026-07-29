"""Data models for ontology storage.

Four frozen dataclasses mirror the four SQLite tables. Each provides
``to_dict()`` for serialization and ``from_row()`` for SQLite Row construction.

Attribute values are stored as TEXT in SQLite, with ``value_type`` controlling
serialization/deserialization:
  number    → float
  boolean   → bool
  string    → str
  entity_ref → str (entity_id)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from kb_ontology.domains.schema import VALUE_TYPES


# ── Serialization helpers ──


def serialize_value(value: Any, value_type: str) -> str | None:
    """Convert a Python value to its TEXT representation for storage."""
    if value is None:
        return None
    if value_type == "number":
        return str(float(value))
    if value_type == "boolean":
        return "true" if value else "false"
    # string and entity_ref both stored as-is
    return str(value)


def deserialize_value(raw: str | None, value_type: str) -> Any:
    """Convert stored TEXT back to its Python type."""
    if raw is None:
        return None
    if value_type == "number":
        try:
            return float(raw)
        except ValueError:
            return raw  # graceful degradation
    if value_type == "boolean":
        return raw.strip().lower() in ("true", "1", "yes")
    return raw


# ── Dataclasses ──


@dataclass(frozen=True)
class Entity:
    """An ontology entity node — a domain concept."""

    id: str
    class_name: str
    canonical_name: str
    domain: str = "default"
    status: str = "active"
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "class": self.class_name,
            "canonical_name": self.canonical_name,
            "domain": self.domain,
            "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Any) -> Entity:
        return cls(
            id=row["id"],
            class_name=row["class"],
            canonical_name=row["canonical_name"],
            domain=row["domain"],
            status=row["status"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True)
class Attribute:
    """A typed attribute triple: (entity_id, name, value)."""

    id: str
    entity_id: str
    name: str
    value: Any = None
    value_type: str = "string"
    confidence: float = 1.0
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "name": self.name,
            "value": self.value,
            "value_type": self.value_type,
            "confidence": self.confidence,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Any) -> Attribute:
        return cls(
            id=row["id"],
            entity_id=row["entity_id"],
            name=row["name"],
            value=deserialize_value(row["value"], row["value_type"]),
            value_type=row["value_type"],
            confidence=row["confidence"] if row["confidence"] is not None else 1.0,
            created_at=row["created_at"],
        )


@dataclass(frozen=True)
class Relation:
    """A typed edge: (source, relation_type, target)."""

    id: str
    source_id: str
    relation_type: str
    target_id: str
    confidence: float = 1.0
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "relation_type": self.relation_type,
            "target_id": self.target_id,
            "confidence": self.confidence,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Any) -> Relation:
        return cls(
            id=row["id"],
            source_id=row["source_id"],
            relation_type=row["relation_type"],
            target_id=row["target_id"],
            confidence=row["confidence"] if row["confidence"] is not None else 1.0,
            created_at=row["created_at"],
        )


@dataclass(frozen=True)
class Evidence:
    """A traceability link from an ontology element to its source document."""

    id: str
    ref_type: str  # entity | attribute | relation
    ref_id: str
    document_id: str
    text_span: str = ""
    location: str = ""
    confidence: float = 1.0
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ref_type": self.ref_type,
            "ref_id": self.ref_id,
            "document_id": self.document_id,
            "text_span": self.text_span,
            "location": self.location,
            "confidence": self.confidence,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Any) -> Evidence:
        return cls(
            id=row["id"],
            ref_type=row["ref_type"],
            ref_id=row["ref_id"],
            document_id=row["document_id"],
            text_span=row["text_span"] or "",
            location=row["location"] or "",
            confidence=row["confidence"] if row["confidence"] is not None else 1.0,
            created_at=row["created_at"],
        )
