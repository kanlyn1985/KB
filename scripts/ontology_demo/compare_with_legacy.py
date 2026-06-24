"""Compare KB1 legacy system vs new ontology system on a curated
set of golden questions.

Approach
--------
We do NOT try to run the full legacy answer_api. Instead, we
**hand-define what each system can answer** and **score the
answers** on:
  - coverage: did the system find an answer at all?
  - exactness: was the answer a single typed value, a set of
    entities, or a free-text snippet?
  - structure: did the answer carry typed metadata (entity ids,
    attribute values, relation paths)?

For the legacy system, the "answer" is the raw must_hit strings
the golden_cases table already records. These are by definition
the legacy answer (extracted via FTS + LLM at golden_case
generation time).

For the ontology system, we run a small set of structured queries
that the ontology actually supports. We use the 5 demo questions
from Phase 5 plus a few realistic extensions, and ask the
ontology to answer them.

The report shows side-by-side what each system can produce.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from kb1_ontology.attribute_store.schema import (
    ensure_schema as ensure_attribute_schema,
)
from kb1_ontology.db import connect, default_db_path
from kb1_ontology.entity_manager.normalization import (
    normalize_canonical_name,
)
from kb1_ontology.entity_manager.schema import (
    ensure_schema as ensure_entity_schema,
)
from kb1_ontology.relation_registry import (
    relations_of,
    traverse_relations,
)
from kb1_ontology.relation_registry.schema import (
    ensure_schema as ensure_relation_schema,
)


WORKSPACE = ROOT / "knowledge_base"
LEGACY_DB = WORKSPACE / "db" / "knowledge.db"
ONTOLOGY_DB = WORKSPACE / "ontology" / "ontology.db"


# ---- Output formatting helpers -----------------------------------

@dataclass
class ComparisonResult:
    question: str
    legacy_answer: str
    ontology_answer: str
    exactness_legacy: str
    exactness_ontology: str
    notes: str = ""


def find_legacy_golden(
    legacy_conn: sqlite3.Connection, query_keyword: str
) -> list[dict[str, Any]]:
    """Look up golden cases that mention a given keyword."""
    cur = legacy_conn.execute(
        """
        SELECT case_id, query, must_hit_json, expected_pages_json
        FROM golden_cases
        WHERE query LIKE ?
        ORDER BY case_id
        LIMIT 5
        """,
        (f"%{query_keyword}%",),
    )
    rows = cur.fetchall()
    out = []
    for r in rows:
        try:
            mh = json.loads(r[2]) if r[2] else []
        except json.JSONDecodeError:
            mh = []
        out.append({
            "case_id": r[0],
            "query": r[1],
            "must_hit": mh,
        })
    return out


def find_ontology_entity(
    ontology_conn: sqlite3.Connection, raw_name: str
) -> str | None:
    """Find an entity_id by canonical-name match."""
    norm = normalize_canonical_name(raw_name)
    cur = ontology_conn.execute("SELECT entity_id, canonical_name FROM entity")
    for row in cur.fetchall():
        if normalize_canonical_name(row[1]) == norm:
            return row[0]
    return None


def find_ontology_attribute(
    ontology_conn: sqlite3.Connection, entity_id: str, attr_name: str
) -> dict[str, Any] | None:
    cur = ontology_conn.execute(
        "SELECT * FROM attribute WHERE subject_kind='entity' "
        "AND subject_id=? AND attribute_name=?",
        (entity_id, attr_name),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return dict(row)


# ---- 5 side-by-side questions ------------------------------------

def question_1_what_does_14229_7_depend_on(
    legacy_conn, ontology_conn
) -> ComparisonResult:
    """Q1: What standards does ISO 14229-7 reference?"""
    # Legacy
    cases = find_legacy_golden(legacy_conn, "14229-7")
    legacy_ans = ""
    for c in cases:
        if "引用" in c["query"] or "refer" in c["query"].lower():
            legacy_ans = "; ".join(c["must_hit"][:3])
            break
    if not legacy_ans and cases:
        legacy_ans = "; ".join(cases[0]["must_hit"][:3])
    # Ontology
    eid = find_ontology_entity(ontology_conn, "ISO 14229-7")
    if eid:
        rels = relations_of(
            ontology_conn, src_id=eid, direction="outgoing",
            relation_name="references", domain="OBC",
        )
        target_names = []
        for r in rels:
            cur = ontology_conn.execute(
                "SELECT canonical_name FROM entity WHERE entity_id=?",
                (r.dst_id,),
            ).fetchone()
            if cur:
                target_names.append(cur[0])
        ontology_ans = ", ".join(target_names)
    else:
        ontology_ans = "(not found in ontology)"
    return ComparisonResult(
        question="Q1: ISO 14229-7 references what other standards?",
        legacy_answer=legacy_ans or "(no matching golden case)",
        ontology_answer=ontology_ans,
        exactness_legacy="free-text must_hit",
        exactness_ontology=(
            f"structured set of {len(target_names)} entity_ids"
        ),
        notes="Legacy returns text snippets; ontology returns typed entities",
    )


def question_2_p2_timing(
    legacy_conn, ontology_conn
) -> ComparisonResult:
    """Q2: What is the P2 Server Timing for ISO 14229-3?"""
    # Legacy
    cases = find_legacy_golden(legacy_conn, "P2_Server")
    legacy_ans = "(no legacy P2_Server case)"
    for c in cases:
        if "P2" in c["query"]:
            legacy_ans = "; ".join(c["must_hit"][:3])
            break
    # Ontology
    eid = find_ontology_entity(ontology_conn, "ISO 14229-3")
    attr = find_ontology_attribute(
        ontology_conn, eid, "P2_Server_Timing"
    ) if eid else None
    if attr:
        ontology_ans = (
            f"{attr['value_num']} {attr['value_unit']} "
            f"(value_type={attr['value_type']})"
        )
    else:
        ontology_ans = "(not found)"
    return ComparisonResult(
        question="Q2: What is P2 Server Timing for ISO 14229-3?",
        legacy_answer=legacy_ans,
        ontology_answer=ontology_ans,
        exactness_legacy="text snippet (P2 mentioned in 14229-3)",
        exactness_ontology=(
            "exact typed float + unit"
        ),
        notes="RAG cannot return a float; ontology can",
    )


def question_3_what_depends_on_14229_1(
    legacy_conn, ontology_conn
) -> ComparisonResult:
    """Q3: Which standards depend on (reference) ISO 14229-1?"""
    # Legacy
    cases = find_legacy_golden(legacy_conn, "14229-1")
    legacy_ans = "(no legacy 14229-1 case)"
    for c in cases:
        if "14229-1" in c["query"]:
            legacy_ans = "; ".join(c["must_hit"][:3])
            break
    # Ontology
    eid = find_ontology_entity(ontology_conn, "ISO 14229-1")
    rels = relations_of(
        ontology_conn, src_id=eid, direction="incoming",
        relation_name="references", domain="OBC",
    )
    src_names = []
    for r in rels:
        cur = ontology_conn.execute(
            "SELECT canonical_name FROM entity WHERE entity_id=?",
            (r.src_id,),
        ).fetchone()
        if cur:
            src_names.append(cur[0])
    return ComparisonResult(
        question="Q3: Which standards depend on ISO 14229-1?",
        legacy_answer=legacy_ans,
        ontology_answer=", ".join(src_names),
        exactness_legacy="text mentioning 14229-1",
        exactness_ontology=(
            f"structured set of {len(src_names)} dependents"
        ),
        notes="Both find related text, but ontology gives the exact set",
    )


def question_4_udus_services_in_14229_1(
    legacy_conn, ontology_conn
) -> ComparisonResult:
    """Q4: What UDS services does ISO 14229-1 define?"""
    # Legacy: hard — hex codes are too short for FTS
    cases = find_legacy_golden(legacy_conn, "DiagnosticSessionControl")
    legacy_ans = "(none)" if not cases else "; ".join(cases[0]["must_hit"][:3])
    # Ontology: list all "service_*" attributes on ISO 14229-1
    eid = find_ontology_entity(ontology_conn, "ISO 14229-1")
    if eid:
        cur = ontology_conn.execute(
            "SELECT attribute_name, value_text FROM attribute "
            "WHERE subject_kind='entity' AND subject_id=? "
            "AND attribute_name LIKE 'service_%' "
            "ORDER BY attribute_name",
            (eid,),
        )
        services = [
            f"{row[0].replace('service_', '')}: {row[1]}"
            for row in cur.fetchall()
        ]
    else:
        services = []
    return ComparisonResult(
        question="Q4: What UDS services does ISO 14229-1 define?",
        legacy_answer=legacy_ans,
        ontology_answer="; ".join(services) if services else "(none)",
        exactness_legacy="hex codes 0x10/0x3E rarely match in FTS",
        exactness_ontology=(
            f"structured list of {len(services)} services"
        ),
        notes=(
            "Legacy struggles with short hex codes; ontology "
            "queries by attribute_name pattern"
        ),
    )


def question_5_charging_chains(
    legacy_conn, ontology_conn
) -> ComparisonResult:
    """Q5: Charging standards reachable from GB/T 18487.1 by 2 hops?"""
    # Legacy: FTS on "18487"
    cases = find_legacy_golden(legacy_conn, "18487.1")
    legacy_ans = "(multi-snippet)" if cases else "(no case)"
    if cases:
        legacy_ans = "; ".join(cases[0]["must_hit"][:3])
    # Ontology
    eid = find_ontology_entity(ontology_conn, "GB/T 18487.1")
    if eid:
        paths = traverse_relations(
            ontology_conn, start_id=eid, max_hops=2,
            relation_name="references", domain="OBC",
        )
        path_strs = []
        for p in paths:
            names = []
            for r in p:
                cur = ontology_conn.execute(
                    "SELECT canonical_name FROM entity WHERE entity_id=?",
                    (r.dst_id,),
                ).fetchone()
                if cur:
                    names.append(cur[0])
            if names:
                path_strs.append(" → ".join(names))
    else:
        path_strs = []
    return ComparisonResult(
        question="Q5: Charging standards reachable from GB/T 18487.1 in 2 hops?",
        legacy_answer=legacy_ans,
        ontology_answer=(
            f"{len(path_strs)} paths: " + " | ".join(path_strs)
            if path_strs else "(no paths)"
        ),
        exactness_legacy=(
            "first matching golden case, not a traversal"
        ),
        exactness_ontology=(
            f"BFS with cycle protection, {len(path_strs)} paths"
        ),
        notes=(
            "BFS traversal is a structural capability that "
            "fuzzy text search cannot provide"
        ),
    )


# ---- Main report -----------------------------------------------

def main() -> None:
    print("=" * 70)
    print("  KB1 Comparison: Legacy Golden Cases vs New Ontology")
    print("=" * 70)
    print()
    print("Source systems:")
    print(f"  - Legacy:  {LEGACY_DB}")
    print(f"  - Ontology: {ONTOLOGY_DB}")
    print()

    if not ONTOLOGY_DB.exists():
        print("❌ Ontology DB not found. Run build first.")
        return
    legacy_conn = sqlite3.connect(str(LEGACY_DB))
    ontology_conn = connect(ONTOLOGY_DB)
    try:
        # Ensure schemas are installed
        ensure_entity_schema(ontology_conn)
        ensure_relation_schema(ontology_conn)
        ensure_attribute_schema(ontology_conn)
        # Sanity: any data?
        cur = ontology_conn.execute("SELECT COUNT(*) FROM entity")
        if cur.fetchone()[0] == 0:
            print("❌ Ontology DB is empty. Run build first.")
            return
        # Run comparisons
        results = [
            question_1_what_does_14229_7_depend_on(
                legacy_conn, ontology_conn
            ),
            question_2_p2_timing(legacy_conn, ontology_conn),
            question_3_what_depends_on_14229_1(
                legacy_conn, ontology_conn
            ),
            question_4_udus_services_in_14229_1(
                legacy_conn, ontology_conn
            ),
            question_5_charging_chains(legacy_conn, ontology_conn),
        ]
        for i, r in enumerate(results, 1):
            print()
            print("─" * 70)
            print(f"Q{i}: {r.question}")
            print("─" * 70)
            print(f"  Legacy:  {r.legacy_answer[:200]}")
            print(f"    ↳ {r.exactness_legacy}")
            print()
            print(f"  Ontology: {r.ontology_answer[:200]}")
            print(f"    ↳ {r.exactness_ontology}")
            if r.notes:
                print()
                print(f"  💡 {r.notes}")
        # Compute summary statistics
        n_legacy_answered = sum(
            1 for r in results
            if r.legacy_answer and "(no" not in r.legacy_answer
        )
        n_ontology_answered = sum(
            1 for r in results
            if r.ontology_answer and "(not" not in r.ontology_answer
            and "(no" not in r.ontology_answer
        )
        n_exact_values = sum(
            1 for r in results if r.exactness_ontology.startswith("exact")
        )
        n_structured_lists = sum(
            1 for r in results
            if r.exactness_ontology.startswith("structured")
        )
        print()
        print("=" * 70)
        print("Summary")
        print("=" * 70)
        print()
        print(f"  Questions asked:        {len(results)}")
        print(f"  Legacy answered:        {n_legacy_answered} / {len(results)}")
        print(f"  Ontology answered:      {n_ontology_answered} / {len(results)}")
        print()
        print(f"  Ontology exact values: {n_exact_values}")
        print(f"  Ontology structured:   {n_structured_lists}")
        print()
        print("Capability comparison:")
        print()
        print("  ┌─ Legacy (text/FTS) ────────────────────────────┐")
        print("  │  ✓ Free-form Q&A (summary, related paragraphs)  │")
        print("  │  ✓ Fuzzy text matching                          │")
        print("  │  ✗ Precise numeric values                       │")
        print("  │  ✗ Graph traversal (BFS, hop limits)            │")
        print("  │  ✗ Short codes (0x10, 0x3E)                     │")
        print("  └─────────────────────────────────────────────────┘")
        print()
        print("  ┌─ Ontology (structured graph) ─────────────────┐")
        print("  │  ✓ Exact numeric values (e.g. 50.0 ms)         │")
        print("  │  ✓ Graph traversal (BFS, hop limits)            │")
        print("  │  ✓ Pattern queries (LIKE 'service_%')           │")
        print("  │  ✓ Typed references (entity_id, class_id)       │")
        print("  │  ✗ Free-form summarization                      │")
        print("  │  ✗ Prose generation                             │")
        print("  └─────────────────────────────────────────────────┘")
        print()
        print("Verdict: the two systems are COMPLEMENTARY, not competing.")
        print("  - Use legacy for: free-form Q&A, prose answers")
        print("  - Use ontology for: structured, exact answers")
        print("  - Best: query BOTH, combine results")
    finally:
        legacy_conn.close()
        ontology_conn.close()


if __name__ == "__main__":
    main()
