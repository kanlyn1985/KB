"""Domain pack schema definitions.

A Domain Pack is the sole source of Ontology schema for a domain. It defines:
- Class templates (attribute templates, relation roles, identity rules)
- Domain-specific relation types (Core relations part_of/references are built-in)
- Terminology (canonical entity IDs → aliases, for query understanding)

Core code never hardcodes domain concepts — see ADR-0002.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Attribute value types (aligned with ontology storage value_type column) ──

VALUE_TYPES = frozenset({"number", "string", "boolean", "entity_ref"})


class DomainPackError(ValueError):
    """Raised when a domain pack is missing required metadata or has invalid shape."""


# ── Core built-in relation types (cross-domain, see ADR-0002) ──


@dataclass(frozen=True)
class RelationTypeSpec:
    """A relation type declaration.

    Core skeleton (part_of, references) have ``is_core=True`` and are
    injected by the loader, not declared in domain pack JSON.
    """

    name: str
    description: str = ""
    inverse_name: str | None = None
    is_core: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "inverse_name": self.inverse_name,
            "is_core": self.is_core,
        }


CORE_RELATION_TYPES: dict[str, RelationTypeSpec] = {
    "part_of": RelationTypeSpec(
        name="part_of",
        description="部分-整体关系，构建层级树",
        inverse_name="has_part",
        is_core=True,
    ),
    "references": RelationTypeSpec(
        name="references",
        description="引用关系，跨实体连接",
        inverse_name="referenced_by",
        is_core=True,
    ),
}


# ── Class definition components ──


@dataclass(frozen=True)
class AttributeSpec:
    """A single attribute in a Class template.

    Attributes are stored as triples (entity_id, name, value) in the ontology
    storage. The ``value_type`` drives serialization and query behavior.
    """

    name: str
    value_type: str = "string"
    required: bool = False
    description: str = ""
    enum_values: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.value_type not in VALUE_TYPES:
            raise DomainPackError(
                f"attribute '{self.name}' has invalid value_type '{self.value_type}'; "
                f"must be one of {sorted(VALUE_TYPES)}"
            )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "value_type": self.value_type,
            "required": self.required,
            "description": self.description,
        }
        if self.enum_values:
            payload["enum_values"] = list(self.enum_values)
        return payload


@dataclass(frozen=True)
class RelationRole:
    """Declares that entities of this Class can participate in a relation.

    A Class lists which relation types its entities can be the *source* of,
    and which target Classes are valid. This drives both extraction (LLM knows
    what relations to look for) and query validation (template engine can
    reject invalid traversals).
    """

    relation_type: str
    target_classes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "relation_type": self.relation_type,
            "target_classes": list(self.target_classes),
        }


@dataclass(frozen=True)
class ClassSpec:
    """A Class definition — the type template for entities.

    Four sections (see ARCHITECTURE.md §4.2):
    - attribute_template: what attributes entities of this class have
    - relation_roles: what relations this class can source
    - identity: which attributes determine entity uniqueness
    - display: how entities of this class render in ContextPack
    """

    name: str
    description: str = ""
    attribute_template: dict[str, AttributeSpec] = field(default_factory=dict)
    relation_roles: list[RelationRole] = field(default_factory=list)
    identity_attributes: list[str] = field(default_factory=list)
    identity_rule: str = ""
    display_primary: str = "name"
    display_secondary: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "attribute_template": {
                name: spec.to_dict() for name, spec in self.attribute_template.items()
            },
            "relation_roles": [role.to_dict() for role in self.relation_roles],
            "identity_attributes": list(self.identity_attributes),
            "identity_rule": self.identity_rule,
            "display_primary": self.display_primary,
            "display_secondary": list(self.display_secondary),
        }


# ── Domain Pack aggregate ──


@dataclass(frozen=True)
class DomainPack:
    """Loaded domain pack — the Ontology schema contract for one domain.

    Core code consumes this structure but does not know any concrete domain
    concepts. All Class/Relation/Attribute knowledge flows from here.
    """

    domain_id: str
    name: str = ""
    version: str = "0.1.0"
    description: str = ""
    classes: dict[str, ClassSpec] = field(default_factory=dict)
    relation_types: dict[str, RelationTypeSpec] = field(default_factory=dict)
    terminology: dict[str, list[str]] = field(default_factory=dict)

    @property
    def all_relation_types(self) -> dict[str, RelationTypeSpec]:
        """Core skeleton + domain-specific relation types combined."""
        merged: dict[str, RelationTypeSpec] = dict(CORE_RELATION_TYPES)
        merged.update(self.relation_types)
        return merged

    def get_class(self, class_name: str) -> ClassSpec | None:
        return self.classes.get(class_name)

    def get_relation_type(self, relation_name: str) -> RelationTypeSpec | None:
        return self.all_relation_types.get(relation_name)

    def to_dict(self) -> dict[str, object]:
        return {
            "domain_id": self.domain_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "classes": {name: spec.to_dict() for name, spec in self.classes.items()},
            "relation_types": {
                name: spec.to_dict() for name, spec in self.relation_types.items()
            },
            "terminology": dict(self.terminology),
        }
