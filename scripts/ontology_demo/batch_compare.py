"""Batch comparison: 30 questions across multiple categories.

We pick questions from the legacy golden_cases table that map
cleanly onto ontology queries:

- Definition questions about a specific standard (ontology:
  get the entity's title attribute)
- Reference questions (ontology: outgoing/incoming relations)
- Parameter questions (ontology: numeric attribute query)
- Service-list questions (ontology: LIKE 'service_%')
- Existence questions (ontology: yes/no via entity lookup)

We score each on:
  1. coverage  - did the system find an answer at all?
  2. exactness - was it a typed value (ontology) or text
                (legacy)?

Output: a JSON + a summary table.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
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


# ---- Question selectors -------------------------------------------

# Each tuple: (selector_id, ontology_query_kind, golden_filter,
#              legacy_answer_from_must_hit, ontology_callable)
# selector_id: unique id for the question
# ontology_query_kind: which ontology API to use
# golden_filter: SQL filter to pick the golden case
# legacy_answer: how to extract a legacy answer from the must_hit list
# ontology_callable: function that runs the ontology query

@dataclass
class Question:
    id: str
    category: str
    query_template: str
    legacy_filter_sql: str
    legacy_extract: str
    ontology_kind: str
    ontology_args: dict[str, Any] = field(default_factory=dict)


QUESTIONS: list[Question] = [
    # Definition questions (5)
    Question(
        id="def-18487-1",
        category="definition",
        query_template="在 GB/T 18487.1—2023 中，<X> 的定义是什么？",
        legacy_filter_sql="""
            query LIKE '%18487.1%' AND query LIKE '%定义%'
        """,
        legacy_extract="first_must_hit",
        ontology_kind="get_title_attr",
        ontology_args={"entity_name": "GB/T 18487.1"},
    ),
    Question(
        id="def-18487-4-v2l",
        category="definition",
        query_template="什么是 V2L (Vehicle-to-Load)？",
        legacy_filter_sql="""
            query LIKE '%V2L%' OR query LIKE '%对外放电%' OR query LIKE '%18487.4%'
        """,
        legacy_extract="first_must_hit",
        ontology_kind="get_title_attr",
        ontology_args={"entity_name": "GB/T 18487.4"},
    ),
    Question(
        id="def-14229-1",
        category="definition",
        query_template="ISO 14229-1 是什么标准？",
        legacy_filter_sql="query LIKE '%14229-1%'",
        legacy_extract="first_must_hit",
        ontology_kind="get_title_attr",
        ontology_args={"entity_name": "ISO 14229-1"},
    ),
    Question(
        id="def-1036",
        category="definition",
        query_template="QC/T 1036 是什么？",
        legacy_filter_sql="query LIKE '%1036%'",
        legacy_extract="first_must_hit",
        ontology_kind="get_title_attr",
        ontology_args={"entity_name": "QC/T 1036"},
    ),
    Question(
        id="def-15118",
        category="definition",
        query_template="ISO 15118 是什么？",
        legacy_filter_sql="query LIKE '%15118%'",
        legacy_extract="first_must_hit",
        ontology_kind="get_title_attr",
        ontology_args={"entity_name": "ISO 15118"},
    ),

    # Reference questions (5)
    Question(
        id="ref-14229-7-out",
        category="reference",
        query_template="ISO 14229-7 引用了哪些标准？",
        legacy_filter_sql="query LIKE '%14229-7%' AND query LIKE '%引用%'",
        legacy_extract="first_must_hit",
        ontology_kind="outgoing_refs",
        ontology_args={"entity_name": "ISO 14229-7"},
    ),
    Question(
        id="ref-14229-1-in",
        category="reference",
        query_template="哪些标准引用了 ISO 14229-1？",
        legacy_filter_sql="query LIKE '%14229-1%' AND (query LIKE '%引用%' OR query LIKE '%参考%')",
        legacy_extract="first_must_hit",
        ontology_kind="incoming_refs",
        ontology_args={"entity_name": "ISO 14229-1"},
    ),
    Question(
        id="ref-18487-1-out",
        category="reference",
        query_template="GB/T 18487.1 引用了哪些充电相关标准？",
        legacy_filter_sql="query LIKE '%18487.1%' AND query LIKE '%引用%'",
        legacy_extract="first_must_hit",
        ontology_kind="outgoing_refs",
        ontology_args={"entity_name": "GB/T 18487.1"},
    ),
    Question(
        id="ref-14229-3-out",
        category="reference",
        query_template="ISO 14229-3 引用了哪些标准？",
        legacy_filter_sql="query LIKE '%14229-3%' AND query LIKE '%引用%'",
        legacy_extract="first_must_hit",
        ontology_kind="outgoing_refs",
        ontology_args={"entity_name": "ISO 14229-3"},
    ),
    Question(
        id="ref-18487-4-out",
        category="reference",
        query_template="GB/T 18487.4 引用了哪些标准？",
        legacy_filter_sql="query LIKE '%18487.4%' AND query LIKE '%引用%'",
        legacy_extract="first_must_hit",
        ontology_kind="outgoing_refs",
        ontology_args={"entity_name": "GB/T 18487.4"},
    ),

    # Parameter questions (5)
    Question(
        id="param-p2-14229-3",
        category="parameter",
        query_template="ISO 14229-3 中 P2 Server Timing 是多少？",
        legacy_filter_sql="query LIKE '%14229-3%' AND (query LIKE '%P2%' OR query LIKE '%timing%')",
        legacy_extract="first_must_hit",
        ontology_kind="get_attribute",
        ontology_args={
            "entity_name": "ISO 14229-3",
            "attribute_name": "P2_Server_Timing",
        },
    ),
    Question(
        id="param-s3-14229-3",
        category="parameter",
        query_template="ISO 14229-3 中 S3 Server Timing 是多少？",
        legacy_filter_sql="query LIKE '%14229-3%' AND (query LIKE '%S3%' OR query LIKE '%timing%')",
        legacy_extract="first_must_hit",
        ontology_kind="get_attribute",
        ontology_args={
            "entity_name": "ISO 14229-3",
            "attribute_name": "S3_Server_Timing",
        },
    ),
    Question(
        id="param-volt-18487-1",
        category="parameter",
        query_template="GB/T 18487.1 中额定交流电压是多少？",
        legacy_filter_sql="query LIKE '%18487.1%' AND query LIKE '%电压%'",
        legacy_extract="first_must_hit",
        ontology_kind="get_attribute",
        ontology_args={
            "entity_name": "GB/T 18487.1",
            "attribute_name": "rated_voltage_AC",
        },
    ),
    Question(
        id="param-curr-18487-1",
        category="parameter",
        query_template="GB/T 18487.1 中额定交流电流是多少？",
        legacy_filter_sql="query LIKE '%18487.1%' AND query LIKE '%电流%'",
        legacy_extract="first_must_hit",
        ontology_kind="get_attribute",
        ontology_args={
            "entity_name": "GB/T 18487.1",
            "attribute_name": "rated_current_AC",
        },
    ),
    Question(
        id="param-v2l-volt",
        category="parameter",
        query_template="GB/T 18487.4 V2L 最大输出电压？",
        legacy_filter_sql="query LIKE '%18487.4%' AND (query LIKE '%V2L%' OR query LIKE '%输出%' OR query LIKE '%电压%')",
        legacy_extract="first_must_hit",
        ontology_kind="get_attribute",
        ontology_args={
            "entity_name": "GB/T 18487.4",
            "attribute_name": "max_output_voltage",
        },
    ),

    # Service list questions (5)
    Question(
        id="svc-14229-1",
        category="service",
        query_template="ISO 14229-1 定义了哪些 UDS 服务？",
        legacy_filter_sql="query LIKE '%14229-1%' AND (query LIKE '%服务%' OR query LIKE '%0x%')",
        legacy_extract="first_must_hit",
        ontology_kind="list_services",
        ontology_args={"entity_name": "ISO 14229-1"},
    ),
    Question(
        id="svc-14229-2",
        category="service",
        query_template="ISO 14229-2 定义了哪些 session 服务？",
        legacy_filter_sql="query LIKE '%14229-2%'",
        legacy_extract="first_must_hit",
        ontology_kind="list_services",
        ontology_args={"entity_name": "ISO 14229-2"},
    ),
    Question(
        id="svc-14229-7",
        category="service",
        query_template="ISO 14229-7 定义了哪些 UDS 服务？",
        legacy_filter_sql="query LIKE '%14229-7%'",
        legacy_extract="first_must_hit",
        ontology_kind="list_services",
        ontology_args={"entity_name": "ISO 14229-7"},
    ),
    Question(
        id="svc-14229-3",
        category="service",
        query_template="ISO 14229-3 中实现了哪些 UDS 服务？",
        legacy_filter_sql="query LIKE '%14229-3%' AND query LIKE '%服务%'",
        legacy_extract="first_must_hit",
        ontology_kind="list_services",
        ontology_args={"entity_name": "ISO 14229-3"},
    ),
    Question(
        id="svc-18487-1",
        category="service",
        query_template="GB/T 18487.1 中定义了哪些充电模式？",
        legacy_filter_sql="query LIKE '%18487.1%' AND (query LIKE '%模式%' OR query LIKE '%mode%')",
        legacy_extract="first_must_hit",
        ontology_kind="list_services",
        ontology_args={"entity_name": "GB/T 18487.1"},
    ),

    # Traversal questions (5)
    Question(
        id="trav-18487-1-1hop",
        category="traversal",
        query_template="GB/T 18487.1 直接引用的标准？",
        legacy_filter_sql="query LIKE '%18487.1%'",
        legacy_extract="first_must_hit",
        ontology_kind="outgoing_refs",
        ontology_args={"entity_name": "GB/T 18487.1"},
    ),
    Question(
        id="trav-18487-1-2hop",
        category="traversal",
        query_template="从 GB/T 18487.1 出发 2 跳可达的充电标准？",
        legacy_filter_sql="query LIKE '%18487.1%'",
        legacy_extract="first_must_hit",
        ontology_kind="bfs_2hop",
        ontology_args={"entity_name": "GB/T 18487.1"},
    ),
    Question(
        id="trav-14229-7-2hop",
        category="traversal",
        query_template="从 ISO 14229-7 出发 2 跳可达的标准？",
        legacy_filter_sql="query LIKE '%14229-7%'",
        legacy_extract="first_must_hit",
        ontology_kind="bfs_2hop",
        ontology_args={"entity_name": "ISO 14229-7"},
    ),
    Question(
        id="trav-14229-3-2hop",
        category="traversal",
        query_template="从 ISO 14229-3 出发 2 跳可达的标准？",
        legacy_filter_sql="query LIKE '%14229-3%'",
        legacy_extract="first_must_hit",
        ontology_kind="bfs_2hop",
        ontology_args={"entity_name": "ISO 14229-3"},
    ),
    Question(
        id="trav-14229-1-2hop",
        category="traversal",
        query_template="从 ISO 14229-1 出发 2 跳可达的标准？",
        legacy_filter_sql="query LIKE '%14229-1%'",
        legacy_extract="first_must_hit",
        ontology_kind="bfs_2hop",
        ontology_args={"entity_name": "ISO 14229-1"},
    ),
]


# ---- Answer extractors -------------------------------------------

def find_golden_case(
    legacy_conn, filter_sql: str
) -> dict[str, Any] | None:
    cur = legacy_conn.execute(
        f"SELECT case_id, query, must_hit_json FROM golden_cases "
        f"WHERE {filter_sql} LIMIT 1"
    )
    row = cur.fetchone()
    if row is None:
        return None
    try:
        mh = json.loads(row[2]) if row[2] else []
    except json.JSONDecodeError:
        mh = []
    return {"case_id": row[0], "query": row[1], "must_hit": mh}


def find_ontology_entity(conn, raw_name: str) -> str | None:
    norm = normalize_canonical_name(raw_name)
    for row in conn.execute(
        "SELECT entity_id, canonical_name FROM entity"
    ):
        if normalize_canonical_name(row[1]) == norm:
            return row[0]
    return None


# ---- Ontology query dispatcher ------------------------------------

def run_ontology_query(
    ontology_conn, kind: str, args: dict[str, Any]
) -> tuple[Any, str]:
    """Return (answer, exactness_label)."""
    if kind == "get_title_attr":
        eid = find_ontology_entity(ontology_conn, args["entity_name"])
        if eid is None:
            return None, "entity_not_found"
        row = ontology_conn.execute(
            "SELECT value_text FROM attribute "
            "WHERE subject_kind='entity' AND subject_id=? "
            "AND attribute_name='title'",
            (eid,),
        ).fetchone()
        if row is None:
            return None, "no_title_attribute"
        return row[0], "structured_string"

    if kind == "outgoing_refs":
        eid = find_ontology_entity(ontology_conn, args["entity_name"])
        if eid is None:
            return None, "entity_not_found"
        rels = relations_of(
            ontology_conn, src_id=eid, direction="outgoing",
            relation_name="references", domain="OBC",
        )
        names = []
        for r in rels:
            cur = ontology_conn.execute(
                "SELECT canonical_name FROM entity WHERE entity_id=?",
                (r.dst_id,),
            ).fetchone()
            if cur:
                names.append(cur[0])
        return names, f"structured_set({len(names)})"

    if kind == "incoming_refs":
        eid = find_ontology_entity(ontology_conn, args["entity_name"])
        if eid is None:
            return None, "entity_not_found"
        rels = relations_of(
            ontology_conn, src_id=eid, direction="incoming",
            relation_name="references", domain="OBC",
        )
        names = []
        for r in rels:
            cur = ontology_conn.execute(
                "SELECT canonical_name FROM entity WHERE entity_id=?",
                (r.src_id,),
            ).fetchone()
            if cur:
                names.append(cur[0])
        return names, f"structured_set({len(names)})"

    if kind == "get_attribute":
        eid = find_ontology_entity(ontology_conn, args["entity_name"])
        if eid is None:
            return None, "entity_not_found"
        row = ontology_conn.execute(
            "SELECT * FROM attribute "
            "WHERE subject_kind='entity' AND subject_id=? "
            "AND attribute_name=?",
            (eid, args["attribute_name"]),
        ).fetchone()
        if row is None:
            return None, "no_attribute"
        d = dict(row)
        if d["value_num"] is not None and d["value_unit"]:
            return (
                f"{d['value_num']} {d['value_unit']}",
                "typed_value",
            )
        return d.get("value_text"), "raw_string"

    if kind == "list_services":
        eid = find_ontology_entity(ontology_conn, args["entity_name"])
        if eid is None:
            return None, "entity_not_found"
        cur = ontology_conn.execute(
            "SELECT attribute_name, value_text FROM attribute "
            "WHERE subject_kind='entity' AND subject_id=? "
            "AND attribute_name LIKE 'service_%' "
            "ORDER BY attribute_name",
            (eid,),
        )
        services = [
            f"{row[0].replace('service_', '')}: {row[1]}"
            for row in cur
        ]
        return services, f"structured_list({len(services)})"

    if kind == "bfs_2hop":
        eid = find_ontology_entity(ontology_conn, args["entity_name"])
        if eid is None:
            return None, "entity_not_found"
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
        return path_strs, f"bfs_paths({len(path_strs)})"

    return None, f"unknown_kind({kind})"


# ---- Comparison logic ---------------------------------------------

def compare_one(
    q: Question, legacy_conn, ontology_conn
) -> dict[str, Any]:
    # Legacy
    case = find_golden_case(legacy_conn, q.legacy_filter_sql)
    if case is None:
        legacy_answer = None
        legacy_exactness = "no_golden_case"
    else:
        mh = case["must_hit"]
        if q.legacy_extract == "first_must_hit":
            legacy_answer = mh[0] if mh else None
        else:
            legacy_answer = mh[0] if mh else None
        legacy_exactness = "free_text_must_hit"

    # Ontology
    onto_answer, onto_exactness = run_ontology_query(
        ontology_conn, q.ontology_kind, q.ontology_args
    )

    # Score
    legacy_answered = legacy_answer is not None
    onto_answered = onto_answer is not None and onto_answer != []
    onto_exact = onto_exactness.startswith(
        ("typed_value", "structured_", "bfs_")
    )

    return {
        "id": q.id,
        "category": q.category,
        "query": q.query_template,
        "legacy_answer": (
            (legacy_answer[:100] + "...")
            if legacy_answer and len(legacy_answer) > 100
            else legacy_answer
        ),
        "legacy_exactness": legacy_exactness,
        "legacy_answered": legacy_answered,
        "ontology_answer": onto_answer,
        "ontology_exactness": onto_exactness,
        "ontology_answered": onto_answered,
        "ontology_exact": onto_exact,
    }


# ---- Main report -----------------------------------------------

def main() -> None:
    print("=" * 70)
    print("  KB1 Batch Comparison: Legacy Golden Cases vs New Ontology")
    print(f"  Questions: {len(QUESTIONS)}")
    print("=" * 70)
    print()
    if not ONTOLOGY_DB.exists():
        print("❌ Ontology DB not found. Run build first.")
        return
    legacy_conn = sqlite3.connect(str(LEGACY_DB))
    ontology_conn = connect(ONTOLOGY_DB)
    try:
        # Ensure schemas
        ensure_entity_schema(ontology_conn)
        ensure_relation_schema(ontology_conn)
        ensure_attribute_schema(ontology_conn)
        # Sanity
        if ontology_conn.execute(
            "SELECT COUNT(*) FROM entity"
        ).fetchone()[0] == 0:
            print("❌ Ontology DB is empty. Run build first.")
            return
        # Run all
        results = [
            compare_one(q, legacy_conn, ontology_conn) for q in QUESTIONS
        ]
        # Per-category summary
        cats: dict[str, dict[str, int]] = {}
        for r in results:
            c = r["category"]
            if c not in cats:
                cats[c] = {"n": 0, "legacy_ans": 0, "onto_ans": 0,
                           "onto_exact": 0}
            cats[c]["n"] += 1
            if r["legacy_answered"]:
                cats[c]["legacy_ans"] += 1
            if r["ontology_answered"]:
                cats[c]["onto_ans"] += 1
            if r["ontology_exact"]:
                cats[c]["onto_exact"] += 1
        # Print table
        print(f"{'Cat':<13} {'N':>3}  {'Legacy OK':>10}  "
              f"{'Ontology OK':>11}  {'Exact':>6}")
        print("-" * 70)
        for cat, stats in cats.items():
            print(f"{cat:<13} {stats['n']:>3}  "
                  f"{stats['legacy_ans']:>4}/{stats['n']:<5}  "
                  f"{stats['onto_ans']:>4}/{stats['n']:<5}  "
                  f"{stats['onto_exact']:>3}/{stats['n']}")
        # Totals
        n_total = len(results)
        n_legacy = sum(1 for r in results if r["legacy_answered"])
        n_onto = sum(1 for r in results if r["ontology_answered"])
        n_exact = sum(1 for r in results if r["ontology_exact"])
        print("-" * 70)
        print(f"{'TOTAL':<13} {n_total:>3}  "
              f"{n_legacy:>4}/{n_total:<5}  "
              f"{n_onto:>4}/{n_total:<5}  "
              f"{n_exact:>3}/{n_total}")
        # Per-question detail
        print()
        print("=" * 70)
        print("Per-question results")
        print("=" * 70)
        for r in results:
            mark = "✓" if r["ontology_answered"] else "✗"
            legacy_mark = "✓" if r["legacy_answered"] else "·"
            print()
            print(f"  [{mark}] {r['id']}  ({r['category']})")
            print(f"      Q: {r['query']}")
            print(f"      Legacy  [{legacy_mark}]: {r['legacy_answer']}")
            ans = r["ontology_answer"]
            if isinstance(ans, list):
                ans_str = ", ".join(ans[:5])
                if len(ans) > 5:
                    ans_str += f", ... ({len(ans)} total)"
            else:
                ans_str = str(ans) if ans else "(empty)"
            print(f"      Ontology [{mark}]: {ans_str}")
            print(f"      Type: legacy={r['legacy_exactness']}, "
                  f"ontology={r['ontology_exactness']}")
        # Save JSON
        out_path = WORKSPACE / "ontology" / "batch_comparison.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump({
                "total": n_total,
                "legacy_answered": n_legacy,
                "ontology_answered": n_onto,
                "ontology_exact": n_exact,
                "categories": cats,
                "results": results,
            }, f, ensure_ascii=False, indent=2)
        print()
        print("=" * 70)
        print(f"Full results saved to: {out_path}")
        print("=" * 70)
    finally:
        legacy_conn.close()
        ontology_conn.close()


if __name__ == "__main__":
    main()
