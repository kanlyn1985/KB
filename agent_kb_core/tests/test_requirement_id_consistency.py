# -*- coding: utf-8 -*-
"""Requirement ID 一致性检查（AKB-P0-BASELINE-CLEANUP-001 §10）。

SRS/RTM 需求 ID 唯一性 + SRS↔RTM 映射完整性。
（由 test_baseline_consistency.py 按任务书指定文件名拆分而来，断言不变。）
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRS = ROOT / "docs" / "requirements" / "SRS" / "Agentic_Knowledge_Base_SRS_V1.1_Engineering_Baseline.html"
RTM = ROOT / "docs" / "verification" / "REQUIREMENT_TRACEABILITY_MATRIX_V1.0.md"

SRS_REQ_RE = re.compile(r"SYS-[A-Z]+-\d+")
RTM_REQ_RE = re.compile(r"SYS-\d{3}")


def _srs_reqs() -> set[str]:
    src = SRS.read_text(encoding="utf-8")
    return {m.group(0) for m in SRS_REQ_RE.finditer(src)}


def _rtm_reqs() -> set[str]:
    src = RTM.read_text(encoding="utf-8")
    return {m.group(0) for m in RTM_REQ_RE.finditer(src)}


def test_srs_requirement_ids_unique() -> None:
    src = SRS.read_text(encoding="utf-8")
    ids = SRS_REQ_RE.findall(src)
    # 族表内唯一：SYS-EVD-001 等在正文（映射表）重复出现是允许的，但 SRS 自身表中不重复
    fam_table = re.search(r"核心系统需求(.*?)(?=<h2>)", src, re.S)
    table_ids = SRS_REQ_RE.findall(fam_table.group(1))
    assert len(table_ids) == len(set(table_ids)), "SRS 需求表内 ID 重复"


def test_rtm_requirement_ids_unique() -> None:
    src = RTM.read_text(encoding="utf-8")
    matrix = re.search(r"## 3\. System Requirement Matrix(.*?)(?=\n## )", src, re.S).group(1)
    ids = RTM_REQ_RE.findall(matrix)
    assert len(ids) >= 20, f"RTM 矩阵应至少 20 条 SYS-nnn，实际 {len(ids)}"
    assert len(set(ids)) == len(ids), "RTM 矩阵内 SYS-nnn ID 重复"
    # §2a 映射表引用的 RTM ID 必须都存在于矩阵（映射不造新号）
    m = re.search(r"## 2a\..*?(?=\n## )", src, re.S).group(0)
    mapped = set(RTM_REQ_RE.findall(m))
    assert mapped <= set(ids), f"映射表引用了矩阵外的 SYS-nnn: {mapped - set(ids)}"


def test_srs_rtm_mapping_complete() -> None:
    """§2a 映射表存在且 SRS 每族都有映射行。"""
    src = RTM.read_text(encoding="utf-8")
    assert "## 2a. SRS ↔ RTM Requirement ID Mapping" in src, "RTM 缺少 §2a 映射表"
    m = re.search(r"## 2a\..*?(?=\n## )", src, re.S)
    mapping_rows = re.findall(r"\| (SYS-[A-Z]+-\d+) \|", m.group(0))
    srs_fams = {f"{r.split('-')[1]}" for r in _srs_reqs()}
    mapped_fams = {r.split("-")[1] for r in mapping_rows}
    assert srs_fams <= mapped_fams, f"SRS 族未映射: {srs_fams - mapped_fams}"
    # RTM 侧：映射行覆盖的 SYS-nnn 必须真实存在于 RTM 矩阵
    rtm_ids = _rtm_reqs()
    mapped_rtm = set(re.findall(r"SYS-\d{3}", m.group(0)))
    unknown = mapped_rtm - rtm_ids
    assert not unknown, f"映射引用了 RTM 不存在的 ID: {unknown}"


