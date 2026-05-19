from __future__ import annotations

import json
from pathlib import Path

from enterprise_agent_kb.query_api import build_query_context


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "knowledge_base"
REPORT_PATH = ROOT / "docs" / "subgraph_regression_report_2026-04-21.json"


def main() -> None:
    cases = [
        {"name": "cc_parameter_subgraph", "doc_id": "DOC-000002", "query": "CC阻值"},
        {"name": "cp_timing_subgraph", "doc_id": "DOC-000002", "query": "CP时序"},
    ]
    results = []
    passed = 0
    for case in cases:
        context = build_query_context(WORKSPACE, case["query"], limit=8, preferred_doc_id=case["doc_id"])
        subgraph = context.get("knowledge_subgraph", {})
        ok = (
            int(subgraph.get("wiki_count", 0)) > 0
            and int(subgraph.get("fact_count", 0)) > 0
            and int(subgraph.get("edge_count", 0)) > 0
        )
        if ok:
            passed += 1
        results.append(
            {
                "name": case["name"],
                "doc_id": case["doc_id"],
                "query": case["query"],
                "passed": ok,
                "knowledge_subgraph": subgraph,
                "wiki_pages": context.get("wiki_pages", [])[:5],
                "graph_edges": context.get("graph_edges", [])[:8],
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
