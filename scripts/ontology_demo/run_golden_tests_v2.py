"""Run golden tests using new architecture.

Each golden case: read query + category + entity → call handlers directly → check answer.
No LLM routing needed — golden cases have pre-extracted category/entity.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from kb1_ontology.handlers import (
    handle_definition, handle_parameter, handle_reference,
    handle_service, handle_traversal,
)
from kb1_ontology.types import RouteResult, HandlerResult
from kb1_ontology.db import connect, default_db_path

_HANDLERS = {
    "definition": handle_definition,
    "parameter": handle_parameter,
    "reference": handle_reference,
    "service": handle_service,
    "traversal": handle_traversal,
}


def _check_result(result: HandlerResult) -> bool:
    """Check if handler returned a meaningful result."""
    if result.data is None:
        return False
    if result.data_type == "list" and isinstance(result.data, list):
        return len(result.data) > 0
    if result.data_type == "path_list" and isinstance(result.data, list):
        return len(result.data) > 0
    if result.data_type == "dict" and isinstance(result.data, dict):
        return True
    if result.data_type == "value":
        return result.data is not None
    return bool(result.data)


def run_golden_tests(
    workspace_root: Path,
    ontology_db_path: Path,
    doc_id: str | None = None,
) -> dict[str, Any]:
    """Run all ontology golden tests."""
    ont_conn = sqlite3.connect(str(ontology_db_path))
    ont_conn.row_factory = sqlite3.Row

    if doc_id:
        rows = ont_conn.execute(
            "SELECT * FROM ontology_golden WHERE doc_id = ? AND status = 'active'",
            (doc_id,),
        ).fetchall()
    else:
        rows = ont_conn.execute(
            "SELECT * FROM ontology_golden WHERE status = 'active'"
        ).fetchall()
    ont_conn.close()

    if not rows:
        return {"error": "No golden cases found"}

    conn = connect(default_db_path(workspace_root))

    results = {
        "total": len(rows),
        "passed": 0,
        "failed": 0,
        "by_category": {},
        "by_doc": {},
        "failures": [],
    }

    for i, row in enumerate(rows):
        case_id = row["case_id"]
        query = row["query"]
        category = row["category"]
        doc = row["doc_id"]
        entity = row["entity"] if "entity" in row.keys() else None

        handler = _HANDLERS.get(category)
        if handler is None:
            results["failed"] += 1
            continue

        route = RouteResult(category=category, entity=entity, target=None)
        result = handler(conn, route, query)
        passed = _check_result(result)

        if passed:
            results["passed"] += 1
        else:
            results["failed"] += 1
            results["failures"].append({
                "case_id": case_id, "doc_id": doc, "query": query,
                "category": category, "entity": entity,
                "data_type": result.data_type, "source": result.source,
            })

        # By category
        if category not in results["by_category"]:
            results["by_category"][category] = {"total": 0, "passed": 0}
        results["by_category"][category]["total"] += 1
        if passed:
            results["by_category"][category]["passed"] += 1

        # By doc
        if doc not in results["by_doc"]:
            results["by_doc"][doc] = {"total": 0, "passed": 0}
        results["by_doc"][doc]["total"] += 1
        if passed:
            results["by_doc"][doc]["passed"] += 1

        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(rows)}] passed={results['passed']} failed={results['failed']}", flush=True)

    conn.close()
    return results


def print_report(results: dict[str, Any]) -> None:
    if "error" in results:
        print(f"Error: {results['error']}")
        return

    total = results["total"]
    passed = results["passed"]
    failed = results["failed"]
    recall = passed / total * 100 if total > 0 else 0

    print()
    print("=" * 60)
    print("GOLDEN TEST REPORT (New Architecture)")
    print("=" * 60)
    print(f"Total:  {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Recall: {recall:.1f}%")
    print()

    print("--- By Category ---")
    for cat in sorted(results["by_category"]):
        s = results["by_category"][cat]
        r = s["passed"] / s["total"] * 100 if s["total"] > 0 else 0
        print(f"  {cat:15} {s['passed']:4d}/{s['total']:4d} ({r:.1f}%)")

    print()
    print("--- By Document ---")
    for doc in sorted(results["by_doc"]):
        s = results["by_doc"][doc]
        r = s["passed"] / s["total"] * 100 if s["total"] > 0 else 0
        print(f"  {doc:15} {s['passed']:4d}/{s['total']:4d} ({r:.1f}%)")

    if results["failures"]:
        print()
        print(f"--- Failure Sources ---")
        for src, cnt in Counter(f["source"] for f in results["failures"]).most_common():
            print(f"  source='{src}' (no data): {cnt}")

        print()
        print(f"--- First 10 Failures ---")
        for f in results["failures"][:10]:
            print(f"  [{f['category']:12}] {f['query'][:70]}")
            print(f"    entity={f.get('entity','N/A')} source={f['source']} type={f['data_type']}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc-id", help="Single document ID")
    parser.add_argument("--workspace", default="knowledge_base")
    args = parser.parse_args()

    workspace = ROOT / args.workspace
    ontology_db = workspace / "ontology" / "ontology.db"

    results = run_golden_tests(workspace, ontology_db, doc_id=args.doc_id)
    print_report(results)


if __name__ == "__main__":
    main()
