from __future__ import annotations

import json
from pathlib import Path

from enterprise_agent_kb.query_api import build_query_context
from enterprise_agent_kb.wiki_compiler import build_wiki_for_document


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "knowledge_base"
REPORT_PATH = ROOT / "docs" / "wiki_regression_report_2026-04-21.json"


def main() -> None:
    docs = ["DOC-000002", "DOC-000003"]
    for doc_id in docs:
        build_wiki_for_document(WORKSPACE, doc_id)

    cases = [
        {"name": "process_wiki_doc000002", "doc_id": "DOC-000002", "query": "CP时序", "must_page_type": "process"},
        {"name": "parameter_wiki_doc000002", "doc_id": "DOC-000002", "query": "CC阻值", "must_page_type": "parameter_group"},
    ]

    results = []
    passed = 0
    for case in cases:
        context = build_query_context(WORKSPACE, case["query"], limit=8, preferred_doc_id=case["doc_id"])
        wiki_pages = context.get("wiki_pages", [])
        ok = any(item.get("page_type") == case["must_page_type"] for item in wiki_pages)
        if ok:
            passed += 1
        results.append(
            {
                "name": case["name"],
                "doc_id": case["doc_id"],
                "query": case["query"],
                "passed": ok,
                "wiki_pages": wiki_pages,
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
