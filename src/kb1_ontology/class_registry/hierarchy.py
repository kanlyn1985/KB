"""Hierarchy queries over the class registry.

A class hierarchy is a forest of trees. The root of every tree
is a Meta-layer class with ``parent_class_id IS NULL``. The
transitive closure (ancestors, descendants) is computed via
recursive CTEs, which SQLite supports from version 3.8.3.
"""
from __future__ import annotations

import sqlite3


def is_subclass_of(
    conn: sqlite3.Connection, child_id: str, parent_id: str
) -> bool:
    """Return True if ``child_id`` is the same as ``parent_id`` or
    a transitive descendant of it."""
    if child_id == parent_id:
        return True
    row = conn.execute(
        """
        WITH RECURSIVE ancestors(child, parent) AS (
            SELECT class_id, parent_class_id FROM class_def
            WHERE class_id = ?
            UNION ALL
            SELECT cd.class_id, cd.parent_class_id
            FROM class_def cd
            JOIN ancestors a ON a.parent = cd.class_id
        )
        SELECT 1 AS hit
        FROM ancestors
        WHERE parent = ?
        LIMIT 1
        """,
        (child_id, parent_id),
    ).fetchone()
    return row is not None


def get_ancestors(conn: sqlite3.Connection, class_id: str) -> list[str]:
    """Return ``[class_id, parent, grandparent, ..., root]`` in
    bottom-up order. The first element is the class itself."""
    rows = conn.execute(
        """
        WITH RECURSIVE ancestors(child, parent, depth) AS (
            SELECT class_id, parent_class_id, 0 FROM class_def
            WHERE class_id = ?
            UNION ALL
            SELECT a.child, cd.parent_class_id, a.depth + 1
            FROM ancestors a
            JOIN class_def cd ON cd.class_id = a.parent
            WHERE a.parent IS NOT NULL
        )
        SELECT parent FROM ancestors WHERE parent IS NOT NULL
        ORDER BY depth
        """,
        (class_id,),
    ).fetchall()
    return [r["parent"] for r in rows]


def get_descendants(
    conn: sqlite3.Connection, class_id: str
) -> list[str]:
    """Return all strict descendants of ``class_id``, in
    top-down order (closest first). The class itself is NOT
    included.

    Implementation note: a single class can be reached through
    multiple paths in a tree, so the CTE has to track the set of
    already-visited nodes to avoid duplicates. We use a recursive
    CTE with DISTINCT, then ORDER by depth.
    """
    rows = conn.execute(
        """
        WITH RECURSIVE descendants(node, depth) AS (
            SELECT class_id, 0 FROM class_def
            WHERE parent_class_id = ?
            UNION
            SELECT cd.class_id, d.depth + 1
            FROM descendants d
            JOIN class_def cd ON cd.parent_class_id = d.node
        )
        SELECT DISTINCT node AS descendant, MIN(depth) AS best_depth
        FROM descendants
        GROUP BY node
        ORDER BY best_depth, node
        """,
        (class_id,),
    ).fetchall()
    return [r["descendant"] for r in rows]


def check_acyclic(conn: sqlite3.Connection) -> bool:
    """Return True if the whole hierarchy is acyclic.

    A cycle would be a class appearing in its own ancestor chain.
    """
    row = conn.execute(
        """
        WITH RECURSIVE up(cls) AS (
            SELECT class_id FROM class_def
            UNION ALL
            SELECT cd.parent_class_id
            FROM class_def cd
            JOIN up ON up.cls = cd.class_id
            WHERE cd.parent_class_id IS NOT NULL
        )
        SELECT class_id, COUNT(*) AS depth
        FROM class_def
        JOIN up ON up.cls = class_def.class_id
        GROUP BY class_id
        HAVING depth > 100
        LIMIT 1
        """
    ).fetchone()
    return row is None
