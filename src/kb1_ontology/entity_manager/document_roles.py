"""Document-role association.

A document can be associated with one or more engineering roles.
This module provides CRUD for the ``document_role`` table.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from .schema import (
    DocumentRole,
    JOB_ROLES,
    _document_role_to_dict,
    _row_to_document_role,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def set_document_roles(
    conn: sqlite3.Connection,
    source_path: str,
    job_roles: list[str],
) -> list[DocumentRole]:
    """Replace the document's role list with the given set.

    Idempotent: re-calling with the same set has no effect.
    """
    # Validate
    for r in job_roles:
        if r not in JOB_ROLES:
            raise ValueError(
                f"unknown job_role {r!r}; valid roles are {JOB_ROLES}"
            )

    # Remove existing
    conn.execute(
        "DELETE FROM document_role WHERE source_path = ?", (source_path,)
    )

    # Insert new
    now = _utc_now()
    out: list[DocumentRole] = []
    for r in job_roles:
        role = DocumentRole(
            source_path=source_path, job_role=r, created_at=now,
        )
        conn.execute(
            """
            INSERT INTO document_role
                (source_path, job_role, created_at)
            VALUES (:source_path, :job_role, :created_at)
            """,
            _document_role_to_dict(role),
        )
        out.append(role)
    conn.commit()
    return out


def get_document_roles(
    conn: sqlite3.Connection, source_path: str
) -> list[str]:
    """Return the document's job roles, sorted."""
    rows = conn.execute(
        "SELECT job_role FROM document_role WHERE source_path = ? "
        "ORDER BY job_role",
        (source_path,),
    ).fetchall()
    return [r["job_role"] for r in rows]


def add_document_role(
    conn: sqlite3.Connection, source_path: str, job_role: str
) -> DocumentRole:
    """Add a single role. Idempotent."""
    if job_role not in JOB_ROLES:
        raise ValueError(
            f"unknown job_role {job_role!r}; valid roles are {JOB_ROLES}"
        )
    # Check if already present
    existing = conn.execute(
        "SELECT 1 FROM document_role WHERE source_path = ? AND job_role = ?",
        (source_path, job_role),
    ).fetchone()
    if existing:
        rows = conn.execute(
            "SELECT * FROM document_role WHERE source_path = ? AND job_role = ?",
            (source_path, job_role),
        ).fetchall()
        return _row_to_document_role(rows[0])
    role = DocumentRole(
        source_path=source_path,
        job_role=job_role,
        created_at=_utc_now(),
    )
    conn.execute(
        """
        INSERT INTO document_role
            (source_path, job_role, created_at)
        VALUES (:source_path, :job_role, :created_at)
        """,
        _document_role_to_dict(role),
    )
    conn.commit()
    return role


def remove_document_role(
    conn: sqlite3.Connection, source_path: str, job_role: str
) -> bool:
    """Remove a role. Returns True if a row was removed."""
    cur = conn.execute(
        "DELETE FROM document_role WHERE source_path = ? AND job_role = ?",
        (source_path, job_role),
    )
    conn.commit()
    return cur.rowcount > 0
