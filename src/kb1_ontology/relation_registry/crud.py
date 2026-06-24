"""CRUD operations for relation definitions and relation instances."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from .schema import (
    VALID_CATEGORIES,
    RelationDef,
    RelationInstance,
    SCOPE_CORE,
    _row_to_relation_def,
    _row_to_relation_instance,
    normalize_scope,
)


class RelationRegistryError(Exception):
    """Raised when an operation violates a relation-registry invariant."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---- relation_def ------------------------------------------------

def create_relation_def(
    conn: sqlite3.Connection,
    relation_name: str,
    category: str,
    scope: str = SCOPE_CORE,
    inverse_name: str | None = None,
    description: str | None = None,
) -> RelationDef:
    """Register a new relation type.

    Pre-conditions:
      - ``relation_name`` is non-empty
      - ``category`` is one of the four valid categories
      - ``scope`` is "core" or "domain:<name>"
    """
    if not relation_name or not relation_name.strip():
        raise RelationRegistryError("relation_name is required")
    if category not in VALID_CATEGORIES:
        raise RelationRegistryError(
            f"category must be one of {sorted(VALID_CATEGORIES)}, "
            f"got {category!r}"
        )
    scope_n = normalize_scope(scope)

    rd = RelationDef(
        relation_name=relation_name,
        category=category,
        scope=scope_n,
        inverse_name=inverse_name,
        description=description,
        created_at=_utc_now(),
    )
    try:
        conn.execute(
            """
            INSERT INTO relation_def
                (relation_name, category, scope, inverse_name,
                 description, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (rd.relation_name, rd.category, rd.scope, rd.inverse_name,
             rd.description, rd.created_at),
        )
    except sqlite3.IntegrityError as e:
        raise RelationRegistryError(str(e)) from e
    conn.commit()
    return rd


def get_relation_def(
    conn: sqlite3.Connection, relation_name: str
) -> RelationDef | None:
    row = conn.execute(
        "SELECT * FROM relation_def WHERE relation_name = ?",
        (relation_name,),
    ).fetchone()
    return _row_to_relation_def(row) if row else None


def list_relation_defs(
    conn: sqlite3.Connection,
    *,
    category: str | None = None,
    scope: str | None = None,
) -> list[RelationDef]:
    clauses: list[str] = []
    params: list[Any] = []
    if category is not None:
        clauses.append("category = ?")
        params.append(category)
    if scope is not None:
        clauses.append("scope = ?")
        params.append(scope)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM relation_def{where} ORDER BY relation_name", params
    ).fetchall()
    return [_row_to_relation_def(r) for r in rows]


# ---- relation (instance) -----------------------------------------

def create_relation(
    conn: sqlite3.Connection,
    relation_name: str,
    src_kind: str,
    src_id: str,
    dst_kind: str,
    dst_id: str,
    *,
    domain: str | None = None,
    confidence: float = 1.0,
    source_path: str | None = None,
) -> RelationInstance:
    """Create a concrete relation instance.

    Pre-conditions:
      - ``relation_name`` is registered (exists in relation_def)
      - ``src_kind`` and ``dst_kind`` are "entity" or "class"
      - The (src_id, dst_id) pair is not self-referential
        (src_id != dst_id)
      - For class-level relations, the classes exist in
        class_def. For entity-level, the entities exist in entity.
    """
    if src_kind not in {"entity", "class"}:
        raise RelationRegistryError(
            f"src_kind must be 'entity' or 'class', got {src_kind!r}"
        )
    if dst_kind not in {"entity", "class"}:
        raise RelationRegistryError(
            f"dst_kind must be 'entity' or 'class', got {dst_kind!r}"
        )
    if src_kind == dst_kind and src_id == dst_id and (
        domain is None or True
    ):
        raise RelationRegistryError(
            f"self-loop not allowed: {src_kind} {src_id} -> {dst_kind} {dst_id}"
        )
    if not (0.0 <= confidence <= 1.0):
        raise RelationRegistryError(
            f"confidence must be in [0, 1], got {confidence}"
        )

    # Verify relation_name is registered
    rd = get_relation_def(conn, relation_name)
    if rd is None:
        raise RelationRegistryError(
            f"relation_name {relation_name!r} is not registered; "
            f"create it via create_relation_def first"
        )

    # Verify referent exists
    if src_kind == "entity":
        row = conn.execute(
            "SELECT 1 FROM entity WHERE entity_id = ?", (src_id,)
        ).fetchone()
        if row is None:
            raise RelationRegistryError(
                f"src entity {src_id!r} does not exist"
            )
    else:
        row = conn.execute(
            "SELECT 1 FROM class_def WHERE class_id = ?", (src_id,)
        ).fetchone()
        if row is None:
            raise RelationRegistryError(
                f"src class {src_id!r} does not exist"
            )
    if dst_kind == "entity":
        row = conn.execute(
            "SELECT 1 FROM entity WHERE entity_id = ?", (dst_id,)
        ).fetchone()
        if row is None:
            raise RelationRegistryError(
                f"dst entity {dst_id!r} does not exist"
            )
    else:
        row = conn.execute(
            "SELECT 1 FROM class_def WHERE class_id = ?", (dst_id,)
        ).fetchone()
        if row is None:
            raise RelationRegistryError(
                f"dst class {dst_id!r} does not exist"
            )

    try:
        cur = conn.execute(
            """
            INSERT INTO relation
                (relation_name, src_kind, src_id, dst_kind, dst_id,
                 domain, confidence, source_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (relation_name, src_kind, src_id, dst_kind, dst_id,
             domain, confidence, source_path, _utc_now()),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise RelationRegistryError(str(e)) from e
    rid = cur.lastrowid
    if rid is None:
        raise RelationRegistryError("INSERT failed to return a rowid")
    row = conn.execute(
        "SELECT * FROM relation WHERE relation_id = ?", (rid,)
    ).fetchone()
    assert row is not None
    return _row_to_relation_instance(row)


def get_relation(
    conn: sqlite3.Connection, relation_id: int
) -> RelationInstance | None:
    row = conn.execute(
        "SELECT * FROM relation WHERE relation_id = ?", (relation_id,)
    ).fetchone()
    return _row_to_relation_instance(row) if row else None


def list_relations(
    conn: sqlite3.Connection,
    *,
    src_kind: str | None = None,
    src_id: str | None = None,
    dst_kind: str | None = None,
    dst_id: str | None = None,
    relation_name: str | None = None,
    domain: str | None = None,
) -> list[RelationInstance]:
    clauses: list[str] = []
    params: list[Any] = []
    if src_kind is not None:
        clauses.append("src_kind = ?")
        params.append(src_kind)
    if src_id is not None:
        clauses.append("src_id = ?")
        params.append(src_id)
    if dst_kind is not None:
        clauses.append("dst_kind = ?")
        params.append(dst_kind)
    if dst_id is not None:
        clauses.append("dst_id = ?")
        params.append(dst_id)
    if relation_name is not None:
        clauses.append("relation_name = ?")
        params.append(relation_name)
    if domain is not None:
        clauses.append("domain = ?")
        params.append(domain)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM relation{where} ORDER BY relation_id", params
    ).fetchall()
    return [_row_to_relation_instance(r) for r in rows]


def delete_relation(conn: sqlite3.Connection, relation_id: int) -> bool:
    cur = conn.execute(
        "DELETE FROM relation WHERE relation_id = ?", (relation_id,)
    )
    conn.commit()
    return cur.rowcount > 0


# ---- Inverse-relation helper --------------------------------------

def inverse_relation_name(
    conn: sqlite3.Connection, relation_name: str
) -> str | None:
    """Return the inverse relation name, if registered.

    Reads from the ``inverse_name`` column. If the relation is
    symmetric (e.g., ``related-to``), the relation is its own
    inverse and the returned name is equal to ``relation_name``.
    Returns None if the relation is not registered.
    """
    rd = get_relation_def(conn, relation_name)
    return rd.inverse_name if rd else None
