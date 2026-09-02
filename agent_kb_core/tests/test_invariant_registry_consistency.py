# -*- coding: utf-8 -*-
"""Invariant Registry 一致性检查（AKB-P0-BASELINE-CLEANUP-001 §10）。

Registry INV-001..010 唯一、全仓引用无未知编号、无同号异义。
（由 test_baseline_consistency.py 按任务书指定文件名拆分而来，断言不变。）
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs" / "architecture" / "INVARIANT_REGISTRY_V1.0.md"
GOLDEN_CASES = ROOT / "docs" / "verification" / "golden" / "cases"
DECISIONS = ROOT / "docs" / "architecture" / "decisions"

INV_RE = re.compile(r"INV-\d{3}")
EXPECTED_INVARIANTS = {f"INV-{i:03d}" for i in range(1, 11)}


def _registry_invariants() -> dict[str, str]:
    """返回 {INV-ID: 规范规则一句话}（Registry 表格行）。"""
    src = REGISTRY.read_text(encoding="utf-8")
    out = {}
    for line in src.splitlines():
        m = re.match(r"\| (INV-\d{3}) \| ([^|]+) \|", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def test_invariant_registry_complete_and_unique() -> None:
    reg = _registry_invariants()
    assert set(reg.keys()) == EXPECTED_INVARIANTS, (
        f"Registry 应含 INV-001..010，实际 {sorted(reg.keys())}")
    for inv, rule in reg.items():
        assert len(rule) > 10, f"{inv} 规范规则过短"


def test_all_repo_inv_references_known() -> None:
    """全仓（docs + tests）INV 引用必须都在 Registry 内——禁止未知编号。"""
    known = EXPECTED_INVARIANTS
    scanned = []
    registry_path = REGISTRY.resolve()
    for base in [ROOT / "docs", ROOT / "agent_kb_core" / "tests"]:
        for p in base.rglob("*"):
            if p.suffix in (".md", ".json", ".py", ".html") and p.is_file():
                try:
                    text = p.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                if p.resolve() == registry_path:
                    # Registry 自身正文含"禁止发明 INV-nnn(nnn>10)"规则示例，不在扫描范围
                    text = text.replace("INV-nnn(nnn>10)", "INV-XXX")
                for m in INV_RE.finditer(text):
                    scanned.append((p, m.group(0)))
    unknown = [(str(p), inv) for p, inv in scanned if inv not in known]
    assert not unknown, f"发现未知 INV 引用（Registry 无此编号）: {unknown[:10]}"


def test_golden_invariant_refs_consistent() -> None:
    """golden case 的 invariant_ref 必须 ∈ Registry 且语义类别正确（抽样规则：agent 写权限类引用必为 INV-008）。"""
    reg = _registry_invariants()
    for f in sorted(GOLDEN_CASES.glob("G*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        for n in c.get("negative_expectations", []):
            r = n.get("invariant_ref")
            if r:
                assert r in reg, f"{f.stem}: invariant_ref {r} 不在 Registry"
                if "Agent" in n.get("description", "") and "写" in n.get("description", ""):
                    assert r == "INV-008", f"{f.stem}: Agent 写权限类期望应引用 INV-008，实际 {r}"


def test_adr_invariant_refs_consistent() -> None:
    """ADR 引用的 INV 编号全部 ∈ Registry；Agent 写边界语义必须引用 INV-008（非历史错位 INV-006）。"""
    reg = _registry_invariants()
    for p in sorted(DECISIONS.glob("ADR-*.md")):
        src = p.read_text(encoding="utf-8")
        for m in INV_RE.finditer(src):
            assert m.group(0) in reg, f"{p.name}: {m.group(0)} 不在 Registry"
    adr8 = (DECISIONS / "ADR-008-agent-runtime-decoupling.md").read_text(encoding="utf-8")
    assert "INV-008" in adr8 and "read-only for agents (INV-006)" not in adr8, (
        "ADR-008 Agent 写边界引用应为 INV-008（Registry 对齐）")