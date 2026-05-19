from __future__ import annotations

import json
from pathlib import Path

from enterprise_agent_kb.answer_api import answer_query


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "knowledge_base"
CASES_PATH = ROOT / "tests" / "generated" / "knowledge_chain_regression_cases_2026-04-21.json"
REPORT_PATH = ROOT / "docs" / "knowledge_chain_regression_report_2026-04-21.json"


def _check_subgraph(subgraph: dict[str, object], expected: dict[str, object]) -> tuple[bool, dict[str, object]]:
    if not expected:
        return True, {}

    failures: dict[str, object] = {}
    for key, expected_value in expected.items():
        if key == "wiki_count_min":
            actual = int(subgraph.get("wiki_count", 0))
            if actual < int(expected_value):
                failures[key] = {"expected_min": expected_value, "actual": actual}
        elif key == "fact_count_min":
            actual = int(subgraph.get("fact_count", 0))
            if actual < int(expected_value):
                failures[key] = {"expected_min": expected_value, "actual": actual}
        elif key == "edge_count_min":
            actual = int(subgraph.get("edge_count", 0))
            if actual < int(expected_value):
                failures[key] = {"expected_min": expected_value, "actual": actual}
    return not failures, failures


def main() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    results: list[dict[str, object]] = []
    passed = 0

    for case in cases:
        response = answer_query(
            WORKSPACE,
            str(case["query"]),
            limit=8,
            preferred_doc_id=str(case["doc_id"]),
        )
        direct_answer = str(response.get("direct_answer", ""))
        context = response.get("context", {}) or {}
        subgraph = context.get("knowledge_subgraph", {}) or {}

        must_include_any = list(case.get("must_include_any", []))
        must_not_include = list(case.get("must_not_include", []))
        subgraph_expect = dict(case.get("subgraph_expect", {}))

        ok = True
        if must_include_any and not any(item in direct_answer for item in must_include_any):
            ok = False
        forbidden = [item for item in must_not_include if item in direct_answer]
        if forbidden:
            ok = False

        subgraph_ok, subgraph_failures = _check_subgraph(subgraph, subgraph_expect)
        if not subgraph_ok:
            ok = False

        if ok:
            passed += 1

        results.append(
            {
                "name": case["name"],
                "doc_id": case["doc_id"],
                "query": case["query"],
                "passed": ok,
                "direct_answer": direct_answer,
                "forbidden_hits": forbidden,
                "subgraph": subgraph,
                "subgraph_failures": subgraph_failures,
                "related_wiki_pages": [item.get("title") for item in response.get("related_wiki_pages", [])],
                "supporting_fact_types": [item.get("fact_type") for item in response.get("supporting_facts", [])],
            }
        )

    report = {
        "case_count": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "success": passed == len(cases),
        "results": results,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(REPORT_PATH)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
