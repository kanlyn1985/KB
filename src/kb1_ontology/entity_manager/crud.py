"""CRUD operations for entity instances.

Provides:
- ``create_entity`` — insert a new entity
- ``get_entity`` — fetch by id
- ``list_entities`` — query with optional filters
- ``find_or_create_entity`` — idempotent insert keyed on
  (normalized_name, class_id, domain)
- ``merge_aliases`` — accumulate alias strings into an entity

De-duplication: entities are unique on
``(canonical_name, class_id, domain)``. ``find_or_create_entity``
runs the name through ``normalize_canonical_name`` before
checking, so variations like "ISO 14229-1—2013" and "ISO 14229-1"
collapse to the same row.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from .normalization import normalize_canonical_name
from .schema import (
    Entity,
    _entity_to_dict,
    _row_to_entity,
)


def _light_normalize(s: str) -> str:
    """Normalize a string for de-duplication of aliases.

    Whitespace, NFKC, and case — but NOT year-stripping. The
    year is the distinguishing information for standard codes:
    "ISO 14229-1:2013" and "ISO 14229-1:2022" are different
    standards, not the same one written two ways.
    """
    import unicodedata
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s).strip()
    s = " ".join(s.split())  # collapse whitespace
    return s.lower()


class EntityManagerError(Exception):
    """Raised when an operation violates an entity-manager invariant."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _validate_new_entity(
    entity_id: str,
    canonical_name: str,
    class_id: str,
) -> None:
    if not entity_id or not entity_id.strip():
        raise EntityManagerError("entity_id is required")
    if not canonical_name or not canonical_name.strip():
        raise EntityManagerError("canonical_name is required")
    if not class_id or not class_id.strip():
        raise EntityManagerError("class_id is required")


def create_entity(
    conn: sqlite3.Connection,
    entity_id: str,
    canonical_name: str,
    class_id: str,
    domain: str | None = None,
    description: str | None = None,
    aliases: list[str] | None = None,
    source_path: str | None = None,
) -> Entity:
    """Insert a new entity.

    Pre-conditions:
      - ``class_id`` must already exist in ``class_def``.
      - ``(canonical_name, class_id, domain)`` must be unique.

    Returns the persisted ``Entity``.
    """
    _validate_new_entity(entity_id, canonical_name, class_id)

    # Sanity: class must exist
    cls_row = conn.execute(
        "SELECT 1 FROM class_def WHERE class_id = ?", (class_id,)
    ).fetchone()
    if cls_row is None:
        raise EntityManagerError(
            f"class_id {class_id!r} does not exist in class_def"
        )

    # Store aliases as raw strings, deduped by **light** form
    # (whitespace + case only — NOT year-stripped, because the
    # year IS the distinguishing information for standards).
    alias_list: list[str] = []
    canonical_light = _light_normalize(canonical_name)
    seen_lights: set[str] = set()
    for a in aliases or []:
        a_light = _light_normalize(a)
        if not a_light or a_light == canonical_light:
            continue
        if a_light in seen_lights:
            continue
        seen_lights.add(a_light)
        alias_list.append(a)

    entity = Entity(
        entity_id=entity_id,
        canonical_name=canonical_name,
        class_id=class_id,
        domain=domain,
        description=description,
        aliases_json=json.dumps(alias_list, ensure_ascii=False),
        source_path=source_path,
        created_at=_utc_now(),
    )
    try:
        conn.execute(
            """
            INSERT INTO entity
                (entity_id, canonical_name, class_id, domain, description,
                 aliases_json, source_path, created_at)
            VALUES (:entity_id, :canonical_name, :class_id, :domain,
                    :description, :aliases_json, :source_path, :created_at)
            """,
            _entity_to_dict(entity),
        )
    except sqlite3.IntegrityError as e:
        raise EntityManagerError(str(e)) from e
    conn.commit()
    return entity


def get_entity(conn: sqlite3.Connection, entity_id: str) -> Entity | None:
    """Return an entity by id, or None if not found."""
    row = conn.execute(
        "SELECT * FROM entity WHERE entity_id = ?", (entity_id,)
    ).fetchone()
    return _row_to_entity(row) if row else None


