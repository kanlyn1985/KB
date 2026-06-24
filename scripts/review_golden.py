#!/usr/bin/env python3
"""Interactive review tool for ontology golden test cases.

For each golden case, shows the query, expected answer, and source context
(wiki_chunk body). Reviewer marks: [v]erified, [c]orrected, [r]ejected, [s]kip.

Usage:
  python scripts/review_golden.py --doc-id DOC-000003
  python scripts/review_golden.py --all --limit 20
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_DB = ROOT / "knowledge_base" / "ontology" / "ontology.db"
KNOWLEDGE_DB = ROOT / "knowledge_base" / "db" / "knowledge.db"
REVIEW_FILE = ROOT / "output" / "golden_review.json"


def _load_chunk_map(kb_conn: sqlite3.Connection) -> dict[str, dict]:
    """Build chunk_id → {section_title, body_text} map."""
    rows = kb_conn.execute(
        "SELECT chunk_id, section_title, body_text FROM wiki_chunks"
    ).fetchall()
    return {r["chunk_id"]: dict(r) for r in rows}


def _load_review_state() -> dict[str, str]:
    """Return {case_id: verdict} from review file."""
    if not REVIEW_FILE.exists():
        return {}
    with open(REVIEW_FILE, "r") as f:
        return json.load(f)


def _save_review_state(state: dict[str, str]) -> None:
    REVIEW_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REVIEW_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def review(args):
    ont_conn = sqlite3.connect(str(ONTOLOGY_DB))
    ont_conn.row_factory = sqlite3.Row
    kb_conn = sqlite3.connect(str(KNOWLEDGE_DB))
    kb_conn.row_factory = sqlite3.Row

    chunk_map = _load_chunk_map(kb_conn)
    review_state = _load_review_state()

    # Build query
    filters = ["status = 'active'"]
    params = []
    if args.doc_id:
        filters.append("doc_id = ?")
        params.append(args.doc_id)

    where = " AND ".join(filters)
    rows = ont_conn.execute(
        f"SELECT * FROM ontology_golden WHERE {where} ORDER BY doc_id, case_id",
        params,
    ).fetchall()

    if args.limit:
        rows = rows[:args.limit]

    total = len(rows)
    reviewed = sum(1 for r in rows if r["case_id"] in review_state)
    verified = sum(1 for r in rows if review_state.get(r["case_id"]) == "verified")
    corrected = sum(1 for r in rows if review_state.get(r["case_id"]) == "corrected")
    rejected = sum(1 for r in rows if review_state.get(r["case_id"]) == "rejected")

    print(f"Cases to review: {total}")
    print(f"Already reviewed: {reviewed} (verified={verified}, corrected={corrected}, rejected={rejected})")
    print(f"Remaining: {total - reviewed}")
    print()
    print("Actions: [v] verified  [c] corrected  [r] rejected  [s] skip  [q] quit")
    print()

    pending = [r for r in rows if r["case_id"] not in review_state]
    if not pending:
        print("All cases reviewed!")
        return

    import readline  # enables line editing

    for i, row in enumerate(pending):
        cid = row["case_id"]
        print(f"\n--- [{i+1}/{len(pending)}] ---")
        print(f"  Doc:      {row['doc_id']}")
        print(f"  Category: {row['category']}")
        print(f"  Entity:   {row.get('entity', '') or '-'}")
        print(f"  Query:    {row['query']}")
        expected = (row.get("expected_json") or "").strip('"')
        print(f"  Expected: {expected}")

        # Show source context if available
        # The chunk_id is embedded in the expected_json for traceability
        # We don't have chunk_id in ontology_golden schema yet, so skip for now

        while True:
            action = input("  [v/c/r/s/q]: ").strip().lower()
            if action == "v":
                review_state[cid] = "verified"
                verified += 1
                break
            elif action == "c":
                new_expected = input("  Corrected answer: ").strip()
                if new_expected:
                    ont_conn.execute(
                        "UPDATE ontology_golden SET expected_json = ?, status = 'reviewed' WHERE case_id = ?",
                        (json.dumps(new_expected), cid),
                    )
                    ont_conn.commit()
                review_state[cid] = "corrected"
                corrected += 1
                break
            elif action == "r":
                reason = input("  Rejection reason (optional): ").strip() or "rejected"
                ont_conn.execute(
                    "UPDATE ontology_golden SET status = 'rejected' WHERE case_id = ?",
                    (cid,),
                )
                ont_conn.commit()
                review_state[cid] = f"rejected: {reason}"
                rejected += 1
                break
            elif action == "s":
                break
            elif action == "q":
                _save_review_state(review_state)
                print(f"\nSaved. {len(review_state)} cases reviewed.")
                return
            else:
                print("  Invalid. Use v/c/r/s/q")

        if (i + 1) % 10 == 0:
            _save_review_state(review_state)
            print(f"\n  [Auto-saved: {verified}v/{corrected}c/{rejected}r]")

    _save_review_state(review_state)
    print(f"\nDone. {verified} verified, {corrected} corrected, {rejected} rejected.")
    print(f"Review state saved to {REVIEW_FILE}")

    ont_conn.close()
    kb_conn.close()


def summary(args):
    """Show review progress summary."""
    review_state = _load_review_state()
    ont_conn = sqlite3.connect(str(ONTOLOGY_DB))
    ont_conn.row_factory = sqlite3.Row

    total = ont_conn.execute(
        "SELECT COUNT(*) FROM ontology_golden WHERE status = 'active'"
    ).fetchone()[0]
    reviewed = len(review_state)
    verified = sum(1 for v in review_state.values() if v == "verified")
    corrected = sum(1 for v in review_state.values() if v == "corrected")
    rejected = sum(1 for v in review_state.values() if v.startswith("rejected"))

    print(f"Total active cases: {total}")
    print(f"Reviewed: {reviewed} ({100*reviewed/max(total,1):.0f}%)")
    print(f"  Verified:  {verified}")
    print(f"  Corrected: {corrected}")
    print(f"  Rejected:  {rejected}")
    print(f"Remaining:   {total - reviewed}")

    ont_conn.close()


def main():
    parser = argparse.ArgumentParser(description="Review ontology golden test cases")
    sub = parser.add_subparsers(dest="cmd")

    r = sub.add_parser("review", help="Review golden cases")
    r.add_argument("--doc-id", help="Single document")
    r.add_argument("--limit", type=int, default=None)
    r.add_argument("--all", action="store_true")

    s = sub.add_parser("summary", help="Show review progress")

    args = parser.parse_args()

    if args.cmd == "review":
        review(args)
    elif args.cmd == "summary":
        summary(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
