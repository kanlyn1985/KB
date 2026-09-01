#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AKB Golden Knowledge Dataset 验证器（AKB-P0-GOLDEN-001 §12）。

零在线依赖（V&V §13 / 任务书 §13）：纯 stdlib + 可选 jsonschema。
用法：
  python agent_kb_core/tools/validate_golden_dataset.py                # 人类可读
  python agent_kb_core/tools/validate_golden_dataset.py --json         # 机器可读
退出码：0=PASS，1=FAIL。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root (golden dataset lives in repo docs/)
GOLDEN = ROOT / "docs" / "verification" / "golden"
SCHEMA = GOLDEN / "schema" / "golden_case.schema.json"
CASES = GOLDEN / "cases"
MANIFEST = GOLDEN / "manifests" / "golden_v1.0.json"

EXPECTED_CASE_COUNT = 30
CATEGORIES = [
    "G01-fact-precise", "G02-numeric-unit", "G03-definition", "G04-entity-recognition",
    "G05-synonym-alias", "G06-single-hop-relation", "G07-multi-hop-relation", "G08-temporal-relation",
    "G09-historical-version", "G10-current-state", "G11-event-query", "G12-state-query",
    "G13-evidence-query", "G14-provenance-query", "G15-insufficient-evidence", "G16-conflicting-knowledge",
    "G17-assertion-status", "G18-candidate-knowledge", "G19-derived-knowledge", "G20-simple-rule-reasoning",
    "G21-multi-step-reasoning", "G22-reverse-graph-query", "G23-graph-vector-hybrid", "G24-lexical-semantic-hybrid",
    "G25-context-assembly", "G26-answer-contract", "G27-knowledge-gap", "G28-decision-support",
    "G29-agent-e2e", "G30-negative-forbidden",
]

EVIDENCE_ID_RE = re.compile(r"^(evd:node:[^\s:]+:[0-9]+|evd:gold:[a-z0-9_]+)$")
ASSERTION_ID_RE = re.compile(r"^ast_g[0-9]{3}(_[a-z0-9_]+)?$")
CASE_ID_RE = re.compile(r"^G[0-9]{3}$")


def fail(errors: list[str], msg: str) -> None:
    errors.append(msg)


def collect_assertion_ids(case: dict) -> set[str]:
    ids: set[str] = set()
    for a in case.get("expected", {}).get("assertions", []):
        if a.get("assertion_id"):
            ids.add(a["assertion_id"])
    for r in case.get("expected", {}).get("reasoning", []):
        for a in r.get("expected_derived_assertions", []):
            if a.get("assertion_id"):
                ids.add(a["assertion_id"])
    return ids


