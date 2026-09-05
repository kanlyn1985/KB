# -*- coding: utf-8 -*-
"""V0.1 Security Boundaries（任务书 §26）：Agent 无写路径 / 无 provider 泄漏。

Requirement: SYS-020 · Invariant: INV-008 · Test ID: 边界审计
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[3] / "agent_kb_core" / "src" / "agent_kb" / "evidence_core"
AGENT_PLANE = Path(__file__).resolve().parents[3] / "agent_kb_core" / "src" / "agent_kb"


def test_no_agent_write_path_in_evidence_core():
    """evidence_core 包不提供 agent 前缀写入口（INV-008 静态面）。"""
    src = "\n".join(p.read_text(encoding="utf-8") for p in CORE.glob("*.py"))
    assert "def create_asserted" not in src
    assert "def promote" not in src or "promote" not in src.replace("auto promote", "")


def test_no_semantica_or_provider_import():
    """ADR-006/009：evidence_core 零 Semantica/SDK import（provider 只在 Adapter/边界）。"""
    banned = re.compile(r"^\s*(import|from)\s+(neo4j|qdrant|openai|anthropic|semantica)\b", re.M)
    for p in CORE.rglob("*.py"):
        assert not banned.search(p.read_text(encoding="utf-8")), f"{p.name}: provider import 泄漏"


def test_no_agent_import_of_evidence_core_write():
    """agent 平面模块（service/webui/commands）不 import evidence_core 写接口。"""
    write_markers = ("create_candidate", "AssertionStore", "transition")
    for plane in ("service", "webui"):
        d = AGENT_PLANE / plane
        if not d.exists():
            continue
        for p in d.rglob("*.py"):
            src = p.read_text(encoding="utf-8")
            for m in write_markers:
                assert m not in src, f"{p}: agent 平面引用了写接口 {m}"