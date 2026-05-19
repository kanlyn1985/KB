from __future__ import annotations

import json
from pathlib import Path

from enterprise_agent_kb.entities import build_entities_for_document
from enterprise_agent_kb.graph import build_graph_for_document


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "knowledge_base"
REPORT_PATH = ROOT / "docs" / "graph_regression_report_2026-04-21.json"


def main() -> None:
    docs = ["DOC-000002", "DOC-000003"]
    results = []
    passed = 0

    for doc_id in docs:
        build_entities_for_document(WORKSPACE, doc_id)
        graph_result = build_graph_for_document(WORKSPACE, doc_id)
        edge_types = graph_result.edge_types
        ok = (
            edge_types.get("has_process", 0) > 0
            and edge_types.get("has_parameter_group", 0) > 0
            and edge_types.get("relates_to_term", 0) > 0
        )
        if ok:
            passed += 1
        results.append(
            {
                "doc_id": doc_id,
                "passed": ok,
                "edge_count": graph_result.edge_count,
                "edge_types": edge_types,
                "export_path": str(graph_result.export_path),
            }
        )

    report = {
        "case_count": len(docs),
        "passed": passed,
        "failed": len(docs) - passed,
        "success": passed == len(docs),
        "results": results,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(REPORT_PATH)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
