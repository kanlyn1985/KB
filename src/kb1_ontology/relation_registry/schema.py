"""Schema for relation definitions and relation instances.

Two tables:

* ``relation_def`` — a relation *type* with name, category, scope.
* ``relation`` — a concrete edge between two entities (or two
  classes — we use the same table for both, with ``src_kind``
  and ``dst_kind`` saying "entity" or "class").

Categories and scopes are encoded as TEXT with CHECK constraints
so that data integrity is preserved at the SQL level.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

# ---- Constants -----------------------------------------------------

CATEGORY_STRUCTURAL  = "structural"
CATEGORY_ATTRIBUTIVE = "attributive"
CATEGORY_REFERENTIAL = "referential"
CATEGORY_TEMPORAL    = "temporal"
VALID_CATEGORIES = frozenset({
    CATEGORY_STRUCTURAL,
    CATEGORY_ATTRIBUTIVE,
    CATEGORY_REFERENTIAL,
    CATEGORY_TEMPORAL,
})

# Scope: a relation can be "core" (global) or "domain:<name>".
SCOPE_CORE = "core"
SCOPE_DOMAIN_PREFIX = "domain:"


def normalize_scope(scope: str) -> str:
    """Validate / normalize a scope string.

    A scope is either ``"core"`` or ``"domain:<name>"``. Other
    forms are rejected.
    """
    if scope == SCOPE_CORE:
        return SCOPE_CORE
    if scope.startswith(SCOPE_DOMAIN_PREFIX):
        rest = scope[len(SCOPE_DOMAIN_PREFIX):]
        if not rest or not rest.strip():
            raise ValueError(f"scope {scope!r} has empty domain name")
        return scope
    raise ValueError(
        f"scope must be {SCOPE_CORE!r} or '{SCOPE_DOMAIN_PREFIX}<name>', "
        f"got {scope!r}"
    )


# ---- Dataclasses ---------------------------------------------------

@dataclass(frozen=True)
class RelationDef:
    """A relation type."""
    relation_name: str
    category: str
    scope: str
    inverse_name: str | None
    description: str | None
    created_at: str


@dataclass(frozen=True)
class RelationInstance:
    """A concrete edge in the ontology graph."""
    relation_id: int
    relation_name: str
    src_kind: str
    src_id: str
    dst_kind: str
    dst_id: str
    domain: str | None
    confidence: float
    source_path: str | None
    created_at: str


# ---- Schema DDL ---------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS relation_def (
    relation_name  TEXT PRIMARY KEY,
    category       TEXT NOT NULL CHECK (category IN
                       ('structural', 'attributive',
                        'referential', 'temporal')),
    scope          TEXT NOT NULL,
    inverse_name   TEXT,
    description    TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_relation_def_category
    ON relation_def(category);
CREATE INDEX IF NOT EXISTS idx_relation_def_scope
    ON relation_def(scope);

CREATE TABLE IF NOT EXISTS relation (
    relation_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    relation_name TEXT NOT NULL REFERENCES relation_def(relation_name)
                      ON UPDATE CASCADE ON DELETE RESTRICT,
    src_kind      TEXT NOT NULL CHECK (src_kind IN ('entity', 'class')),
    src_id        TEXT NOT NULL,
    dst_kind      TEXT NOT NULL CHECK (dst_kind IN ('entity', 'class')),
    dst_id        TEXT NOT NULL,
    domain        TEXT,
    confidence    REAL NOT NULL DEFAULT 1.0,
    source_path   TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE (relation_name, src_kind, src_id, dst_kind, dst_id, domain)
);
CREATE INDEX IF NOT EXISTS idx_relation_src
    ON relation(src_kind, src_id);
CREATE INDEX IF NOT EXISTS idx_relation_dst
    ON relation(dst_kind, dst_id);
CREATE INDEX IF NOT EXISTS idx_relation_name
    ON relation(relation_name);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the relation tables if missing. Idempotent."""
    conn.executescript(_SCHEMA_SQL)
    conn.commit()


def _row_to_relation_def(row: sqlite3.Row) -> RelationDef:
    return RelationDef(
        relation_name=row["relation_name"],
        category=row["category"],
        scope=row["scope"],
        inverse_name=row["inverse_name"],
        description=row["description"],
        created_at=row["created_at"],
    )


def _row_to_relation_instance(row: sqlite3.Row) -> RelationInstance:
    return RelationInstance(
        relation_id=row["relation_id"],
        relation_name=row["relation_name"],
        src_kind=row["src_kind"],
        src_id=row["src_id"],
        dst_kind=row["dst_kind"],
        dst_id=row["dst_id"],
        domain=row["domain"],
        confidence=float(row["confidence"]),
        source_path=row["source_path"],
        created_at=row["created_at"],
    )
