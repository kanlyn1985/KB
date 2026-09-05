# -*- coding: utf-8 -*-
"""V0.1 migration tool（任务书 §20）：默认 DRY-RUN；--apply 才写库。"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_kb.evidence_core.graph import GraphProjection  # noqa: E402
from agent_kb.evidence_core.ids import migration_assertion_id, mint_id  # noqa: E402
from agent_kb.evidence_core.models import KnowledgeAssertion  # noqa: E402
from agent_kb.storage.migrations import SchemaMigrator  # noqa: E402

POLICY = "policy:v0.1"


def _canonical_for_edge(row: sqlite3.Row, seq: int, batch: int) -> KnowledgeAssertion:
    edge_id = row["edge_id"]
    return KnowledgeAssertion(
        assertion_id=migration_assertion_id(batch, seq),
        subject_ref=f"entity:{row['source_object_id']}",
        predicate_ref=f"relation:{row['relation_type']}",
        object={"kind": "entity_ref", "entity_id": f"entity:{row['target_object_id']}"},
        assertion_type="extracted",
        status="candidate",  # PATH A：candidate 合法（legacy 登记语义）
        confidence=row["confidence"],
        evidence_refs=list(json.loads(row["evidence_ids_json"] or "[]"))[:1],
        provenance_ref=None,
        ontology_scope=f"ontology:{row['domain']}:0.6",
    )


def migrate(db_path: Path, *, apply: bool, batch_size: int = 100, resume: bool = False) -> dict:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    report: dict = {"schema": None, "edges_total": 0, "backfilled": 0,
                    "assertions_created": 0, "skipped_resume": 0, "errors": []}

    # schema（迁移 10：幂等，IF NOT EXISTS / ALTER 捕获重复）
    con.execute("BEGIN")
    try:
        migrator = SchemaMigrator(con)
        applied = migrator.migrate()
        con.commit()
        report["schema"] = f"applied={applied}"
    except sqlite3.OperationalError as exc:
        con.rollback()
        if "duplicate column" in str(exc).lower():
            con.execute("COMMIT") if not con.in_transaction else None
            report["schema"] = "graph_edges.assertion_ref already present (idempotent skip)"
        else:
            raise

    edges = con.execute(
        "SELECT rowid, * FROM graph_edges WHERE assertion_ref IS NULL ORDER BY rowid").fetchall()
    report["edges_total"] = len(edges)
    if not apply:
        con.close()
        report["mode"] = "DRY-RUN（未写库）"
        report["would_create_assertions"] = len(edges)
        return report

    # PATH A backfill（批量事务 + resume）
    proj = GraphProjection(con)
    prov_id = mint_id("provenance")
    con.execute(
        "INSERT INTO akb_provenance (provenance_id, actor_id, actor_kind, activity,"
        " policy_version, occurred_at, inputs_json, metadata_json)"
        " VALUES (?, 'system:migrator', 'system', 'migrate', ?,"
        " strftime('%Y-%m-%dT%H:%M:%SZ','now'), '[]', '{}')", (prov_id, POLICY))
    done_rows = set()
    if resume:
        done_rows = {r[0] for r in con.execute(
            "SELECT rowid FROM graph_edges WHERE assertion_ref IS NOT NULL")}
    seq = 0
    batch = 1
    in_txn = 0
    for row in edges:
        if resume and row["rowid"] in done_rows:
            report["skipped_resume"] += 1
            continue
        seq += 1
        assertion = _canonical_for_edge(row, seq, batch)
        d = assertion.to_row()
        d["provenance_ref"] = prov_id
        con.execute(
            "INSERT OR IGNORE INTO akb_assertions (assertion_id, subject_ref, predicate_ref,"
            " object_kind, object_value, object_datatype, object_unit, object_entity_ref,"
            " assertion_type, status, confidence, evidence_refs_json, source_unit_refs_json,"
            " provenance_ref, temporal_scope_json, ontology_scope, derivation_json, canonical_json)"
            " VALUES (:assertion_id, :subject_ref, :predicate_ref, :object_kind, :object_value,"
            " :object_datatype, :object_unit, :object_entity_ref, :assertion_type, :status,"
            " :confidence, :evidence_refs_json, :source_unit_refs_json, :provenance_ref,"
            " :temporal_scope_json, :ontology_scope, :derivation_json, :canonical_json)", d)
        if con.total_changes and con.execute(
            "SELECT changes()").fetchone()[0]:
            report["assertions_created"] += 1
        proj.backfill_legacy_edge(edge_rowid=row["rowid"], assertion_id=assertion.assertion_id)
        report["backfilled"] += 1
        in_txn += 1
        if in_txn >= batch_size:
            con.commit()
            in_txn = 0
            batch += 1
    if in_txn:
        con.commit()
    integrity = proj.verify_integrity()
    report["integrity"] = integrity
    con.close()
    return report


def verify(db_path: Path) -> dict:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    proj = GraphProjection(con)
    integrity = proj.verify_integrity()
    inv1 = con.execute(
        "SELECT COUNT(*) FROM akb_assertions WHERE status IN ('validated','asserted','disputed')"
        " AND json_array_length(evidence_refs_json) = 0").fetchone()[0]
    inv2 = con.execute(
        "SELECT COUNT(*) FROM akb_assertions WHERE assertion_type='inferred'"
        " AND derivation_json IS NULL").fetchone()[0]
    con.close()
    return {"integrity": integrity, "INV-001 violations": inv1, "INV-002 violations": inv2,
            "pass": integrity["broken_refs"] == 0 and inv1 == 0 and inv2 == 0}


def main() -> int:
    ap = argparse.ArgumentParser(description="V0.1 Evidence Core migration (default DRY-RUN)")
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--apply", action="store_true", help="真实写库（默认 dry-run）")
    ap.add_argument("--batch-size", type=int, default=100)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--verify", action="store_true", help="只做完整性巡检")
    args = ap.parse_args()
    if args.verify:
        out = verify(args.db)
    else:
        out = migrate(args.db, apply=args.apply, batch_size=args.batch_size, resume=args.resume)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out.get("pass", True) else 1


if __name__ == "__main__":
    sys.exit(main())