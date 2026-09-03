# -*- coding: utf-8 -*-
"""V03-CMP-001..005：Set 身份/顺序/变更/重复/实体对齐。"""
from __future__ import annotations

import pytest

from agent_kb.evidence_core.synthesis import (
    EvidenceSetManager,
    SynthesisEngine,
    SynthesisError,
)


def test_v03_cmp_001_set_identity(db, compiled_evidence):
    mgr = EvidenceSetManager(db)
    eids = compiled_evidence["evidence_ids"]
    s1 = mgr.create(eids, actor_id="system:synth")
    s2 = mgr.create(list(reversed(eids)), actor_id="system:synth")
    assert s1.set_id == s2.set_id and s1.set_fingerprint == s2.set_fingerprint
    rows = db.execute("SELECT COUNT(*) AS c FROM akb_evidence_sets").fetchone()["c"]
    assert rows == 1  # Set 复用（不重复建）


def test_v03_cmp_002_ordering_invariance(db, compiled_evidence):
    eids = compiled_evidence["evidence_ids"]
    eng = SynthesisEngine(db)
    r1 = eng.synthesize(eids, actor_id="system:synth")
    r2 = eng.synthesize(list(reversed(eids)), actor_id="system:synth")
    assert r1["fingerprint"] == r2["fingerprint"]
    assert r2["idempotent_hit"]


def test_v03_cmp_003_mutation_changes_fingerprint(db, compiled_evidence):
    from agent_kb.evidence_core.synthesis import evidence_set_fingerprint
    mgr = EvidenceSetManager(db)
    eids = compiled_evidence["evidence_ids"]
    s_full = mgr.create(eids, actor_id="system:synth")
    s_two = mgr.create(eids[:2], actor_id="system:synth")
    assert s_two.set_fingerprint != s_full.set_fingerprint
    # 旧 Set 冻结（INV-005）：全成员 Set 仍可取回
    assert mgr.get(s_full.set_id).members == sorted(eids)
    assert evidence_set_fingerprint(sorted(eids), "v", "c") != \
        evidence_set_fingerprint(sorted(eids)[:2], "v", "c")


def test_v03_cmp_004_duplicate_membership_rejection(db, compiled_evidence):
    mgr = EvidenceSetManager(db)
    eids = compiled_evidence["evidence_ids"]
    with pytest.raises(SynthesisError, match="E-V03-SET-DUPLICATE"):
        mgr.create([eids[0], eids[0]], actor_id="system:synth")
    rows = db.execute("SELECT COUNT(*) AS c FROM akb_evidence_sets").fetchone()["c"]
    assert rows == 0  # 零副作用


def test_v03_cmp_005_entity_alignment(db, compiled_evidence):
    eng = compiled_evidence["engine"]
    r = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    clusters = r["run"].alignment["entity_clusters"]
    assert clusters, "expected entity clusters"
    cross = [c for c in clusters if len({m["evidence_id"] for m in c["members"]}) >= 2]
    assert cross, "expected at least one cross-evidence entity cluster (OBC)"
    cl = cross[0]
    member_eids = {m["evidence_id"] for m in cl["members"]}
    assert len(member_eids) >= 2  # 跨证据
    # 簇 ID 稳定：跨证据簇按最小 (evidence_id, candidate_id) 编号（cl_0001 恒为首个簇）
    assert cl["cluster_id"] == "cl_0001"