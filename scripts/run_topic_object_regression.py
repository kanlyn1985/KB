from __future__ import annotations

import json
from pathlib import Path

from enterprise_agent_kb.answer_api import answer_query


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "knowledge_base"
CASES_PATH = ROOT / "tests" / "generated" / "topic_object_regression_cases_2026-04-21.json"
REPORT_PATH = ROOT / "docs" / "topic_object_regression_report_2026-04-21.json"


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
        topic_objects = list(response.get("topic_objects", []) or [])
        topic_entities = list(response.get("topic_entities", []) or [])
        topic_titles = [str(item.get("title") or "") for item in topic_objects]
        topic_entity_types = [str(item.get("entity_type") or "") for item in topic_entities]

        expected_titles_any = list(case.get("expected_topic_titles_any", []))
        expected_entity_types_any = list(case.get("expected_topic_entity_types_any", []))

        ok = True
        if expected_titles_any and not any(title in topic_titles for title in expected_titles_any):
            ok = False
        if expected_entity_types_any and not any(entity_type in topic_entity_types for entity_type in expected_entity_types_any):
            ok = False

        if ok:
            passed += 1

        results.append(
            {
                "name": case["name"],
                "doc_id": case["doc_id"],
                "query": case["query"],
                "passed": ok,
                "topic_titles": topic_titles,
                "topic_entity_types": topic_entity_types,
                "topic_objects": topic_objects,
                "topic_entities": topic_entities,
                "direct_answer": response.get("direct_answer"),
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
