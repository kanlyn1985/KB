# -*- coding: utf-8 -*-
"""Golden manifest coverage 一致性（AKB-P0-ADR-001 §16）。

manifest 的 4 个计数字段必须与 cases/*.json 自动计算结果逐项一致：
case_count / negative_case_count / negative_expectation_count / reasoning_case_count。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "docs" / "verification" / "golden"


def _cases() -> dict[str, dict]:
    return {f.stem: json.loads(f.read_text(encoding="utf-8"))
            for f in sorted((GOLDEN / "cases").glob("G*.json"))}


def _manifest() -> dict:
    return json.loads((GOLDEN / "manifests" / "golden_v1.0.json").read_text(encoding="utf-8"))


def test_manifest_coverage_consistency() -> None:
    cases = _cases()
    manifest = _manifest()

    actual = {
        "case_count": len(cases),
        "negative_case_count": sum(1 for c in cases.values() if c.get("negative_expectations")),
        "negative_expectation_count": sum(
            len(c.get("negative_expectations", [])) for c in cases.values()),
        "reasoning_case_count": sum(1 for c in cases.values() if c["expected"].get("reasoning")),
    }
    for field, value in actual.items():
        assert manifest.get(field) == value, (
            f"manifest {field}={manifest.get(field)} != actual {value}")


def test_manifest_counts_not_hand_edited() -> None:
    """count_policy 必须声明数字来自自动计算（防手工硬编码漂移回归）。"""
    m = _manifest()
    assert "auto-computed" in m.get("count_policy", ""), (
        "manifest count_policy must state counts are auto-computed")