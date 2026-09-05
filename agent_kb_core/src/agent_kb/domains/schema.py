from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ObjectTypeSpec:
    """Domain-declared object type.

    This is intentionally generic. Domain packs define concrete types such as
    Parameter, StandardClause, LawArticle, PolicyRule, TestMethod, etc.
    """

    name: str
    description: str = ""
    properties: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RelationTypeSpec:
    """Domain-declared relation type."""

    name: str
    source_types: list[str] = field(default_factory=list)
    target_types: list[str] = field(default_factory=list)
    description: str = ""


@dataclass(frozen=True)
class AnswerContractSpec:
    """Structured answer/context shape for a query intent."""

    name: str
    intent: str
    required_sections: list[str] = field(default_factory=list)
    optional_sections: list[str] = field(default_factory=list)
    preferred_object_types: list[str] = field(default_factory=list)
    preferred_fact_types: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HiddenContextRule:
    """Rule for injecting expert background context into an Agent Context Pack."""

    rule_id: str
    trigger: dict[str, Any]
    inject: list[str]


@dataclass(frozen=True)
class DomainPack:
    """Loaded domain pack.

    A domain pack is the only place where domain-specific ontology-like
    semantics should live. Core code consumes this structure but does not know
    OBC/DCDC, legal, medical, finance, or other concrete domain concepts.
    """

    domain_id: str
    name: str
    version: str = "0.1.0"
    description: str = ""
    object_types: dict[str, ObjectTypeSpec] = field(default_factory=dict)
    relation_types: dict[str, RelationTypeSpec] = field(default_factory=dict)
    terminology: dict[str, list[str]] = field(default_factory=dict)
    answer_contracts: dict[str, AnswerContractSpec] = field(default_factory=dict)
    hidden_context_rules: list[HiddenContextRule] = field(default_factory=list)
