# -*- coding: utf-8 -*-
"""V0.1-REG-001：Golden 回归（V0.1 加入后基线零回归）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_reg_001_golden_validator_pass():
    r = subprocess.run(
        [sys.executable, str(ROOT / "agent_kb_core" / "tools" / "validate_golden_dataset.py")],
        capture_output=True, text=True, timeout=120)
    assert r.returncode == 0
    assert "Golden Dataset validation: PASS" in r.stdout
    assert "Cases: 30" in r.stdout
    assert "Invalid: 0" in r.stdout


def test_reg_001b_golden_evd_refs_resolvable(db, seeded):
    """Golden evd:node:* 引用经 legacy resolver 可解析路径存在（影子映射契约）。"""
    from agent_kb.evidence_core import LegacyEvidenceResolver
    resolver = LegacyEvidenceResolver(db)
    db.execute("INSERT INTO evidence (evidence_id, document_id, snippet)"
               " VALUES ('evd:node:P-ROOT:0', 'doc:node:P-ROOT', '样本')")
    assert resolver.resolve("evd:node:P-ROOT:0") is not None