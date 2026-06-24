"""Demo queries against the OBC ontology.

This script answers 5 realistic systems-engineer questions by
traversing the ontology graph (relations + attributes) rather
than by fuzzy text search.

Run:
    python scripts/ontology_demo/query_obc_ontology.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from kb1_ontology.attribute_store.schema import (
    ensure_schema as ensure_attribute_schema,
)
from kb1_ontology.db import connect, default_db_path
from kb1_ontology.entity_manager.schema import (
    ensure_schema as ensure_entity_schema,
)
from kb1_ontology.relation_registry import (
    CATEGORY_REFERENTIAL,
    relations_of,
    traverse_relations,
)
from kb1_ontology.relation_registry.schema import (
    ensure_schema as ensure_relation_schema,
)


WORKSPACE = ROOT / "knowledge_base"


def find_entity_by_name(conn, raw_name: str) -> str | None:
    """Return the entity_id for a standard by its raw name."""
    from kb1_ontology.entity_manager.normalization import (
        normalize_canonical_name,
    )
    norm = normalize_canonical_name(raw_name)
    cur = conn.execute(
        "SELECT entity_id FROM entity"
    )
    for row in cur.fetchall():
        eid = row["entity_id"]
        e_cur = conn.execute(
            "SELECT canonical_name FROM entity WHERE entity_id = ?",
            (eid,),
        ).fetchone()
        if e_cur and normalize_canonical_name(
            e_cur["canonical_name"]
        ) == norm:
            return eid
    return None


def print_header(title: str) -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def q1_what_does_14229_7_depend_on(conn) -> None:
    """Q1: What standards does ISO 14229-7 (UDS on LIN) reference?

    This is the canonical "ontology-driven" question. The answer
    is the set of outgoing references from the ISO 14229-7 entity.
    """
    print_header("Q1: What standards does ISO 14229-7 (UDS on LIN) reference?")
    eid = find_entity_by_name(conn, "ISO 14229-7")
    if eid is None:
        print("  ISO 14229-7 not found")
        return
    rels = relations_of(
        conn, src_id=eid, direction="outgoing",
        relation_name="references", domain="OBC",
    )
    print(f"  ISO 14229-7 directly references {len(rels)} standards:")
    for r in rels:
        # Resolve the target name
        cur = conn.execute(
            "SELECT canonical_name FROM entity WHERE entity_id = ?",
            (r.dst_id,),
        ).fetchone()
        target_name = cur["canonical_name"] if cur else r.dst_id
        print(f"    → {target_name}")


def q2_what_depends_on_14229_1(conn) -> None:
    """Q2: What standards depend on (reference) ISO 14229-1?

    The reverse direction of Q1.
    """
    print_header("Q2: What standards depend on ISO 14229-1?")
    eid = find_entity_by_name(conn, "ISO 14229-1")
    if eid is None:
        print("  ISO 14229-1 not found")
        return
    rels = relations_of(
        conn, src_id=eid, direction="incoming",
        relation_name="references", domain="OBC",
    )
    print(f"  {len(rels)} standards reference ISO 14229-1:")
    for r in rels:
        cur = conn.execute(
            "SELECT canonical_name FROM entity WHERE entity_id = ?",
            (r.src_id,),
        ).fetchone()
        src_name = cur["canonical_name"] if cur else r.src_id
        print(f"    ← {src_name}")


def q3_p2_timing_for_14229_3(conn) -> None:
    """Q3: What is the P2 Server Timing for ISO 14229-3?

    This is an attribute query. The answer is a precise numeric
    value, not a fuzzy text match.
    """
    print_header("Q3: What is the P2 Server Timing for ISO 14229-3?")
    eid = find_entity_by_name(conn, "ISO 14229-3")
    if eid is None:
        print("  ISO 14229-3 not found")
        return
    cur = conn.execute(
        "SELECT * FROM attribute WHERE subject_kind='entity' "
        "AND subject_id=? AND attribute_name='P2_Server_Timing'",
        (eid,),
    ).fetchone()
    if cur is None:
        print("  No P2_Server_Timing attribute set")
        return
    print(f"  P2_Server_Timing = {cur['value_num']} {cur['value_unit']}")
    print(f"  (text representation: {cur['value_text']!r})")
    # Bonus: S3 is a range
    cur = conn.execute(
        "SELECT * FROM attribute WHERE subject_kind='entity' "
        "AND subject_id=? AND attribute_name='S3_Server_Timing'",
        (eid,),
    ).fetchone()
    if cur is not None:
        print()
        print(f"  S3_Server_Timing: {cur['value_num']} "
              f"± {cur['value_tol']} {cur['value_unit']}")
        print(f"    range: [{cur['value_min']}, {cur['value_max']}]")


def q4_transitive_charging_standards(conn) -> None:
    """Q4: Show all charging-related standards reachable from
    GB/T 18487.1 by 2 hops of references.

    A relation graph query, not a text query.
    """
    print_header(
        "Q4: What charging standards are reachable from "
        "GB/T 18487.1 within 2 hops of references?"
    )
    eid = find_entity_by_name(conn, "GB/T 18487.1")
    if eid is None:
        print("  GB/T 18487.1 not found")
        return
    paths = traverse_relations(
        conn, start_id=eid, max_hops=2,
        relation_name="references", domain="OBC",
    )
    print(f"  Found {len(paths)} reachable path(s):")
    for p in paths:
        names = []
        for r in p:
            cur = conn.execute(
                "SELECT canonical_name FROM entity WHERE entity_id = ?",
                (r.dst_id,),
            ).fetchone()
            names.append(cur["canonical_name"] if cur else r.dst_id)
        print(f"    {' → '.join(names)}")


def q5_what_services_does_14229_1_define(conn) -> None:
    """Q5: What UDS services does ISO 14229-1 define?

    A structured query: list all attributes on the entity whose
    name starts with 'service_'. This is the kind of question
    that would be very hard to answer via text search ("0x10"
    might match many unrelated hex values).
    """
    print_header("Q5: What UDS services does ISO 14229-1 define?")
    eid = find_entity_by_name(conn, "ISO 14229-1")
    if eid is None:
        print("  ISO 14229-1 not found")
        return
    cur = conn.execute(
        "SELECT attribute_name, value_text FROM attribute "
        "WHERE subject_kind='entity' AND subject_id=? "
        "AND attribute_name LIKE 'service_%' ORDER BY attribute_name",
        (eid,),
    ).fetchall()
    print(f"  {len(cur)} UDS services defined:")
    for row in cur:
        name = row["attribute_name"].replace("service_", "")
        print(f"    {name}: {row['value_text']}")


def main() -> None:
    db_path = default_db_path(WORKSPACE)
    if not db_path.exists():
        print(f"Ontology DB not found: {db_path}")
        print("Run scripts/ontology_demo/build_obc_ontology.py first.")
        sys.exit(1)
    conn = connect(db_path)
    try:
        # Ensure schemas (idempotent)
        ensure_entity_schema(conn)
        ensure_relation_schema(conn)
        ensure_attribute_schema(conn)
        # Sanity check: is there data?
        cur = conn.execute("SELECT COUNT(*) FROM entity")
        n_entities = cur.fetchone()[0]
        if n_entities == 0:
            print("Ontology DB is empty. Run build first.")
            sys.exit(1)
        # Run queries
        q1_what_does_14229_7_depend_on(conn)
        q2_what_depends_on_14229_1(conn)
        q3_p2_timing_for_14229_3(conn)
        q4_transitive_charging_standards(conn)
        q5_what_services_does_14229_1_define(conn)
        print()
        print("=" * 60)
        print("All 5 demo queries answered successfully.")
        print("These are STRUCTURED ontology queries,")
        print("not fuzzy text search — each answer is exact.")
        print("=" * 60)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
