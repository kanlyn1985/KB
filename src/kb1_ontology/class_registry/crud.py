"""CRUD operations for class definitions.

These are intentionally thin wrappers over SQLite that enforce the
business rules the schema cannot express in DDL:

- The root class (Thing) has ``parent_class_id = NULL``.
- A class must be created AFTER its parent exists.
- Cycles are forbidden (delegated to ``hierarchy.check_acyclic``).
- Domain-layer classes must declare a ``domain``; Meta-layer
  classes must not.

Errors are raised as ``ClassRegistryError`` so callers can
distinguish registry errors from generic database errors.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from .hierarchy import check_acyclic
from .schema import (
    ClassDef,
    LAYER_DOMAIN,
    LAYER_META,
    VALID_LAYERS,
    _class_to_dict,
    _row_to_class,
)


class ClassRegistryError(Exception):
    """Raised when an operation violates a class-registry invariant."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _validate_new_class(
    class_id: str,
    class_name: str,
    parent_class_id: str | None,
    layer: str,
    domain: str | None,
) -> None:
    if not class_id or not class_id.strip():
        raise ClassRegistryError("class_id is required")
    if not class_name or not class_name.strip():
        raise ClassRegistryError("class_name is required")
    if layer not in VALID_LAYERS:
        raise ClassRegistryError(
            f"layer must be one of {sorted(VALID_LAYERS)}, got {layer!r}"
        )
    if layer == LAYER_META and domain is not None:
        raise ClassRegistryError(
            f"Meta-layer classes must not have a domain, got {domain!r}"
        )
    if layer == LAYER_DOMAIN and not domain:
        raise ClassRegistryError(
            "Domain-layer classes must declare a domain"
        )


def create_class(
    conn: sqlite3.Connection,
    class_id: str,
    class_name: str,
    parent_class_id: str | None,
    layer: str,
    domain: str | None = None,
    description: str | None = None,
    is_core: bool = False,
) -> ClassDef:
    """Insert a new class.

    Pre-conditions:
    * The class_id is unique.
    * If parent_class_id is given, the parent must exist.
    * The new class must not create a cycle in the parent chain.

    Returns the persisted ``ClassDef``.
    """
    _validate_new_class(class_id, class_name, parent_class_id, layer, domain)

    if parent_class_id is not None:
        parent = get_class(conn, parent_class_id)
        if parent is None:
            raise ClassRegistryError(
                f"parent_class_id {parent_class_id!r} does not exist"
            )
        # Layer rules: Domain classes must be children of Meta
        # classes. Meta classes can only be children of other Meta
        # classes (which is the layer invariant).
        if layer == LAYER_DOMAIN and parent.layer != LAYER_META:
            raise ClassRegistryError(
                f"Domain classes must have a Meta parent, got "
                f"parent layer {parent.layer!r}"
            )
        if layer == LAYER_META and parent.layer != LAYER_META:
            raise ClassRegistryError(
                f"Meta classes can only have Meta parents, got "
                f"parent layer {parent.layer!r}"
            )

    # Cycle check: if we add (parent_class_id -> class_id), the
    # resulting graph must remain acyclic. This is equivalent to
    # checking that class_id is not currently an ancestor of
    # parent_class_id.
    if parent_class_id is not None:
        from .hierarchy import get_ancestors
        existing_ancestors = get_ancestors(conn, parent_class_id)
        if class_id in existing_ancestors:
            raise ClassRegistryError(
                f"adding {class_id!r} under {parent_class_id!r} would "
                f"create a cycle"
            )

    cls = ClassDef(
        class_id=class_id,
        class_name=class_name,
        parent_class_id=parent_class_id,
        layer=layer,
        domain=domain,
        description=description,
        is_core=is_core,
        created_at=_utc_now(),
    )
    try:
        conn.execute(
            """
            INSERT INTO class_def
                (class_id, class_name, parent_class_id, layer, domain,
                 description, is_core, created_at)
            VALUES (:class_id, :class_name, :parent_class_id, :layer,
                    :domain, :description, :is_core, :created_at)
            """,
            _class_to_dict(cls),
        )
    except sqlite3.IntegrityError as e:
        raise ClassRegistryError(str(e)) from e
    conn.commit()
    return cls


def get_class(conn: sqlite3.Connection, class_id: str) -> ClassDef | None:
    """Return a class by id, or None if not found."""
    row = conn.execute(
        "SELECT * FROM class_def WHERE class_id = ?", (class_id,)
    ).fetchone()
    return _row_to_class(row) if row else None


def list_classes(
    conn: sqlite3.Connection,
    *,
    layer: str | None = None,
    domain: str | None = None,
    is_core: bool | None = None,
) -> list[ClassDef]:
    """List classes, optionally filtered by layer / domain / is_core."""
    clauses: list[str] = []
    params: list[Any] = []
    if layer is not None:
        clauses.append("layer = ?")
        params.append(layer)
    if domain is not None:
        clauses.append("domain = ?")
        params.append(domain)
    if is_core is not None:
        clauses.append("is_core = ?")
        params.append(1 if is_core else 0)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM class_def{where} ORDER BY class_id", params
    ).fetchall()
    return [_row_to_class(r) for r in rows]


def update_class(
    conn: sqlite3.Connection,
    class_id: str,
    *,
    class_name: str | None = None,
    description: str | None = None,
    is_core: bool | None = None,
) -> ClassDef:
    """Update mutable fields. ``parent_class_id`` and ``layer`` and
    ``domain`` are immutable post-creation (changing them would
    invalidate the hierarchy)."""
    existing = get_class(conn, class_id)
    if existing is None:
        raise ClassRegistryError(f"class {class_id!r} does not exist")
    updates: dict[str, Any] = {}
    if class_name is not None:
        updates["class_name"] = class_name
    if description is not None:
        updates["description"] = description
    if is_core is not None:
        updates["is_core"] = 1 if is_core else 0
    if not updates:
        return existing
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    params = {**updates, "class_id": class_id}
    conn.execute(
        f"UPDATE class_def SET {set_clause} WHERE class_id = :class_id",
        params,
    )
    conn.commit()
    refreshed = get_class(conn, class_id)
    assert refreshed is not None  # we just updated it
    return refreshed


def delete_class(conn: sqlite3.Connection, class_id: str) -> bool:
    """Delete a class. Returns True if a row was removed.

    Fails if the class has children, because the schema's
    ``ON DELETE RESTRICT`` on ``parent_class_id`` would block
    deletion. We pre-check and raise a clean error.
    """
    existing = get_class(conn, class_id)
    if existing is None:
        return False
    children = conn.execute(
        "SELECT COUNT(*) AS n FROM class_def WHERE parent_class_id = ?",
        (class_id,),
    ).fetchone()["n"]
    if children > 0:
        raise ClassRegistryError(
            f"cannot delete {class_id!r}: {children} child class(es) "
            f"still reference it"
        )
    conn.execute("DELETE FROM class_def WHERE class_id = ?", (class_id,))
    conn.commit()
    return True
