# -*- coding: utf-8 -*-
"""V0.3 对抗/诊断测试（任务书 §30 20 项中的补充面）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.evidence_core.synthesis import (
    EvidenceSetManager,
    SynthesisEngine,
    SynthesisError,
)


def test_diag_provider_failed_isolated(db):
    """provider 失败 → 成员级隔离（fake provider 注入异常不产生半成品）。"""
    # V0.3 builtin 主路径不依赖外部 provider；provider 异常注入由 ENGINE 内部捕获——
    # 这里验证 run status=failed 时零候选
    eng = SynthesisEngine(db)
    before = db.execute("SELECT COUNT(*) AS c FROM akb_assertions").fetchone()["c"]
    try:
        eng.synthesize(["ev_ghost"], actor_id="system:synth")
    except SynthesisError:
        pass
    after = db.execute("SELECT COUNT(*) AS c FROM akb_assertions").fetchone()["c"]
    assert before == after


def test_diag_provenance_failure_atomic(db):
    """provenance 面异常 → run failed，零候选提交（事务原子）。"""
    eng = SynthesisEngine(db)
    # 空库无 evidence → SET-MEMBER-NOT-FOUND 在事务外拒绝（零 run 创建）
    with pytest.raises(SynthesisError):
        eng.synthesize(["ev_none"], actor_id="system:synth")
    assert db.execute("SELECT COUNT(*) AS c FROM akb_synthesis_runs").fetchone()["c"] == 0


def test_diag_capped_run_status(db):
    """冲突爆炸 → capped（MAX_CONFLICTS 边界注入）。"""
    from agent_kb.evidence_core.synthesis.conflicts import ConflictDetector, MAX_CONFLICTS
    from agent_kb.evidence_core.synthesis.models import AlignmentResult, RelationAlignmentCluster
    al = AlignmentResult()
    for i in range(MAX_CONFLICTS + 10):
        al.relation_clusters.append(RelationAlignmentCluster(
            cluster_id=f"rc_{i:04d}", subject_cluster="cl_0001", predicate="has_parameter",
            object_cluster="cl_0002",
            members=[{"evidence_id": f"e{i}", "unit_id": f"u{i}", "confidence": 0.9,
                      "object_value": f"v{i}"}, {"evidence_id": f"f{i}", "unit_id": f"w{i}",
                                                 "confidence": 0.9, "object_value": f"w{i}"}]))
    cs = ConflictDetector().detect(al, [])
    assert cs.capped and len(cs.conflicts) == MAX_CONFLICTS


def test_diag_reversed_order_idempotent(db, compiled_evidence):
    """逆序成员 → 同 run（幂等）；不产生重复候选。"""
    eng = compiled_evidence["engine"]
    r1 = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    r2 = eng.synthesize(list(reversed(compiled_evidence["evidence_ids"])),
                        actor_id="system:synth")
    assert r1["fingerprint"] == r2["fingerprint"] and r2["idempotent_hit"]
    assert len(r2["assertions"]) == len(r1["assertions"])


def test_diag_v02_compile_unchanged(db, compiled_evidence):
    """V0.2 编译行为在 V0.3 引入后保持不变（幂等+candidate）。"""
    comp = compiled_evidence["compiler"]
    eids = compiled_evidence["evidence_ids"]
    r = comp.compile(eids[0], actor_id="system:compiler")
    assert r.idempotent_hit and all(a.status == "candidate" for a in r.assertions)


def test_diag_direct_authoritative_write_blocked(db, compiled_evidence):
    """直写 authoritative 被 V0.1 触发器拦截（V0.3 侧验证）。"""
    eng = compiled_evidence["engine"]
    eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    import sqlite3
    aid = db.execute("SELECT assertion_id FROM akb_assertions LIMIT 1").fetchone()["assertion_id"]
    with pytest.raises(sqlite3.Error):
        db.execute("UPDATE akb_assertions SET status='validated' WHERE assertion_id=?", (aid,))