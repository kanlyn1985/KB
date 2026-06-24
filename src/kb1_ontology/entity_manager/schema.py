"""Schema for the entity table and the document-roles table.

Two tables live in this module:

* ``entity`` — concrete instances of registered classes. Every row
  has a class_id (FK to class_def) and a domain. The
  (canonical_name, class_id, domain) tuple is unique.

* ``document_role`` — a many-to-many between documents (by source
  path) and job roles. A single document can be relevant to
  multiple engineering roles. This is the place where the
  "what is this doc for?" question is answered.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

# Layer constant for completeness. The entity table is itself the
# "instance" layer, so any new class registry layer would be
# "instance" by definition.
LAYER_INSTANCE = "instance"


# ---- DocumentRole (job-role tags) ---------------------------------

# Predefined job roles in the KB1 knowledge base. New roles can
# be added; these are the well-known ones.
JOB_ROLES: tuple[str, ...] = (
    "systems_engineer",         # systems integration engineer
    "software_engineer",       # embedded software
    "electronics_engineer",    # circuit / power electronics
    "test_engineer",           # test & validation
    "mechanical_engineer",     # mechanical / structural
    "quality_engineer",        # quality / compliance
)


@dataclass(frozen=True)
class DocumentRole:
    """A document associated with a job role.

    ``source_path`` is the document's filesystem path. The
    document_role table is intentionally kept simple: no
    confidence, no scope, no version. Future work can extend
    this if roles need weighting.
    """
    source_path: str
    job_role: str
    created_at: str


# ---- Entity -------------------------------------------------------

@dataclass(frozen=True)
class Entity:
    """A concrete entity instance."""
    entity_id: str
    canonical_name: str
    class_id: str
    domain: str | None
    description: str | None
    aliases_json: str
    source_path: str | None
    created_at: str


# ---- Schema DDL ---------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entity (
    entity_id        TEXT PRIMARY KEY,
    canonical_name   TEXT NOT NULL,
    class_id         TEXT NOT NULL REFERENCES class_def(class_id)
                         ON DELETE RESTRICT
                         ON UPDATE CASCADE,
    domain           TEXT,
    description      TEXT,
    aliases_json     TEXT NOT NULL DEFAULT '[]',
    source_path      TEXT,
    wiki_chunk_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at       TEXT NOT NULL,
    UNIQUE (canonical_name, class_id, domain)
);
CREATE INDEX IF NOT EXISTS idx_entity_class_id  ON entity(class_id);
CREATE INDEX IF NOT EXISTS idx_entity_domain    ON entity(domain)
    WHERE domain IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entity_canonical ON entity(canonical_name);

CREATE TABLE IF NOT EXISTS document_role (
    source_path   TEXT NOT NULL,
    job_role      TEXT NOT NULL CHECK (job_role IN (
        'systems_engineer', 'software_engineer',
        'electronics_engineer', 'test_engineer',
        'mechanical_engineer', 'quality_engineer'
    )),
    created_at    TEXT NOT NULL,
    PRIMARY KEY (source_path, job_role)
);
CREATE INDEX IF NOT EXISTS idx_document_role_role
    ON document_role(job_role);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the entity and document_role tables if missing.

    Idempotent.
    """
    conn.executescript(_SCHEMA_SQL)
    conn.commit()


def _row_to_entity(row: sqlite3.Row) -> Entity:
    return Entity(
        entity_id=row["entity_id"],
        canonical_name=row["canonical_name"],
        class_id=row["class_id"],
        domain=row["domain"],
        description=row["description"],
        aliases_json=row["aliases_json"],
        source_path=row["source_path"],
        created_at=row["created_at"],
    )


def _row_to_document_role(row: sqlite3.Row) -> DocumentRole:
    return DocumentRole(
        source_path=row["source_path"],
        job_role=row["job_role"],
        created_at=row["created_at"],
    )


def _entity_to_dict(e: Entity) -> dict[str, Any]:
    return {
        "entity_id": e.entity_id,
        "canonical_name": e.canonical_name,
        "class_id": e.class_id,
        "domain": e.domain,
        "description": e.description,
        "aliases_json": e.aliases_json,
        "source_path": e.source_path,
        "created_at": e.created_at,
    }


def _document_role_to_dict(r: DocumentRole) -> dict[str, Any]:
    return {
        "source_path": r.source_path,
        "job_role": r.job_role,
        "created_at": r.created_at,
    }
