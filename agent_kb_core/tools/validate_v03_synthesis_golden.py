# -*- coding: utf-8 -*-
"""V0.3 Golden validator：manifest 结构 + 分类配额 + 案例字段完备性。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT.parent / "docs" / "verification" / "golden" / "v03_synthesis"

REQUIRED_FIELDS = {"case_id", "category", "description", "input_evidence_ids",
                   "expectation"}
CATEGORIES = {"positive": 20, "negative": 15, "determinism": 5,
              "conflict": 5, "provider_boundary": 5, "provenance": 5}


def main() -> int:
    manifest = json.loads((GOLDEN / "cases.json").read_text(encoding="utf-8"))
    cases = manifest["cases"]
    problems = []
    counts = {}
    seen = set()
    for c in cases:
        missing = REQUIRED_FIELDS - set(c)
        if missing:
            problems.append(f"{c.get('case_id')}: missing {missing}")
        if c["case_id"] in seen:
            problems.append(f"{c['case_id']}: duplicate id")
        seen.add(c["case_id"])
        counts[c["category"]] = counts.get(c["category"], 0) + 1
    for cat, want in CATEGORIES.items():
        if counts.get(cat, 0) != want:
            problems.append(f"category {cat}: {counts.get(cat, 0)} != {want}")
    if len(cases) != 55:
        problems.append(f"total {len(cases)} != 55")
    print("V0.3 Golden dataset validation:", "PASS" if not problems else "FAIL")
    print(f"Cases: {len(cases)} | " +
          " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    for p in problems:
        print("  PROBLEM:", p)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())