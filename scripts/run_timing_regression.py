from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "tests" / "generated" / "timing_regression_cases_2026-04-21.json"
REPORT_PATH = ROOT / "docs" / "timing_regression_report_2026-04-21.json"


def main() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    results = []
    passed = 0

    for case in cases:
        payload = json.dumps(
            {
                "query": case["query"],
                "limit": 8,
                "preferred_doc_id": case["doc_id"],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        req = Request(
            "http://127.0.0.1:8000/answer-query",
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
        response = json.loads(body)
        direct_answer = str(response.get("direct_answer", ""))

        must_include_any = case.get("must_include_any", [])
        must_not_include = case.get("must_not_include", [])

        ok = True
        if must_include_any and not any(item in direct_answer for item in must_include_any):
            ok = False
        forbidden = [item for item in must_not_include if item in direct_answer]
        if forbidden:
            ok = False

        if ok:
            passed += 1

        results.append(
            {
                "name": case["name"],
                "doc_id": case["doc_id"],
                "query": case["query"],
                "passed": ok,
                "forbidden_hits": forbidden,
                "direct_answer": direct_answer,
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
