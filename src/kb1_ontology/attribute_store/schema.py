"""Schema for the attribute store.

One table, ``attribute``, with the (subject, attribute_name, value)
triple form. ``subject_kind`` is "entity" or "class" so a single
table can carry attributes on either.

The four value types are encoded in **separate columns** rather
than a single JSON blob. This makes range queries like
"give me all attributes where value_num > 100" trivial to express
in SQL and to index.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

# ---- Value-type constants ------------------------------------------

VALUE_TYPE_STRING   = "string"
VALUE_TYPE_NUMBER   = "number"
VALUE_TYPE_RANGE    = "range"
VALUE_TYPE_REFERENCE = "reference"
VALID_VALUE_TYPES = frozenset({
    VALUE_TYPE_STRING, VALUE_TYPE_NUMBER,
    VALUE_TYPE_RANGE, VALUE_TYPE_REFERENCE,
})


# ---- Dataclasses ---------------------------------------------------

@dataclass(frozen=True)
class Attribute:
    """A single (subject, attr, value) triple.

    The unused value columns are None depending on value_type:
      - string  -> value_text holds the string
      - number  -> value_num holds the number (value_text is a
                   stringified representation for debugging)
      - range   -> value_num is the nominal value, value_min
                   and value_max are the bounds, value_unit is
                   the unit, value_tol is the tolerance
      - reference -> value_ref_kind + value_ref_id point to the
                     referenced entity or class
    """
    attribute_id: int
    subject_kind: str
    subject_id: str
    attribute_name: str
    value_type: str
    value_text: str | None
    value_num: float | None
    value_min: float | None
    value_max: float | None
    value_unit: str | None
    value_tol: float | None
    value_ref_kind: str | None
    value_ref_id: str | None
    source_path: str | None
    created_at: str


@dataclass(frozen=True)
class Term:
    """A term in the dictionary (concept, component, protocol)."""
    term_id: str
    canonical_name: str
    category: str
    definition_zh: str | None
    definition_en: str | None
    source_standard: str | None
    source_section: str | None
    confidence: float
    extracted_at: str | None
    verified: int
    created_at: str


@dataclass(frozen=True)
class Parameter:
    """A parameter in the parameter dictionary."""
    param_id: str
    canonical_name: str
    value_num: float | None
    value_unit: str | None
    value_min: float | None
    value_max: float | None
    definition_zh: str | None
    definition_en: str | None
    source_standard: str | None
    source_section: str | None
    confidence: float
    extracted_at: str | None
    verified: int
    created_at: str


@dataclass(frozen=True)
class TermAlias:
    """An alias for a term."""
    term_id: str
    alias: str
    alias_type: str | None


@dataclass(frozen=True)
class ParamAlias:
    """An alias for a parameter."""
    param_id: str
    alias: str
    alias_type: str | None


@dataclass(frozen=True)
class TermRelation:
    """A relation between two terms."""
    term1_id: str
    relation: str
    term2_id: str
    confidence: float


# ---- Schema DDL ---------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS attribute (
    attribute_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_kind    TEXT NOT NULL CHECK (subject_kind IN ('entity', 'class')),
    subject_id      TEXT NOT NULL,
    attribute_name  TEXT NOT NULL,
    value_type      TEXT NOT NULL CHECK (value_type IN
                          ('string', 'number', 'range', 'reference')),
    value_text      TEXT,
    value_num       REAL,
    value_min       REAL,
    value_max       REAL,
    value_unit      TEXT,
    value_tol       REAL,
    value_ref_kind  TEXT CHECK (value_ref_kind IN ('entity', 'class')
                                   OR value_ref_kind IS NULL),
    value_ref_id    TEXT,
    source_path     TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE (subject_kind, subject_id, attribute_name)
);
CREATE INDEX IF NOT EXISTS idx_attribute_subject
    ON attribute(subject_kind, subject_id);
CREATE INDEX IF NOT EXISTS idx_attribute_name
    ON attribute(attribute_name);
CREATE INDEX IF NOT EXISTS idx_attribute_value_num
    ON attribute(value_num);

-- Term Dictionary (Phase 7)
CREATE TABLE IF NOT EXISTS term (
    term_id         TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    category        TEXT NOT NULL CHECK (category IN ('concept', 'component', 'protocol', 'process')),
    definition_zh   TEXT,
    definition_en   TEXT,
    source_standard TEXT,
    source_section  TEXT,
    confidence      REAL DEFAULT 1.0,
    extracted_at    TEXT,
    verified        INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_term_name ON term(canonical_name);
CREATE INDEX IF NOT EXISTS idx_term_category ON term(category);

CREATE TABLE IF NOT EXISTS term_alias (
    term_id     TEXT REFERENCES term(term_id) ON DELETE CASCADE,
    alias       TEXT NOT NULL,
    alias_type  TEXT CHECK (alias_type IN ('abbreviation', 'full_name', 'chinese', 'english', 'other')),
    PRIMARY KEY (term_id, alias)
);
CREATE INDEX IF NOT EXISTS idx_term_alias ON term_alias(alias);

CREATE TABLE IF NOT EXISTS term_relation (
    term1_id    TEXT REFERENCES term(term_id) ON DELETE CASCADE,
    relation    TEXT NOT NULL CHECK (relation IN ('related_to', 'part_of', 'synonym', 'antonym', 'defined_in', 'references')),
    term2_id    TEXT REFERENCES term(term_id) ON DELETE CASCADE,
    confidence  REAL DEFAULT 1.0,
    PRIMARY KEY (term1_id, relation, term2_id)
);

-- Parameter Dictionary (Phase 7)
CREATE TABLE IF NOT EXISTS param (
    param_id        TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    value_num       REAL,
    value_unit      TEXT,
    value_min       REAL,
    value_max       REAL,
    definition_zh   TEXT,
    definition_en   TEXT,
    source_standard TEXT,
    source_section  TEXT,
    confidence      REAL DEFAULT 1.0,
    extracted_at    TEXT,
    verified        INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_param_name ON param(canonical_name);

CREATE TABLE IF NOT EXISTS param_alias (
    param_id    TEXT REFERENCES param(param_id) ON DELETE CASCADE,
    alias       TEXT NOT NULL,
    alias_type  TEXT CHECK (alias_type IN ('abbreviation', 'full_name', 'chinese', 'english', 'other')),
    PRIMARY KEY (param_id, alias)
);
CREATE INDEX IF NOT EXISTS idx_param_alias ON param_alias(alias);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQL)
    conn.commit()


def _row_to_attribute(row: sqlite3.Row) -> Attribute:
    return Attribute(
        attribute_id=row["attribute_id"],
        subject_kind=row["subject_kind"],
        subject_id=row["subject_id"],
        attribute_name=row["attribute_name"],
        value_type=row["value_type"],
        value_text=row["value_text"],
        value_num=row["value_num"],
        value_min=row["value_min"],
        value_max=row["value_max"],
        value_unit=row["value_unit"],
        value_tol=row["value_tol"],
        value_ref_kind=row["value_ref_kind"],
        value_ref_id=row["value_ref_id"],
        source_path=row["source_path"],
        created_at=row["created_at"],
    )
