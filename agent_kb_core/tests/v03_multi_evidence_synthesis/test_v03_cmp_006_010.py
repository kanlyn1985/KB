# -*- coding: utf-8 -*-
"""V03-CMP-006..010：relation/event/state/temporal 对齐 + compatible。"""
from __future__ import annotations

import pytest


def test_v03_cmp_006_relation_alignment(db, compiled_evidence):
    eng = compiled_evidence["engine"]
    r = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    rcs = r["run"].alignment["relation_clusters"]
    assert rcs, "expected cross-evidence relation cluster (has_parameter)"
    assert any(len({m["evidence_id"] for m in rc["members"]}) >= 2 for rc in rcs)


def test_v03_cmp_007_event_alignment(db, compiled_evidence):
    # 事件簇需要 event_time——V0.2 R-01 文本无绝对日期 → event 簇为空（合法）
    eng = compiled_evidence["engine"]
    r = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    assert isinstance(r["run"].alignment["event_clusters"], list)


def test_v03_cmp_008_state_alignment(db, compiled_evidence):
    eng = compiled_evidence["engine"]
    r = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    assert isinstance(r["run"].alignment["state_clusters"], list)


def test_v03_cmp_009_temporal_alignment(db, compiled_evidence):
    eng = compiled_evidence["engine"]
    r = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    ta = r["run"].alignment["temporal_alignment"]
    assert ta["overall"] in ("same", "partial", "missing", "unresolved")
    assert set(ta["per_evidence"]) == set(compiled_evidence["evidence_ids"])


def test_v03_cmp_010_compatible_evidence(db, compiled_evidence):
    eng = compiled_evidence["engine"]
    r = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    compat = r["run"].alignment["rule_audit"]
    assert any(audit["rule_id"] == "COMPAT-001" for audit in compat)
    # 同值多证据 → COMPATIBLE（无冲突）
    assert not r["run"].conflicts["conflicts"] or all(
        c["conflict_type"] != "VALUE_CONFLICT"
        for c in r["run"].conflicts["conflicts"])