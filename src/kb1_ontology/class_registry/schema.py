"""Schema definition for the class registry.

One table, ``class_def``, holds the entire class hierarchy. Instances
themselves are not stored here — they live in the entity table of
the entity manager module (Phase 2).

The 3-layer hierarchy is enforced by the ``layer`` column:

* ``LAYER_META``  — abstract universals (Thing, InformationEntity, ...)
* ``LAYER_DOMAIN`` — engineering-role subtrees (OBC, Software, ...)
* Instance-level entities are not stored in this table at all; the
  ``class_id`` they reference is always a Meta or Domain class.

The ``parent_class_id`` column forms a tree, not a DAG. Cycles are
rejected at write time.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

# Layer constants
LAYER_META = "meta"
LAYER_DOMAIN = "domain"
VALID_LAYERS = frozenset({LAYER_META, LAYER_DOMAIN})


@dataclass(frozen=True)
class ClassDef:
    """A registered ontology class.

    ``class_id`` is the canonical primary key (e.g., ``CLS-META-THING``).
    It is constructed by the caller, not auto-generated, so that
    seed data can be loaded deterministically.
    """
    class_id: str
    class_name: str
    parent_class_id: str | None
    layer: str
    domain: str | None
    description: str | None
    is_core: bool
    created_at: str


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS class_def (
    class_id        TEXT PRIMARY KEY,
    class_name      TEXT NOT NULL,
    parent_class_id TEXT REFERENCES class_def(class_id)
                       ON DELETE RESTRICT
                       ON UPDATE CASCADE,
    layer           TEXT NOT NULL CHECK (layer IN ('meta', 'domain')),
    domain          TEXT,
    description     TEXT,
    is_core         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    UNIQUE (class_name, layer, domain)
);
CREATE INDEX IF NOT EXISTS idx_class_def_parent ON class_def(parent_class_id);
CREATE INDEX IF NOT EXISTS idx_class_def_domain ON class_def(domain) WHERE domain IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_class_def_layer  ON class_def(layer);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the class_def table and its indexes if missing.

    Idempotent — safe to call repeatedly.
    """
    conn.executescript(_SCHEMA_SQL)
    conn.commit()


def _row_to_class(row: sqlite3.Row) -> ClassDef:
    return ClassDef(
        class_id=row["class_id"],
        class_name=row["class_name"],
        parent_class_id=row["parent_class_id"],
        layer=row["layer"],
        domain=row["domain"],
        description=row["description"],
        is_core=bool(row["is_core"]),
        created_at=row["created_at"],
    )


def _class_to_dict(c: ClassDef) -> dict[str, Any]:
    return {
        "class_id": c.class_id,
        "class_name": c.class_name,
        "parent_class_id": c.parent_class_id,
        "layer": c.layer,
        "domain": c.domain,
        "description": c.description,
        "is_core": 1 if c.is_core else 0,
        "created_at": c.created_at,
    }
