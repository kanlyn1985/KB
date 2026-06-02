"""Regression runner for DOC-000001 (QC/T 1036-2016) constraint/parameter/process queries.

Usage:
    python scripts/run_constraint_regression.py

Reads test cases from tests/generated/constraint_regression_cases_DOC-000001.json,
runs answer_query() directly (no HTTP server needed), and writes a JSON report.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure src is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from enterprise_agent_kb.answer_api import answer_query  # noqa: E402

CASES_PATH = ROOT / "tests" / "generated" / "constraint_regression_cases_DOC-000001.json"
REPORT_PATH = ROOT / "docs" / "constraint_regression_report_DOC-000001.json"
WORKSPACE = ROOT / "knowledge_base"


def main() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    results = []
    passed = 0

    for case in cases:
        query = case["query"]
        doc_id = case.get("doc_id")
        response = answer_query(
            WORKSPACE,
            query,
            limit=8,
            **({"preferred_doc_id": doc_id} if doc_id else {}),
        )
        direct_answer = str(response.get("direct_answer", ""))

        must_include_all = case.get("must_include_all", [])
        must_include_any = case.get("must_include_any", [])
        must_not_include = case.get("must_not_include", [])

        ok = True
        missing_all = [item for item in must_include_all if item not in direct_answer]
        if missing_all:
            ok = False
        missing_any = []
        if must_include_any and not any(item in direct_answer for item in must_include_any):
            missing_any = must_include_any
            ok = False
        forbidden = [item for item in must_not_include if item in direct_answer]
        if forbidden:
            ok = False

        expected_fail = case.get("_expected_fail", False)
        is_regression = not ok and not expected_fail

        if ok:
            passed += 1

        results.append({
            "name": case["name"],
            "doc_id": doc_id,
            "query": query,
            "passed": ok,
            "expected_fail": expected_fail,
            "is_regression": is_regression,
            "missing_all": missing_all,
            "missing_any": missing_any,
            "forbidden_hits": forbidden,
            "direct_answer": direct_answer[:500],
        })

    regressions = [r for r in results if r.get("is_regression")]
    report = {
        "case_count": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "expected_fails": len([r for r in results if r.get("expected_fail") and not r.get("passed")]),
        "regressions": len(regressions),
        "success": len(regressions) == 0,
        "results": results,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {REPORT_PATH}")
    print(json.dumps({"passed": passed, "failed": len(cases) - passed, "expected_fails": report["expected_fails"], "regressions": len(regressions)}, ensure_ascii=False))
    if regressions:
        print("REGRESSIONS (unexpected failures):")
        for r in regressions:
            print(f"  {r['name']}: query={r['query']} missing_all={r['missing_all']} missing_any={r['missing_any']} forbidden={r['forbidden_hits']}")
    sys.exit(0 if report["success"] else 1)


if __name__ == "__main__":
    main()
