"""Graph traversal over the relation table.

The whole point of having a relation registry is to support
**structured graph queries**: given a starting entity, find
what is connected to it via N hops of relations. This is what
makes ontology-driven queries different from RAG.
"""
from __future__ import annotations

import sqlite3
from collections import deque
from typing import Iterable

from .crud import (
    create_relation,
    get_relation_def,
    list_relations,
)
from .schema import (
    CATEGORY_STRUCTURAL,
    RelationInstance,
    SCOPE_CORE,
    _row_to_relation_instance,
)


def relations_of(
    conn: sqlite3.Connection,
    *,
    src_id: str,
    src_kind: str = "entity",
    direction: str = "outgoing",
    relation_name: str | None = None,
    category: str | None = None,
    domain: str | None = None,
) -> list[RelationInstance]:
    """Return relations attached to a single node.

    ``direction``:
      - ``"outgoing"`` (default) — relations where ``src_id`` is
        the start node
      - ``"incoming"`` — relations where the start node is the
        destination
      - ``"both"`` — union of the two
    """
    if direction not in {"outgoing", "incoming", "both"}:
        raise ValueError(
            f"direction must be outgoing/incoming/both, got {direction!r}"
        )
    out: list[RelationInstance] = []
    if direction in ("outgoing", "both"):
        out.extend(list_relations(
            conn, src_kind=src_kind, src_id=src_id,
            relation_name=relation_name, domain=domain,
        ))
    if direction in ("incoming", "both"):
        rows = conn.execute(
            """
            SELECT * FROM relation
            WHERE dst_kind = ? AND dst_id = ?
              AND (? IS NULL OR relation_name = ?)
              AND (? IS NULL OR domain = ?)
            ORDER BY relation_id
            """,
            (src_kind, src_id,
             relation_name, relation_name,
             domain, domain),
        ).fetchall()
        out.extend(_row_to_relation_instance(r) for r in rows)
    if category is not None:
        out = [r for r in out if _category_of(conn, r.relation_name) == category]
    return out


def _category_of(
    conn: sqlite3.Connection, relation_name: str
) -> str | None:
    rd = get_relation_def(conn, relation_name)
    return rd.category if rd else None


def traverse_relations(
    conn: sqlite3.Connection,
    start_id: str,
    *,
    start_kind: str = "entity",
    max_hops: int = 3,
    relation_name: str | None = None,
    category: str | None = None,
    domain: str | None = None,
) -> list[list[RelationInstance]]:
    """Breadth-first traversal from ``start_id``.

    Returns a list of paths. Each path is a list of
    ``RelationInstance``s, where consecutive relations connect
    (i.e., the dst of one is the src of the next). Paths of
    length 0 (the start node alone) are NOT included — only
    real walks.

    The traversal respects a category filter: structural
    relations (``is-a``, ``part-of``) are followed preferentially
    because they form the ontology's skeleton.
    """
    if max_hops < 1:
        return []
    results: list[list[RelationInstance]] = []
    queue: deque[list[RelationInstance]] = deque()

    # Seed with single-hop paths
    seed = relations_of(
        conn, src_id=start_id, src_kind=start_kind,
        direction="outgoing", relation_name=relation_name,
        category=category, domain=domain,
    )
    for r in seed:
        results.append([r])
        queue.append([r])

    while queue:
        path = queue.popleft()
        if len(path) >= max_hops:
            continue
        # Per-path visited: only nodes already on the current
        # path are forbidden. This permits the same node to be
        # reached via different paths (a real graph traversal
        # requirement), but blocks genuine cycles.
        path_nodes: set[tuple[str, str]] = {(start_kind, start_id)}
        for r in path:
            path_nodes.add((r.src_kind, r.src_id))
        last = path[-1]
        next_rels = relations_of(
            conn, src_id=last.dst_id, src_kind=last.dst_kind,
            direction="outgoing", relation_name=relation_name,
            category=category, domain=domain,
        )
        for r in next_rels:
            if (r.dst_kind, r.dst_id) in path_nodes:
                # True cycle: this node is already on the path
                continue
            new_path = path + [r]
            results.append(new_path)
            if len(new_path) < max_hops:
                queue.append(new_path)

    # Stable ordering: shorter paths first, then by relation_id
    results.sort(key=lambda p: (len(p), [r.relation_id for r in p]))
    return results
