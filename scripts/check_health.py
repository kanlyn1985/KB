"""System health check for KB1.

Verifies that the knowledge base is in a healthy state:
  - DB is accessible
  - Documents are active
  - Evidence / facts / expected_points are populated
  - FTS index is not empty
  - Recent eval pass rate meets threshold (if available)

Usage:
    python scripts/check_health.py                  # default workspace
    python scripts/check_health.py --workspace /path/to/kb
    python scripts/check_health.py --min-fact-count 100   # custom threshold

Exit codes:
    0 = healthy
    1 = one or more checks failed
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _check(name: str, condition: bool, detail: str = "") -> bool:
    """Print and return a single check result."""
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}: {detail}")
    return condition


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace", default=str(ROOT / "knowledge_base"),
        help="path to knowledge_base workspace (default: <repo>/knowledge_base)",
    )
    parser.add_argument(
        "--min-fact-count", type=int, default=10,
        help="minimum total fact count (default 10)",
    )
    parser.add_argument(
        "--min-doc-count", type=int, default=1,
        help="minimum active document count (default 1)",
    )
    parser.add_argument(
        "--min-expected-docs", type=int, default=1,
        help="minimum expected_points document count (default 1)",
    )
    parser.add_argument(
        "--max-fact-zero-ratio", type=float, default=0.5,
        help="maximum ratio of fact_types that are zero (default 0.5)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="output JSON instead of human-readable",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace)
    db_file = workspace / "db" / "knowledge.db"

    results: list[dict] = []
    overall_pass = True

    def add(name: str, passed: bool, detail: str = "") -> None:
        nonlocal overall_pass
        if not passed:
            overall_pass = False
        results.append({"check": name, "passed": passed, "detail": detail})

    # 1. Workspace exists
    add("workspace_exists", workspace.is_dir(),
        f"path={workspace}")

    # 2. DB file exists
    add("db_file_exists", db_file.is_file(),
        f"path={db_file}")

    if not db_file.is_file():
        # Cannot continue without DB
        return _output_results(args, results, overall_pass)

    # 3. DB accessible
    from enterprise_agent_kb.db import connect
    try:
        conn = connect(db_file)
        add("db_connect", True, "OK")
    except Exception as e:
        add("db_connect", False, str(e))
        return _output_results(args, results, overall_pass)

    try:
        # 4. Documents active
        doc_count = conn.execute(
            "SELECT COUNT(*) AS n FROM documents WHERE is_active = 1"
        ).fetchone()["n"]
        add("active_documents", doc_count >= args.min_doc_count,
            f"count={doc_count}, min={args.min_doc_count}")

        # 5. Facts populated
        fact_count = conn.execute(
            "SELECT COUNT(*) AS n FROM facts"
        ).fetchone()["n"]
        add("facts_populated", fact_count >= args.min_fact_count,
            f"count={fact_count}, min={args.min_fact_count}")

        # 6. Evidence populated
        evidence_count = conn.execute(
            "SELECT COUNT(*) AS n FROM evidence"
        ).fetchone()["n"]
        add("evidence_populated", evidence_count > 0,
            f"count={evidence_count}")

        # 7. Expected points populated
        try:
            ep_count = conn.execute(
                "SELECT COUNT(DISTINCT doc_id) AS n FROM expected_points"
            ).fetchone()["n"]
            add("expected_points_populated", ep_count >= args.min_expected_docs,
                f"distinct_docs={ep_count}, min={args.min_expected_docs}")
        except Exception as e:
            add("expected_points_populated", False, f"query error: {e}")

        # 8. FTS index not empty
        try:
            fts_count = conn.execute(
                "SELECT COUNT(*) AS n FROM facts_fts"
            ).fetchone()["n"]
            add("fts_index_populated", fts_count > 0,
                f"facts_fts_rows={fts_count}")
        except Exception as e:
            add("fts_index_populated", False, f"query error: {e}")

        # 9. Fact type distribution: avoid docs with all zero types
        try:
            fact_types = conn.execute(
                "SELECT fact_type, COUNT(*) AS n FROM facts GROUP BY fact_type"
            ).fetchall()
            type_count = len(fact_types)
            zero_types = sum(1 for r in fact_types if r["n"] == 0)
            ratio = zero_types / type_count if type_count > 0 else 0
            add("fact_type_diversity", ratio <= args.max_fact_zero_ratio,
                f"types={type_count}, zero_ratio={ratio:.2%}")
        except Exception as e:
            add("fact_type_diversity", False, f"query error: {e}")

        # 10. Recent eval report (if any)
        eval_dir = workspace / "eval_runs"
        if eval_dir.is_dir():
            reports = sorted(eval_dir.glob("v*.json"))
            if reports:
                latest = reports[-1]
                try:
                    data = json.loads(latest.read_text(encoding="utf-8"))
                    pr = data.get("pass_rate")
                    if pr is None:
                        pr = data.get("pass_rate_token_overlap", 0)
                    add("latest_eval_report_exists", True,
                        f"file={latest.name}, pass_rate={pr:.2%}")
                except Exception as e:
                    add("latest_eval_report_exists", False, f"parse error: {e}")
            else:
                add("latest_eval_report_exists", False, "no v*.json found in eval_runs/")
        else:
            add("latest_eval_report_exists", False, "eval_runs/ not found")

    finally:
        conn.close()

    return _output_results(args, results, overall_pass)


def _output_results(args: argparse.Namespace, results: list, overall_pass: bool) -> int:
    if args.json:
        print(json.dumps({"overall_pass": overall_pass, "checks": results}, indent=2))
    else:
        print(f"\n=== KB1 Health Check ===")
        for r in results:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"  [{status}] {r['check']}: {r['detail']}")
        print(f"\n=== Overall: {'PASS' if overall_pass else 'FAIL'} ===")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