def validate() -> tuple[list[str], dict]:
    errors: list[str] = []
    stats: dict = {"cases": 0, "schema_errors": 0}

    if not SCHEMA.exists():
        fail(errors, f"schema missing: {SCHEMA}")
        return errors, stats
    if not MANIFEST.exists():
        fail(errors, f"manifest missing: {MANIFEST}")
        return errors, stats
    case_files = sorted(CASES.glob("G*.json"))
    if not case_files:
        fail(errors, f"no case files in {CASES}")
        return errors, stats

    raw_cases: dict[str, dict] = {}
    for f in case_files:
        try:
            raw_cases[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(errors, f"{f.name}: invalid JSON: {exc}")

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    try:
        import jsonschema
        validator = jsonschema.Draft202012Validator(schema)
        use_jsonschema = True
    except ImportError:
        use_jsonschema = False
        print("note: jsonschema not installed, running built-in structural checks only")

    for cid, case in raw_cases.items():
        if use_jsonschema:
            for err in validator.iter_errors(case):
                fail(errors, f"{cid}: schema violation at {list(err.absolute_path)}: {err.message}")
                stats["schema_errors"] += 1
        else:
            for field in ("case_id", "category", "difficulty", "input", "expected", "notes"):
                if field not in case:
                    fail(errors, f"{cid}: missing required field {field}")

    seen_ids: list[str] = []
    for cid, case in raw_cases.items():
        c = case.get("case_id", "")
        if not CASE_ID_RE.match(c):
            fail(errors, f"{cid}: bad case_id format {c!r}")
        seen_ids.append(c)
    dupes = {x for x in seen_ids if seen_ids.count(x) > 1}
    for d in sorted(dupes):
        fail(errors, f"duplicate case_id: {d}")
    for fname, case in raw_cases.items():
        if case.get("case_id") and case["case_id"] != fname:
            fail(errors, f"file {fname}.json contains case_id {case['case_id']}")

    used_cats = set()
    for cid, case in raw_cases.items():
        cat = case.get("category", "")
        if cat not in CATEGORIES:
            fail(errors, f"{cid}: unknown category {cat!r}")
        used_cats.add(cat)
    missing_cats = [c for c in CATEGORIES if c not in used_cats]
    if missing_cats:
        fail(errors, f"categories not covered: {missing_cats}")

    n_reasoning = 0
    for cid, case in raw_cases.items():
        exp = case.get("expected", {})
        if not exp:
            fail(errors, f"{cid}: missing expected block")
            continue
        for ev in exp.get("evidence", []):
            if not EVIDENCE_ID_RE.match(ev.get("evidence_id", "")):
                fail(errors, f"{cid}: bad evidence_id {ev.get('evidence_id')!r}")
            if not ev.get("excerpt") and not ev.get("document_id"):
                fail(errors, f"{cid}: evidence {ev.get('evidence_id')} needs excerpt or document_id")
        for a in exp.get("assertions", []):
            aid = a.get("assertion_id", "")
            if aid and not ASSERTION_ID_RE.match(aid):
                fail(errors, f"{cid}: bad assertion_id {aid!r}")
            if a.get("status") in ("validated", "asserted") and not a.get("evidence_refs"):
                fail(errors, f"{cid}: INV-001 violation — {aid or cid} {a.get('status')} without evidence_refs")
            if a.get("assertion_type") == "inferred" and not a.get("derivation"):
                fail(errors, f"{cid}: INV-002 — inferred assertion {aid} missing derivation block")
        for r in exp.get("reasoning", []):
            for a in r.get("expected_derived_assertions", []):
                if a.get("assertion_type") == "inferred" and not a.get("derivation"):
                    fail(errors, f"{cid}: INV-002 — inferred assertion in {r.get('reasoning_id')} missing derivation")
        if case.get("category") in {"G20-simple-rule-reasoning", "G21-multi-step-reasoning",
                                    "G07-multi-hop-relation", "G19-derived-knowledge"} and not exp.get("reasoning"):
            fail(errors, f"{cid}: reasoning-category case lacks expected.reasoning")
        if exp.get("reasoning"):
            n_reasoning += 1
            for r in exp["reasoning"]:
                for key in ("input_assertions", "rule_refs", "expected_derived_assertions", "expected_trace"):
                    if not r.get(key):
                        fail(errors, f"{cid}/{r.get('reasoning_id')}: reasoning {key} empty")

    n_negative = 0
    for cid, case in raw_cases.items():
        negs = case.get("negative_expectations", [])
        if case.get("category") == "G30-negative-forbidden" and not negs:
            fail(errors, f"{cid}: negative case lacks negative_expectations")
        if negs:
            n_negative += 1
            for n in negs:
                if not n.get("description"):
                    fail(errors, f"{cid}: negative expectation missing description")

    n_neg_expectations = sum(
        len(case.get("negative_expectations", [])) for case in raw_cases.values()
    )

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    m_ids = manifest.get("case_ids", [])
    if sorted(m_ids) != sorted(raw_cases.keys()):
        fail(errors, "manifest case_ids do not match case files")
    if len(raw_cases) != EXPECTED_CASE_COUNT:
        fail(errors, f"case count {len(raw_cases)} != expected {EXPECTED_CASE_COUNT}")

    checks = [
        ("case_count", len(raw_cases)),
        ("negative_case_count", n_negative),
        ("negative_expectation_count", n_neg_expectations),
        ("reasoning_case_count", n_reasoning),
    ]
    for field, actual in checks:
        declared = manifest.get(field)
        if declared is None:
            fail(errors, f"manifest missing {field} (must be auto-computed value {actual})")
        elif declared != actual:
            fail(errors, f"manifest {field}={declared} != actual {actual}")

    stats.update({
        "cases": len(raw_cases),
        "reasoning_cases": n_reasoning,
        "negative_cases": n_negative,
        "negative_expectations": n_neg_expectations,
        "categories_covered": len(used_cats),
        "jsonschema_used": use_jsonschema,
    })
    return errors, stats


def main() -> int:
    as_json = "--json" in sys.argv
    errors, stats = validate()
    if as_json:
        print(json.dumps({"pass": not errors, "errors": errors, "stats": stats},
                         ensure_ascii=False, indent=1))
    else:
        print(f"Golden Dataset validation: {'PASS' if not errors else 'FAIL'}")
        print(f"Cases: {stats.get('cases', 0)}")
        print(f"Invalid: {len(errors)}")
        print(f"Duplicate IDs: {sum(1 for e in errors if 'duplicate case_id' in e)}")
        print(f"Reasoning cases: {stats.get('reasoning_cases', 0)} (require >=5)")
        print(f"Negative cases: {stats.get('negative_cases', 0)} (require >=3)")
        print(f"Negative expectations: {stats.get('negative_expectations', 0)}")
        print(f"Categories covered: {stats.get('categories_covered', 0)}/30")
        if errors:
            print("-" * 60)
            for e in errors:
                print(f"  ✗ {e}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())