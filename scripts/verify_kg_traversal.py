#!/usr/bin/env python3
"""Verify knowledge-graph traversal works for multi-hop queries.

Demonstrates Phase E: the KG (relation table) can answer cross-document
questions that wiki chunks alone cannot.

Usage:
  python scripts/verify_kg_traversal.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DB = ROOT / "knowledge_base" / "ontology" / "ontology.db"


def _entity_id(conn, name: str) -> str | None:
    row = conn.execute(
        "SELECT entity_id FROM entity WHERE canonical_name = ? LIMIT 1",
        (name,),
    ).fetchone()
    return row[0] if row else None


def _traverse(conn, src_id: str, max_hops: int = 3) -> list[dict]:
    """BFS traversal via SQL recursive CTE."""
    rows = conn.execute(
        """
        WITH RECURSIVE walk(src, dst, relation_name, depth, path) AS (
            SELECT src_id, dst_id, relation_name, 1,
                   src_id || ' --' || relation_name || '--> ' || dst_id
            FROM relation
            WHERE src_id = ? AND src_kind = 'entity' AND dst_kind = 'entity'
            UNION ALL
            SELECT w.dst, r.dst_id, r.relation_name, w.depth + 1,
                   w.path || ' --' || r.relation_name || '--> ' || r.dst_id
            FROM walk w
            JOIN relation r
              ON r.src_id = w.dst
             AND r.src_kind = 'entity'
             AND r.dst_kind = 'entity'
            WHERE w.depth < ?
        )
        SELECT DISTINCT e.canonical_name AS dst_name, relation_name, depth, path
        FROM walk
        JOIN entity e ON e.entity_id = walk.dst
        ORDER BY depth, dst_name
        """,
        (src_id, max_hops),
    ).fetchall()
    return [dict(r) for r in rows]


def main():
    if not DB.exists():
        print(f"Ontology DB not found: {DB}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    # Test cases: name -> expected to reach
    test_cases = [
        ("GB/T 18487.1", 2, "Multi-hop: 18487.1 → depends-on → referenced standards"),
        ("ISO 14229-1", 2, "Multi-hop: 14229-1 → references → other standards"),
        ("GB/T 18487.1", 1, "1-hop references from 18487.1"),
    ]

    print("=" * 60)
    print("KG Traversal Verification")
    print("=" * 60)

    for name, hops, desc in test_cases:
        eid = _entity_id(conn, name)
        if not eid:
            print(f"\n[{name}] ENTITY NOT FOUND")
            continue

        print(f"\n[{name}] {desc}")
        results = _traverse(conn, eid, max_hops=hops)
        print(f"  Reachable in {hops} hops: {len(results)} entities")
        # Show first 5 by depth
        seen = set()
        count = 0
        for r in results:
            key = (r["depth"], r["dst_name"])
            if key in seen:
                continue
            seen.add(key)
            count += 1
            if count <= 8:
                print(f"  hop {r['depth']} [{r['relation_name']:12s}] {r['dst_name'][:30]}")
        if len(seen) > 8:
            print(f"  ... +{len(seen) - 8} more")

    # Semantic relation counts
    print("\n" + "=" * 60)
    print("Semantic relation coverage")
    print("=" * 60)
    counts = conn.execute(
        """
        SELECT relation_name, COUNT(*) AS cnt
        FROM relation
        WHERE relation_name != 'references'
        GROUP BY relation_name
        ORDER BY cnt DESC
        """
    ).fetchall()
    for r in counts:
        print(f"  {r['relation_name']:15s}: {r['cnt']:3d}")

    # Specific check: ISO 14229 series semantic relations
    print("\n=== ISO 14229 series internal relations ===")
    rows = conn.execute(
        """
        SELECT s.canonical_name, r.relation_name, d.canonical_name
        FROM relation r
        JOIN entity s ON r.src_id = s.entity_id
        JOIN entity d ON r.dst_id = d.entity_id
        WHERE r.relation_name != 'references'
          AND (s.canonical_name LIKE 'ISO 14229%' AND d.canonical_name LIKE 'ISO 14229%')
        """
    ).fetchall()
    if not rows:
        print("  (none — pending extraction of ISO 14229 chunks)")
    else:
        for r in rows:
            print(f"  {r[0]} --{r[1]}--> {r[2]}")

    conn.close()


if __name__ == "__main__":
    main()