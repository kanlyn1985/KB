"""Class registry for the KB1 ontology system.

This module manages the taxonomy of "kinds of things" that can exist
in the knowledge base. It implements a 3-layer hierarchy:

    Meta layer     abstract universals (Thing, InformationEntity, ...)
    Domain layer   engineering-role specific subtrees
                   (OBC, Software, Electronics, Test, ...)
    Instance       concrete things from documents
                   (referenced by the entity table; not stored here)

Design notes are in docs/ontology/CONTEXT.md and ROADMAP.md.
"""
from .schema import LAYER_META, LAYER_DOMAIN, ensure_schema
from .crud import (
    ClassRegistryError,
    create_class,
    get_class,
    list_classes,
    update_class,
    delete_class,
)
from .hierarchy import (
    is_subclass_of,
    get_ancestors,
    get_descendants,
    check_acyclic,
)
from .seeds import seed_core_classes

__all__ = [
    "LAYER_META",
    "LAYER_DOMAIN",
    "ensure_schema",
    "ClassRegistryError",
    "create_class",
    "get_class",
    "list_classes",
    "update_class",
    "delete_class",
    "is_subclass_of",
    "get_ancestors",
    "get_descendants",
    "check_acyclic",
    "seed_core_classes",
]
