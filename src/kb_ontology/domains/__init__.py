"""Domain pack schema and loader."""

from kb_ontology.domains.schema import (
    AttributeSpec,
    CORE_RELATION_TYPES,
    ClassSpec,
    DomainPack,
    DomainPackError,
    RelationRole,
    RelationTypeSpec,
    VALUE_TYPES,
)
from kb_ontology.domains.loader import load_domain_pack

__all__ = [
    "AttributeSpec",
    "CORE_RELATION_TYPES",
    "ClassSpec",
    "DomainPack",
    "DomainPackError",
    "RelationRole",
    "RelationTypeSpec",
    "VALUE_TYPES",
    "load_domain_pack",
]
