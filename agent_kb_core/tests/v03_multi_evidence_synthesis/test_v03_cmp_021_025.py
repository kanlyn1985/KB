# -*- coding: utf-8 -*-
"""V03-CMP-021..025：provider 边界/基数/向后兼容/无 authoritative 写/trace 确定性。"""
from __future__ import annotations

import json

import pytest


def test_v03_cmp_021_provider_boundary(db, compiled_evidence):
    # provider_id 记录在 run；裁决/治理面无 provider 参与
    eng = compiled_evidence["engine"]
    r = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    assert r["run"].provider_id == "builtin-synthesis"
    for c in (r["run"].conflicts or {}).get("conflicts", []):
        assert c["provider_id"] in (None, "builtin-synthesis")


def test_v03_cmp_022_multi_evidence_cardinality(db):
    from agent_kb.evidence_core import EvidenceStore
    from agent_kb.evidence_core.synthesis import EvidenceSetManager, SynthesisError
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('sc', 'document', 'SC')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at) VALUES ('dc', 'sc', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    store = EvidenceStore(db)
    mgr = EvidenceSetManager(db)
    eids = []
    for i in range(1, 35):
        ev = store.create(document_id="dc", content=f"证据编号 {i} 号内容。",
                          extraction_method="t")
        eids.append(ev.evidence_id)
    with pytest.raises(SynthesisError, match="E-V03-SET-TOO-LARGE"):
        mgr.create(eids, actor_id="system:synth")          # 34 > 32
    s = mgr.create(eids[:32], actor_id="system:synth")     # 32 = 上限合法
    assert len(s.members) == 32
    with pytest.raises(SynthesisError, match="E-V03-SET-EMPTY"):
        mgr.create([], actor_id="system:synth")


def test_v03_cmp_023_backward_compatibility(db, compiled_evidence):
    # V0.2 compile 行为零变化：同文本单证据编译产物与 synthesis 无关且幂等
    from agent_kb.evidence_core import EvidenceStore
    from agent_kb.evidence_core.compilation import SemanticCompiler
    store = EvidenceStore(db)
    comp = SemanticCompiler(db)
    ev = store.create(document_id="d1", content="OBC 额定输入电压 265V。", extraction_method="t")
    r1 = comp.compile(ev.evidence_id, actor_id="system:compiler")
    r2 = comp.compile(ev.evidence_id, actor_id="system:compiler")
    assert r2.idempotent_hit
    assert all(a.status == "candidate" for a in r1.assertions)


def test_v03_cmp_024_no_authoritative_write(db, compiled_evidence):
    from agent_kb.evidence_core.synthesis import SynthesisEngine
    eng = SynthesisEngine(db)
    eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    rows = db.execute("SELECT DISTINCT status FROM akb_assertions").fetchall()
    assert all(row["status"] == "candidate" for row in rows)
    # 直写 validated 被触发器拦截（V0.1 兜底）
    import sqlite3
    aid = db.execute("SELECT assertion_id FROM akb_assertions LIMIT 1").fetchone()["assertion_id"]
    with pytest.raises(sqlite3.Error):
        db.execute("UPDATE akb_assertions SET status='asserted' WHERE assertion_id=?", (aid,))


def test_v03_cmp_025_trace_determinism(db, compiled_evidence):
    eng = compiled_evidence["engine"]
    r = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    a0 = r["assertions"][0]
    aid = a0["assertion_id"] if isinstance(a0, dict) else a0.assertion_id
    t1 = eng.trace_candidate_synthesis(aid)
    t2 = eng.trace_candidate_synthesis(aid)
    assert {k: (dict(v) if isinstance(v, dict) else v) for k, v in t1.items()
            if k in ("members", "documents", "units")} == \
           {k: (dict(v) if isinstance(v, dict) else v) for k, v in t2.items()
            if k in ("members", "documents", "units")}
    assert len(t1["members"]) == 3  # 多成员父级正确