# -*- coding: utf-8 -*-
"""Golden Knowledge Dataset V1.0 —— pytest 集成（离线，零 LLM）。

覆盖任务书 §12 的 10 项验证 + §14 完整回归要求。
验证器本体：agent_kb_core/tools/validate_golden_dataset.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]  # repo root
GOLDEN = ROOT / "docs" / "verification" / "golden"
VALIDATOR = ROOT / "agent_kb_core" / "tools" / "validate_golden_dataset.py"


def _cases() -> dict[str, dict]:
    return {f.stem: json.loads(f.read_text(encoding="utf-8"))
            for f in sorted((GOLDEN / "cases").glob("G*.json"))}


def test_dataset_directory_layout() -> None:
    assert (GOLDEN / "schema" / "golden_case.schema.json").is_file()
    assert (GOLDEN / "manifests" / "golden_v1.0.json").is_file()
    assert (GOLDEN / "README.md").is_file()


def test_case_count_is_30() -> None:
    assert len(_cases()) == 30


def test_case_ids_unique_and_match_files() -> None:
    cases = _cases()
    ids = [c["case_id"] for c in cases.values()]
    assert len(ids) == len(set(ids)), "duplicate case_id"
    for fname, case in cases.items():
        assert case["case_id"] == fname


def test_all_30_categories_covered() -> None:
    cats = {c["category"] for c in _cases().values()}
    assert len(cats) == 30


def test_schema_validation_passes() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((GOLDEN / "schema" / "golden_case.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for cid, case in _cases().items():
        errors = list(validator.iter_errors(case))
        assert not errors, f"{cid}: {[e.message for e in errors]}"


def test_inv001_no_asserted_without_evidence() -> None:
    for cid, case in _cases().items():
        for a in case["expected"].get("assertions", []):
            if a.get("status") in ("validated", "asserted"):
                assert a.get("evidence_refs"), f"{cid}/{a.get('assertion_id')}: INV-001"


def test_inv002_inferred_has_derivation() -> None:
    for cid, case in _cases().items():
        blocks = list(case["expected"].get("assertions", []))
        for r in case["expected"].get("reasoning", []):
            blocks += r.get("expected_derived_assertions", [])
        for a in blocks:
            if a.get("assertion_type") == "inferred":
                d = a.get("derivation")
                assert d and d.get("rule_ref") and d.get("parent_assertions") and d.get("reasoner_id"), (
                    f"{cid}/{a.get('assertion_id')}: INV-002")


def test_reasoning_cases_at_least_5() -> None:
    n = sum(1 for c in _cases().values() if c["expected"].get("reasoning"))
    assert n >= 5


def test_negative_cases_at_least_3() -> None:
    n = sum(1 for c in _cases().values() if c.get("negative_expectations"))
    assert n >= 3


def test_manifest_consistency() -> None:
    manifest = json.loads((GOLDEN / "manifests" / "golden_v1.0.json").read_text(encoding="utf-8"))
    cases = _cases()
    assert manifest["case_count"] == len(cases)
    assert sorted(manifest["case_ids"]) == sorted(cases.keys())


def test_validator_cli_pass() -> None:
    """任务书 §12：验证入口必须独立可执行且输出规定格式。"""
    result = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Golden Dataset validation: PASS" in result.stdout
    assert "Cases: 30" in result.stdout
    assert "Invalid: 0" in result.stdout
    assert "Duplicate IDs: 0" in result.stdout