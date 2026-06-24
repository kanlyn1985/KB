"""Core relation seeds.

The hand-curated set of relation *types* that the ontology ships
with. Per the design in docs/ontology/CONTEXT.md:
- **Structural**  (skeleton): is-a, part-of
- **Attributive** (properties): has-attribute
- **Referential** (cross-entity): references, cites
- **Temporal**    (event order): precedes, follows

Core relations are global (scope = "core"). Domain-specific
relations are added in their own Domain's seed function.
"""
from __future__ import annotations

import sqlite3

from .crud import RelationRegistryError, create_relation_def, get_relation_def
from .schema import (
    CATEGORY_STRUCTURAL,
    CATEGORY_ATTRIBUTIVE,
    CATEGORY_REFERENTIAL,
    CATEGORY_TEMPORAL,
    SCOPE_CORE,
    ensure_schema,
)


# (relation_name, category, inverse_name, description)
CORE_RELATIONS: tuple[tuple[str, str, str | None, str], ...] = (
    (
        "is-a",
        CATEGORY_STRUCTURAL,
        "instance-of",
        "Class inclusion or instantiation. Most often used between "
        "classes (subclass).",
    ),
    (
        "part-of",
        CATEGORY_STRUCTURAL,
        "has-part",
        "Mereological part relation: the source is a part of the "
        "destination.",
    ),
    (
        "has-attribute",
        CATEGORY_ATTRIBUTIVE,
        "attribute-of",
        "Attaches an attribute to an entity (Phase 4 will use this).",
    ),
    (
        "references",
        CATEGORY_REFERENTIAL,
        "referenced-by",
        "The source document or standard references the destination. "
        "Cross-entity connection used heavily for cross-document "
        "knowledge linking.",
    ),
    (
        "cites",
        CATEGORY_REFERENTIAL,
        "cited-by",
        "The source formally cites the destination (e.g., in "
        "normative references sections).",
    ),
    (
        "precedes",
        CATEGORY_TEMPORAL,
        "follows",
        "The source temporally precedes the destination.",
    ),
    (
        "follows",
        CATEGORY_TEMPORAL,
        "precedes",
        "The source temporally follows the destination.",
    ),
)


def seed_core_relations(conn: sqlite3.Connection) -> int:
    """Insert the core relation definitions. Idempotent.

    Returns the number of relations newly created.
    """
    ensure_schema(conn)
    created = 0
    for name, category, inverse, description in CORE_RELATIONS:
        if get_relation_def(conn, name) is not None:
            continue
        try:
            create_relation_def(
                conn,
                relation_name=name,
                category=category,
                scope=SCOPE_CORE,
                inverse_name=inverse,
                description=description,
            )
        except RelationRegistryError as e:
            if "UNIQUE" in str(e):
                # Race: another process already created it
                continue
            raise
        created += 1
    return created
