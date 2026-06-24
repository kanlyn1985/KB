"""CRUD operations for the attribute store.

Attributes are unique on ``(subject_kind, subject_id, attribute_name)``.
``set_attribute`` is therefore upsert: re-calling it overwrites
the previous value. This is the right semantic for an attribute
("the value of X is now Y").
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from .range_parser import RangeValue, parse_range_value
from .schema import (
    VALID_VALUE_TYPES,
    Attribute,
    _row_to_attribute,
)


class AttributeStoreError(Exception):
    """Raised when an operation violates an attribute-store invariant."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _validate_attr(
    subject_kind: str, attribute_name: str, value_type: str
) -> None:
    if subject_kind not in {"entity", "class"}:
        raise AttributeStoreError(
            f"subject_kind must be 'entity' or 'class', got {subject_kind!r}"
        )
    if not attribute_name or not attribute_name.strip():
        raise AttributeStoreError("attribute_name is required")
    if value_type not in VALID_VALUE_TYPES:
        raise AttributeStoreError(
            f"value_type must be one of {sorted(VALID_VALUE_TYPES)}, "
            f"got {value_type!r}"
        )


def set_attribute(
    conn: sqlite3.Connection,
    subject_kind: str,
    subject_id: str,
    attribute_name: str,
    *,
    value_text: str | None = None,
    value_num: float | None = None,
    value_min: float | None = None,
    value_max: float | None = None,
    value_unit: str | None = None,
    value_tol: float | None = None,
    value_ref_kind: str | None = None,
    value_ref_id: str | None = None,
    value_type: str = "string",
    source_path: str | None = None,
) -> Attribute:
    """Insert or update an attribute.

    Unique on (subject_kind, subject_id, attribute_name). Calling
    twice with the same key overwrites the previous value.

    For convenience, if value_text is provided and value_type is
    "number" or "range", the text is parsed to populate the
    numeric fields. If the text is unparseable, the value_type
    is downgraded to "string".
    """
    _validate_attr(subject_kind, attribute_name, value_type)

    # Verify referent exists for reference-typed attributes
    if value_type == "reference":
        if not value_ref_kind or not value_ref_id:
            raise AttributeStoreError(
                "value_ref_kind and value_ref_id are required for "
                "value_type='reference'"
            )
        if value_ref_kind not in {"entity", "class"}:
            raise AttributeStoreError(
                f"value_ref_kind must be 'entity' or 'class', "
                f"got {value_ref_kind!r}"
            )
        if value_ref_kind == "entity":
            row = conn.execute(
                "SELECT 1 FROM entity WHERE entity_id = ?", (value_ref_id,)
            ).fetchone()
            if row is None:
                raise AttributeStoreError(
                    f"value_ref entity {value_ref_id!r} does not exist"
                )
        else:
            row = conn.execute(
                "SELECT 1 FROM class_def WHERE class_id = ?", (value_ref_id,)
            ).fetchone()
            if row is None:
                raise AttributeStoreError(
                    f"value_ref class {value_ref_id!r} does not exist"
                )

    # Auto-parse text to numeric if value_type is number/range
    if value_type in ("number", "range") and value_text:
        parsed: RangeValue | None = parse_range_value(value_text)
        if parsed is not None:
            value_num = parsed.nominal
            # Also inherit the unit from the parsed text, unless
            # the caller already provided one.
            if parsed.unit and not value_unit:
                value_unit = parsed.unit
            if value_type == "range":
                value_min = parsed.min
                value_max = parsed.max
                value_tol = parsed.tolerance
        else:
            # Unparseable text — keep as string
            value_type = "string"

    try:
        conn.execute(
            """
            INSERT INTO attribute
                (subject_kind, subject_id, attribute_name, value_type,
                 value_text, value_num, value_min, value_max,
                 value_unit, value_tol, value_ref_kind, value_ref_id,
                 source_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (subject_kind, subject_id, attribute_name) DO
            UPDATE SET
                value_type = excluded.value_type,
                value_text = excluded.value_text,
                value_num = excluded.value_num,
                value_min = excluded.value_min,
                value_max = excluded.value_max,
                value_unit = excluded.value_unit,
                value_tol = excluded.value_tol,
                value_ref_kind = excluded.value_ref_kind,
                value_ref_id = excluded.value_ref_id,
                source_path = excluded.source_path,
                created_at = excluded.created_at
            """,
            (subject_kind, subject_id, attribute_name, value_type,
             value_text, value_num, value_min, value_max,
             value_unit, value_tol, value_ref_kind, value_ref_id,
             source_path, _utc_now()),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise AttributeStoreError(str(e)) from e

    return get_attribute(
        conn, subject_kind=subject_kind, subject_id=subject_id,
        attribute_name=attribute_name,
    )  # type: ignore[return-value]


def get_attribute(
    conn: sqlite3.Connection,
    subject_kind: str,
    subject_id: str,
    attribute_name: str,
) -> Attribute | None:
    row = conn.execute(
        """
        SELECT * FROM attribute
        WHERE subject_kind = ? AND subject_id = ? AND attribute_name = ?
        """,
        (subject_kind, subject_id, attribute_name),
    ).fetchone()
    return _row_to_attribute(row) if row else None


def list_attributes(
    conn: sqlite3.Connection,
    *,
    subject_kind: str | None = None,
    subject_id: str | None = None,
    attribute_name: str | None = None,
) -> list[Attribute]:
    clauses: list[str] = []
    params: list[Any] = []
    if subject_kind is not None:
        clauses.append("subject_kind = ?")
        params.append(subject_kind)
    if subject_id is not None:
        clauses.append("subject_id = ?")
        params.append(subject_id)
    if attribute_name is not None:
        clauses.append("attribute_name = ?")
        params.append(attribute_name)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM attribute{where} ORDER BY attribute_id", params
    ).fetchall()
    return [_row_to_attribute(r) for r in rows]


def delete_attribute(
    conn: sqlite3.Connection,
    subject_kind: str,
    subject_id: str,
    attribute_name: str,
) -> bool:
    cur = conn.execute(
        """
        DELETE FROM attribute
        WHERE subject_kind = ? AND subject_id = ? AND attribute_name = ?
        """,
        (subject_kind, subject_id, attribute_name),
    )
    conn.commit()
    return cur.rowcount > 0


def query_attributes(
    conn: sqlite3.Connection,
    *,
    attribute_name: str | None = None,
    value_type: str | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    subject_kind: str | None = None,
    value_ref_kind: str | None = None,
    value_ref_id: str | None = None,
) -> list[Attribute]:
    """Query attributes by name, type, value range, or reference target.

    This is the core "attribute-value" query: find all entities
    whose attribute matches a filter.
    """
    clauses: list[str] = []
    params: list[Any] = []
    if attribute_name is not None:
        clauses.append("attribute_name = ?")
        params.append(attribute_name)
    if value_type is not None:
        clauses.append("value_type = ?")
        params.append(value_type)
    if min_value is not None:
        clauses.append("value_num >= ?")
        params.append(min_value)
    if max_value is not None:
        clauses.append("value_num <= ?")
        params.append(max_value)
    if subject_kind is not None:
        clauses.append("subject_kind = ?")
        params.append(subject_kind)
    if value_ref_kind is not None:
        clauses.append("value_ref_kind = ?")
        params.append(value_ref_kind)
    if value_ref_id is not None:
        clauses.append("value_ref_id = ?")
        params.append(value_ref_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM attribute{where} ORDER BY attribute_id", params
    ).fetchall()
    return [_row_to_attribute(r) for r in rows]