def list_entities(
    conn: sqlite3.Connection,
    *,
    class_id: str | None = None,
    domain: str | None = None,
    canonical_name: str | None = None,
) -> list[Entity]:
    """List entities, optionally filtered."""
    clauses: list[str] = []
    params: list[Any] = []
    if class_id is not None:
        clauses.append("class_id = ?")
        params.append(class_id)
    if domain is not None:
        clauses.append("domain = ?")
        params.append(domain)
    if canonical_name is not None:
        clauses.append("canonical_name = ?")
        params.append(canonical_name)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM entity{where} ORDER BY entity_id", params
    ).fetchall()
    return [_row_to_entity(r) for r in rows]


def find_or_create_entity(
    conn: sqlite3.Connection,
    raw_canonical_name: str,
    class_id: str,
    domain: str | None = None,
    description: str | None = None,
    source_path: str | None = None,
    extra_aliases: list[str] | None = None,
) -> tuple[Entity, bool]:
    """Return ``(entity, created)`` where ``created`` is True iff
    a new row was inserted.

    The lookup key is the **normalized** name. If an entity with
    the same normalized name, same class, and same domain already
    exists, it is returned as-is. Otherwise a new entity is
    created with a generated entity_id of the form
    ``ENT-{class_id_short}-{N}``.

    Extra aliases are merged into the existing entity's alias list
    (idempotent — duplicates are removed).
    """
    norm = normalize_canonical_name(raw_canonical_name)
    if not norm:
        raise EntityManagerError("raw_canonical_name is empty after normalization")

    # Try to find existing by normalized name
    # Note: we stored the name AS-PROVIDED; the match is done by
    # normalizing both sides at query time. For efficient lookup
    # we compare by re-normalizing the stored name — this is
    # acceptable at Phase 2 scale (entity counts are small).
    candidates = list_entities(
        conn, class_id=class_id, domain=domain
    )
    for c in candidates:
        if normalize_canonical_name(c.canonical_name) == norm:
            # Found existing — merge aliases if any
            if extra_aliases:
                merge_aliases(conn, c.entity_id, extra_aliases)
            # Refresh to get merged alias list
            refreshed = get_entity(conn, c.entity_id)
            assert refreshed is not None
            return refreshed, False

    # Not found — create
    # Generate a deterministic-ish id: ENT-{class_short}-{counter}
    # counter is the count of existing entities for that class.
    short = class_id.split("-")[-1].upper()[:6]  # e.g., STANDARD -> STANDA
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM entity WHERE class_id = ?",
        (class_id,),
    ).fetchone()["n"]
    entity_id = f"ENT-{short}-{count + 1:04d}"

    aliases_combined: list[str] = []
    if extra_aliases:
        # Also store the raw input as an alias (so we don't lose
        # the year suffix or formatting)
        aliases_combined.append(raw_canonical_name)

    new_entity = create_entity(
        conn,
        entity_id=entity_id,
        canonical_name=norm,
        class_id=class_id,
        domain=domain,
        description=description,
        aliases=aliases_combined,
        source_path=source_path,
    )
    return new_entity, True


def merge_aliases(
    conn: sqlite3.Connection,
    entity_id: str,
    new_aliases: list[str],
) -> Entity:
    """Add ``new_aliases`` to the entity's alias list.

    Aliases are stored as **raw strings** (preserving year suffixes
    and formatting). De-duplication is done at the *light* level
    (whitespace + case, not year-stripping) so that
    "ISO 14229-1:2013" and "ISO 14229-1—2013" are recognized as
    the same alias. Different years are NOT collapsed: "ISO
    14229-1:2013" vs "ISO 14229-1:2022" are different standards.

    An alias that light-normalizes to the canonical_name is
    skipped — no point aliasing an entity by its own canonical
    name.
    """
    entity = get_entity(conn, entity_id)
    if entity is None:
        raise EntityManagerError(
            f"entity {entity_id!r} does not exist"
        )
    try:
        existing: list[str] = json.loads(entity.aliases_json or "[]")
    except json.JSONDecodeError:
        existing = []
    existing_lights = {_light_normalize(a) for a in existing}
    canonical_light = _light_normalize(entity.canonical_name)
    added: list[str] = []
    for a in new_aliases:
        a_light = _light_normalize(a)
        if not a_light or a_light == canonical_light:
            continue
        if a_light in existing_lights:
            continue
        existing_lights.add(a_light)
        added.append(a)
    new_list = sorted(set(existing) | set(added))
    conn.execute(
        "UPDATE entity SET aliases_json = ? WHERE entity_id = ?",
        (json.dumps(new_list, ensure_ascii=False), entity_id),
    )
    conn.commit()
    refreshed = get_entity(conn, entity_id)
    assert refreshed is not None
    return refreshed
