# -*- coding: utf-8 -*-
"""V03-CMP-016..020：candidate-only/provenance/确定性/幂等/失败隔离。"""
from __future__ import annotations

import json

import pytest


def test_v03_cmp_016_candidate_only(db, compiled_evidence):
    eng = compiled_evidence["engine"]
    r = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    rows = db.execute(
        "SELECT status FROM akb_assertions WHERE derivation_json LIKE ?",
        (f'%{r["run"].run_id}%',)).fetchall()
    assert rows and all(row["status"] == "candidate" for row in rows)


def test_v03_cmp_017_provenance_completeness(db, compiled_evidence):
    eng = compiled_evidence["engine"]
    r = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    a0 = r["assertions"][0]
    aid = a0["assertion_id"] if isinstance(a0, dict) else a0.assertion_id
    tr = eng.trace_candidate_synthesis(aid)
    assert tr["run"] and tr["set"] and tr["members"] and tr["documents"]
    assert set(tr["members"]) == set(compiled_evidence["evidence_ids"])
    assert len(tr["units"]) >= len(tr["members"])  # 每成员至少 1 unit


def test_v03_cmp_018_determinism(db, compiled_evidence):
    eng = compiled_evidence["engine"]
    r1 = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    r2 = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    assert r1["fingerprint"] == r2["fingerprint"] and r2["idempotent_hit"]
    # 语义快照全等（排除审计字段）
    def sem(run):
        return {"alignment": run.alignment, "conflicts": run.conflicts,
                "weights": run.weights, "members": run.members}
    assert sem(r1["run"]) == sem(r2["run"])


def test_v03_cmp_019_idempotent_replay(db, compiled_evidence):
    eng = compiled_evidence["engine"]
    r1 = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    n1 = db.execute("SELECT COUNT(*) AS c FROM akb_assertions").fetchone()["c"]
    r2 = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    assert r2["idempotent_hit"]
    assert len(r2["assertions"]) == len(r1["assertions"])
    n2 = db.execute("SELECT COUNT(*) AS c FROM akb_assertions").fetchone()["c"]
    assert n1 == n2  # 无第二 create_candidate
    runs = db.execute("SELECT COUNT(*) AS c FROM akb_synthesis_runs").fetchone()["c"]
    assert runs == 1  # 无重复 run


def test_v03_cmp_020_failure_isolation(db, compiled_evidence):
    # 缺 unit 成员 → run failed；既有产物零破坏
    eng = compiled_evidence["engine"]
    r0 = eng.synthesize(compiled_evidence["evidence_ids"][:2], actor_id="system:synth")
    before = db.execute("SELECT COUNT(*) AS c FROM akb_assertions").fetchone()["c"]
    from agent_kb.evidence_core import EvidenceStore
    ev = compiled_evidence["store"].create(document_id="d1", content="新证据 无编译。",
                                           extraction_method="t")
    from agent_kb.evidence_core.synthesis import E_ALIGN_UNIT_MISSING, SynthesisError
    with pytest.raises(SynthesisError) as ei:
        eng.synthesize(compiled_evidence["evidence_ids"][:2] + [ev.evidence_id],
                       actor_id="system:synth")
    assert ei.value.code == E_ALIGN_UNIT_MISSING
    # 失败 run 留痕但零候选
    failed = db.execute(
        "SELECT status FROM akb_synthesis_runs WHERE status='failed'").fetchone()
    assert failed is not None
    after = db.execute("SELECT COUNT(*) AS c FROM akb_assertions").fetchone()["c"]
    assert after == before