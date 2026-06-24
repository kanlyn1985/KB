"""Relation registry for the KB1 ontology system.

A relation is a typed connection between two entities (or, in the
case of class-level relations, two classes). Relations are the
"edges" of the ontology graph.

The relation registry has two layers:

1. **relation_def** — definitions of relation *types* (e.g., the
   `references` relation exists, with category "referential").
2. **relation** — concrete instances of relations between
   specific entities (e.g., the entity for ISO 14229-7 has a
   `references` edge to the entity for ISO 14229-1).

Four categories of relations are supported (per the design in
docs/ontology/CONTEXT.md):

* **structural**  — ``is-a``, ``part-of``: build the skeleton
* **attributive** — ``has-attribute``: attach properties
* **referential** — ``references``, ``cites``: cross-entity links
* **temporal**    — ``precedes``, ``follows``: event ordering

Core relations are global. Domain-specific relations live in
their own scope ("domain:<name>").
"""
from .schema import (
    CATEGORY_STRUCTURAL,
    CATEGORY_ATTRIBUTIVE,
    CATEGORY_REFERENTIAL,
    CATEGORY_TEMPORAL,
    SCOPE_CORE,
    SCOPE_DOMAIN_PREFIX,
    RelationDef,
    RelationInstance,
    ensure_schema,
)
from .crud import (
    RelationRegistryError,
    create_relation_def,
    get_relation_def,
    list_relation_defs,
    create_relation,
    get_relation,
    list_relations,
    delete_relation,
    inverse_relation_name,
)
from .traversal import (
    traverse_relations,
    relations_of,
)
from .seeds import (
    seed_core_relations,
    CORE_RELATIONS,
)

__all__ = [
    "CATEGORY_STRUCTURAL",
    "CATEGORY_ATTRIBUTIVE",
    "CATEGORY_REFERENTIAL",
    "CATEGORY_TEMPORAL",
    "SCOPE_CORE",
    "SCOPE_DOMAIN_PREFIX",
    "RelationDef",
    "RelationInstance",
    "ensure_schema",
    "RelationRegistryError",
    "create_relation_def",
    "get_relation_def",
    "list_relation_defs",
    "create_relation",
    "get_relation",
    "list_relations",
    "delete_relation",
    "inverse_relation_name",
    "traverse_relations",
    "relations_of",
    "seed_core_relations",
    "CORE_RELATIONS",
]
