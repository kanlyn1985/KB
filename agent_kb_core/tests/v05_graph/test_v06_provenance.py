# -*- coding: utf-8 -*-
"""PC-CMP-001..010（AKB-V06-IMPL-003：Provenance Closure acceptance）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.kgraph import (
    GraphContextBuilder,
    GraphPersistenceService,
    GraphProjectionService,
    GraphQueryService,
    GraphReasoningOrchestrator,
    ProvenanceClosureError,
    ReasoningProvenanceService,
)


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con).migrate()
    yield con
    con.close()


def _seed_reason(db):
    """P fixture：完整链 → context → orchestration（候选含 RR-02 传递推理）。"""
    from agent_kb.evidence_core import EvidenceStore
    from agent_kb.evidence_core.assertions import AssertionStore
    from agent_kb.evidence_core.compilation import SemanticCompiler
    from agent_kb.evidence_core.synthesis import SynthesisEngine
    from agent_kb.reasoning import (
        BuiltinRuleReasoner,
        ReasoningContext,
        ReasoningEngine,
    )
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('pc', 'document', 'PC')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at) VALUES ('dpc', 'pc', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    store = EvidenceStore(db)
    comp = SemanticCompiler(db)
    eids = []
    for t in ["OBC 额定输入电压 265V。", "流程 T1 先于流程 T2 执行。"]:
        ev = store.create(document_id="dpc", content=t, extraction_method="t")
        comp.compile(ev.evidence_id, actor_id="system:compiler")
        eids.append(ev.evidence_id)
    sr = SynthesisEngine(db).synthesize(eids, actor_id="system:synth")
    a_store = AssertionStore(db)
    ab = a_store.create_candidate(
        subject_ref="T1", predicate_ref="before",
        object={"kind": "literal", "value": "T2"}, assertion_type="extracted",
        ontology_scope="test", actor_id="system:seed", confidence=0.9,
        evidence_refs=[eids[0]])
    bc = a_store.create_candidate(
        subject_ref="T2", predicate_ref="before",
        object={"kind": "literal", "value": "T3"}, assertion_type="extracted",
        ontology_scope="test", actor_id="system:seed", confidence=0.9,
        evidence_refs=[eids[1]])
    proj = GraphProjectionService().process(db)
    pr = GraphPersistenceService(db).persist(proj)
    ctx = GraphContextBuilder().build(
        db, root_entity=next(
            n.node_id for n in GraphQueryService(db).query_nodes(
                node_type="entity", limit=1000)
            if n.payload.get("canonical_form") in ("T1", "T2", "T3")))
    orch = GraphReasoningOrchestrator(db)
    r = orch.run(ctx)
    assert r["candidates"], "fixture must yield candidates (RR-02)"
    svc = ReasoningProvenanceService(db)
    return {"ctx": ctx, "run": r, "eids": eids, "svc": svc, "ab": ab, "bc": bc}


def test_pc_cmp_001_context_provenance_kept(db):
    """PC-CMP-001：context provenance 保留——context 的 assertion→evidence→document
    链在 orchestration 后完好。"""
    s = _seed_reason(db)
    for p in s["ctx"].provenance:
        assert db.execute("SELECT 1 FROM akb_assertions WHERE assertion_id=?",
                          (p.assertion_id,)).fetchone()
        assert p.evidence_ids and p.document_ids
        for eid in p.evidence_ids:
            assert db.execute("SELECT 1 FROM akb_evidence WHERE evidence_id=?",
                              (eid,)).fetchone()


def test_pc_cmp_002_reasoning_run_traceable(db):
    """PC-CMP-002：reasoning run 可追溯——trace_run 返回 context/run/status/parents。"""
    s = _seed_reason(db)
    tr = s["svc"].trace_run(s["run"]["run_id"])
    assert tr.context_id == s["ctx"].context_id
    assert tr.reasoning_run_id == s["run"]["run_id"]
    assert tr.graph_fingerprint == s["ctx"].graph_fingerprint
    assert tr.parent_assertion_ids == tuple(sorted(s["ctx"].input_assertions))
    assert tr.audit_refs


def test_pc_cmp_003_candidate_chain_complete(db):
    """PC-CMP-003：candidate chain 完整——六要素（conclusion/rule/run/context/
    parents/status）。"""
    s = _seed_reason(db)
    for a in s["run"]["candidates"]:
        cp = s["svc"].trace_candidate(a.assertion_id)
        assert cp.conclusion and cp.rule_ref and cp.reasoning_run_id
        assert cp.context_id == s["ctx"].context_id
        assert cp.parent_assertion_ids
        assert cp.status == "candidate" and cp.assertion_type == "inferred"


def test_pc_cmp_004_evidence_backtrack(db):
    """PC-CMP-004：evidence 回溯——候选 → parents → evidence 全可解析。"""
    s = _seed_reason(db)
    for a in s["run"]["candidates"]:
        cp = s["svc"].trace_candidate(a.assertion_id)
        assert cp.evidence_ids
        for eid in cp.evidence_ids:
            assert db.execute("SELECT 1 FROM akb_evidence WHERE evidence_id=?",
                              (eid,)).fetchone()


def test_pc_cmp_005_document_backtrack(db):
    """PC-CMP-005：document 回溯——evidence → document 全可解析。"""
    s = _seed_reason(db)
    for a in s["run"]["candidates"]:
        cp = s["svc"].trace_candidate(a.assertion_id)
        assert cp.document_ids
        for did in cp.document_ids:
            assert db.execute("SELECT 1 FROM akb_documents WHERE document_id=?",
                              (did,)).fetchone()


def test_pc_cmp_006_missing_provenance_fail_closed(db):
    """PC-CMP-006：missing provenance → fail-closed（不 fabricate）。"""
    s = _seed_reason(db)
    svc = s["svc"]
    cand = s["run"]["candidates"][0]
    # ①schema 层 fail-closed：inferred 断言 derivation_json NOT NULL（V0.4 CHECK
    #   约束）——数据库层直接拒绝缺 derivation 的状态（更强的保护）
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint"):
        db.execute("UPDATE akb_assertions SET derivation_json=NULL"
                   " WHERE assertion_id=?", (cand.assertion_id,))
    # ②删除 run 记录
    db.execute("UPDATE akb_assertions SET derivation_json=? WHERE assertion_id=?",
               (json.dumps({"rule_ref": "RR-02", "parent_assertions":
                            [s["ab"].assertion_id, s["bc"].assertion_id],
                            "reasoning_run_id": "rrn_ghost"}), cand.assertion_id))
    with pytest.raises(ProvenanceClosureError, match="E-V06-PROVENANCE-MISSING"):
        svc.trace_candidate(cand.assertion_id)
    # ③不存在的 run trace
    with pytest.raises(ProvenanceClosureError, match="E-V06-PROVENANCE-MISSING"):
        svc.trace_run("rrn_ghost")
    # ④不存在的候选
    with pytest.raises(ProvenanceClosureError, match="E-V06-PROVENANCE-MISSING"):
        svc.trace_candidate("ast_ghost")
    # ⑤非 inferred 候选拒绝
    with pytest.raises(ProvenanceClosureError, match="E-V06-NOT-INFERRED"):
        svc.trace_candidate(s["ab"].assertion_id)


def test_pc_cmp_007_deterministic_trace(db):
    """PC-CMP-007：deterministic trace——同状态双查询全等（canonical 排序）。"""
    s = _seed_reason(db)
    svc = s["svc"]
    cand = s["run"]["candidates"][0]
    c1 = svc.trace_candidate(cand.assertion_id)
    c2 = svc.trace_candidate(cand.assertion_id)
    assert c1 == c2
    t1 = svc.trace_run(s["run"]["run_id"])
    t2 = svc.trace_run(s["run"]["run_id"])
    assert t1 == t2
    assert [c.candidate_assertion_id for c in t1.candidates] == \
        sorted(c.candidate_assertion_id for c in t1.candidates)


def test_pc_cmp_008_rollback_error_trace(db):
    """PC-CMP-008：rollback/error trace——failed run 的 graph:reason-failed 审计可查。"""
    s = _seed_reason(db)
    class Crash:
        def reasoner_id(self):
            return "crash"
        def rule_version(self):
            return "v0"
        def infer(self, parents, ctx):
            raise RuntimeError("boom")
    from agent_kb.reasoning import ReasoningEngine
    orch = GraphReasoningOrchestrator(db, engine=ReasoningEngine(db, provider=Crash()))
    r = orch.run(s["ctx"])
    assert r["status"] == "failed"
    rows = [dict(x) for x in db.execute(
        "SELECT * FROM akb_provenance WHERE activity='graph:reason-failed'")]
    assert rows
    m = json.loads(rows[0]["metadata_json"])
    assert m["context_id"] == s["ctx"].context_id
    assert any("E-V06-ENGINE-FAILED" in e for e in m["errors"])
    # verify_closure 对空 run（无候选）闭环（零候选 = 无 gap）
    # failed run 无 run 行或 run failed——verify_closure 按审计路径仍可解释
    v = s["svc"].verify_closure(s["run"]["run_id"])
    assert v["closed"] is True


def test_pc_cmp_009_inferred_lifecycle_protection(db):
    """PC-CMP-009：inferred lifecycle protection——候选恒 candidate；→asserted 禁；
    →validated 治理路径开放。"""
    s = _seed_reason(db)
    from agent_kb.evidence_core.state_machine import validate_transition
    for a in s["run"]["candidates"]:
        row = db.execute("SELECT assertion_type, status FROM akb_assertions"
                         " WHERE assertion_id=?", (a.assertion_id,)).fetchone()
        assert row["assertion_type"] == "inferred" and row["status"] == "candidate"
        v = validate_transition(current_status="candidate", new_status="asserted",
                                assertion_type="inferred", actor_id="human:reviewer",
                                evidence_count=1)
        assert any("E-ILLEGAL-TRANSITION" in x for x in v)
    # provenance 面不改变生命周期：trace 后 status 仍 candidate
    cand = s["run"]["candidates"][0]
    s["svc"].trace_candidate(cand.assertion_id)
    assert db.execute("SELECT status FROM akb_assertions WHERE assertion_id=?",
                      (cand.assertion_id,)).fetchone()["status"] == "candidate"


def test_pc_cmp_010_v05_regression(db):
    """PC-CMP-010：V0.5 regression——provenance 面只读（图/查询/五表零变化）。"""
    s = _seed_reason(db)
    q = GraphQueryService(db)
    v1 = q.canonical_view()
    before = {t: [tuple(r) for r in db.execute(f"SELECT * FROM {t}")]
              for t in ("kg_nodes", "kg_edges", "kg_projection_runs",
                        "kg_invalidation_log")}
    svc = s["svc"]
    for a in s["run"]["candidates"]:
        svc.trace_candidate(a.assertion_id)
    svc.trace_run(s["run"]["run_id"])
    svc.verify_closure(s["run"]["run_id"])
    v2 = q.canonical_view()
    after = {t: [tuple(r) for r in db.execute(f"SELECT * FROM {t}")]
             for t in ("kg_nodes", "kg_edges", "kg_projection_runs",
                       "kg_invalidation_log")}
    assert v1 == v2 and before == after