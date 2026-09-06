# -*- coding: utf-8 -*-
"""OC-CMP-001..010（AKB-V06-IMPL-002：Graph Reasoning Orchestrator acceptance）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.kgraph import (
    GraphContextBuilder,
    GraphOrchestrationError,
    GraphPersistenceService,
    GraphProjectionService,
    GraphQueryService,
    GraphReasoningOrchestrator,
)
from agent_kb.reasoning import (
    BuiltinRuleReasoner,
    ReasoningContext as V04Context,
    ReasoningEngine,
)


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con).migrate()
    yield con
    con.close()


def _seed_and_persist(db):
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
               " VALUES ('oc', 'document', 'OC')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at) VALUES ('doc', 'oc', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    store = EvidenceStore(db)
    comp = SemanticCompiler(db)
    eids = []
    for t in ["OBC 额定输入电压 265V。", "OBC 额定输入电压是 265V。"]:
        ev = store.create(document_id="doc", content=t, extraction_method="t")
        comp.compile(ev.evidence_id, actor_id="system:compiler")
        eids.append(ev.evidence_id)
    sr = SynthesisEngine(db).synthesize(eids, actor_id="system:synth")
    a_store = AssertionStore(db)
    s1 = a_store.create_candidate(
        subject_ref="OBC", predicate_ref="has_parameter",
        object={"kind": "literal", "value": "265V"}, assertion_type="extracted",
        ontology_scope="test", actor_id="system:seed", confidence=0.9,
        evidence_refs=[eids[0]])
    s2 = a_store.create_candidate(
        subject_ref="OBC", predicate_ref="has_parameter",
        object={"kind": "literal", "value": "265V"}, assertion_type="extracted",
        ontology_scope="test", actor_id="system:seed", confidence=0.8,
        evidence_refs=[eids[1]])
    d1 = a_store.create_candidate(
        subject_ref="MOT", predicate_ref="has_parameter",
        object={"kind": "literal", "value": "400V"}, assertion_type="extracted",
        ontology_scope="test", actor_id="system:seed", confidence=0.9,
        evidence_refs=[eids[0]])
    d2 = a_store.create_candidate(
        subject_ref="MOT", predicate_ref="has_parameter",
        object={"kind": "literal", "value": "410V"}, assertion_type="extracted",
        ontology_scope="test", actor_id="system:seed", confidence=0.85,
        evidence_refs=[eids[1]])
    # before 链（RR-02 可触发传递推理）
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
    eng = ReasoningEngine(db, provider=BuiltinRuleReasoner())
    rr = eng.reason([s1.assertion_id, s2.assertion_id, d1.assertion_id, d2.assertion_id,
                     ab.assertion_id, bc.assertion_id],
                    actor_id="system:reasoner", context=ReasoningContext("test"))
    proj = GraphProjectionService().process(db)
    pr = GraphPersistenceService(db).persist(proj)
    q = GraphQueryService(db)
    ent = next(n for n in q.query_nodes(node_type="entity", limit=1000)
               if n.payload.get("canonical_form") == "OBC")
    return {"proj": proj, "eids": eids, "persist": pr, "root": ent.node_id,
            "ab": ab, "bc": bc, "seeds": (s1, s2, d1, d2)}


def _snapshot(db):
    out = {}
    for t in ("kg_nodes", "kg_edges", "kg_projection_runs", "kg_invalidation_log"):
        out[t] = [tuple(r) for r in db.execute(f"SELECT * FROM {t} ORDER BY 1")]
    out["akb_provenance"] = [tuple(r) for r in db.execute(
        "SELECT * FROM akb_provenance ORDER BY provenance_id")]
    out["akb_assertions_count"] = db.execute(
        "SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
    return out


def test_oc_cmp_001_context_input(db):
    """OC-CMP-001：context 输入正确——orchestrator 接收 GraphReasoningContext 并消费
    input_assertions。"""
    s = _seed_and_persist(db)
    ctx = GraphContextBuilder().build(db, root_entity=s["root"])
    orch = GraphReasoningOrchestrator(db)
    with pytest.raises(GraphOrchestrationError, match="E-V06-INVALID-CONTEXT"):
        orch.run({"not": "a context"})
    r = orch.run(ctx)
    assert r["context_id"] == ctx.context_id
    assert r["status"] in ("completed", "partial")


def test_oc_cmp_002_engine_reuse(db):
    """OC-CMP-002：engine 复用验证——零新 ReasoningEngine（复用 V0.4 类 + 实例注入）。"""
    s = _seed_and_persist(db)
    ctx = GraphContextBuilder().build(db, root_entity=s["root"])
    # 默认路径：内部引擎 = V0.4 ReasoningEngine
    orch = GraphReasoningOrchestrator(db)
    assert isinstance(orch.engine, ReasoningEngine)
    # 注入路径：外部 V0.4 实例被原样复用（零包装/零重建）
    my_engine = ReasoningEngine(db, provider=BuiltinRuleReasoner())
    orch2 = GraphReasoningOrchestrator(db, engine=my_engine)
    assert orch2.engine is my_engine
    r = orch2.run(ctx)
    assert r["status"] in ("completed", "partial")
    # 无 LLM：默认 provider = deterministic BuiltinRuleReasoner
    assert isinstance(orch.engine.provider, BuiltinRuleReasoner)


def test_oc_cmp_003_deterministic_candidates(db):
    """OC-CMP-003：deterministic——同 context 双 run → 同 fingerprint/同候选集（幂等锚）。"""
    s = _seed_and_persist(db)
    ctx = GraphContextBuilder().build(db, root_entity=s["root"])
    orch = GraphReasoningOrchestrator(db)
    r1 = orch.run(ctx)
    r2 = orch.run(ctx)
    # V0.4 fingerprint 幂等锚：第二次 run 命中既有 run（零新候选）
    assert r1["fingerprint"] == r2["fingerprint"]
    c1 = sorted(a.assertion_id for a in r1["candidates"])
    c2 = sorted(a.assertion_id for a in r2["candidates"])
    assert c1 == c2
    # 候选 id 确定性：candidate 断言 id 由 V0.4 mint（事件溯源）——同库内稳定
    assert c1


def test_oc_cmp_004_derivation_chain_complete(db):
    """OC-CMP-004：derivation chain 完整——候选带 rule_ref/parents/run_id 六键。"""
    s = _seed_and_persist(db)
    ctx = GraphContextBuilder().build(db, root_entity=s["root"])
    r = GraphReasoningOrchestrator(db).run(ctx)
    assert r["candidates"], "fixture must yield candidates"
    for a in r["candidates"]:
        d = a.derivation
        for k in ("rule_ref", "parent_assertions", "reasoner_id",
                  "rule_input_snapshot", "confidence_basis", "depth"):
            assert d.get(k), (a.assertion_id, k)
        assert d.get("reasoning_run_id") == r["run_id"]
        # parent 可回溯到 akb_assertions
        for pid in d["parent_assertions"]:
            assert db.execute("SELECT 1 FROM akb_assertions WHERE assertion_id=?",
                              (pid,)).fetchone()


def test_oc_cmp_005_provenance_preserved(db):
    """OC-CMP-005：provenance 保留——context → run → candidate → assertion/evidence。"""
    s = _seed_and_persist(db)
    ctx = GraphContextBuilder().build(db, root_entity=s["root"])
    r = GraphReasoningOrchestrator(db).run(ctx)
    # graph:reason 审计落 akb_provenance（context_id + candidates + parents）
    rows = [dict(x) for x in db.execute(
        "SELECT * FROM akb_provenance WHERE activity='graph:reason'")]
    assert rows
    m = json.loads(rows[0]["metadata_json"])
    assert m["context_id"] == ctx.context_id
    assert m["graph_fingerprint"] == ctx.graph_fingerprint
    assert m["parent_assertions"] == sorted(ctx.input_assertions)
    # trace 携带推导对（candidate × parents）
    tr = r["trace"]
    assert tr.provenance_pairs if hasattr(tr, "provenance_pairs") else tr.provenance
    # context 自身 provenance 链完好（IMPL-001 语义）
    for p in ctx.provenance:
        assert db.execute("SELECT 1 FROM akb_assertions WHERE assertion_id=?",
                          (p.assertion_id,)).fetchone()


def test_oc_cmp_006_candidate_lifecycle(db):
    """OC-CMP-006：candidate lifecycle——候选恒 inferred/candidate；治理路径可达 validated。"""
    s = _seed_and_persist(db)
    ctx = GraphContextBuilder().build(db, root_entity=s["root"])
    r = GraphReasoningOrchestrator(db).run(ctx)
    assert r["candidates"]
    from agent_kb.evidence_core.assertions import AssertionValidator
    from agent_kb.evidence_core.state_machine import validate_transition
    for a in r["candidates"]:
        row = db.execute("SELECT assertion_type, status FROM akb_assertions"
                         " WHERE assertion_id=?", (a.assertion_id,)).fetchone()
        assert row["assertion_type"] == "inferred"
        assert row["status"] == "candidate"
        # 治理路径可达 validated（validator 通道——有 evidence 支撑时）
        v = validate_transition(current_status="candidate", new_status="validated",
                                assertion_type="inferred", actor_id="human:reviewer",
                                evidence_count=1)
        assert not any("E-ILLEGAL" in x for x in v)


def test_oc_cmp_007_inferred_protection(db):
    """OC-CMP-007：inferred 状态保护——inferred→asserted 仍禁止（V0.4 硬门延续）。"""
    s = _seed_and_persist(db)
    ctx = GraphContextBuilder().build(db, root_entity=s["root"])
    r = GraphReasoningOrchestrator(db).run(ctx)
    assert r["candidates"]
    from agent_kb.evidence_core.state_machine import validate_transition
    from agent_kb.evidence_core.assertions import Provenance  # noqa: F401
    for a in r["candidates"]:
        v = validate_transition(current_status="candidate", new_status="asserted",
                                assertion_type="inferred", actor_id="human:reviewer",
                                evidence_count=1)
        assert any("E-ILLEGAL-TRANSITION" in x for x in v)
        # orchestrator 零晋升动作：akb_assertions 无 asserted 状态的 inferred
        n = db.execute("SELECT COUNT(*) c FROM akb_assertions WHERE assertion_type="
                       "'inferred' AND status='asserted'").fetchone()["c"]
        assert n == 0


def test_oc_cmp_008_failure_fail_closed(db):
    """OC-CMP-008：failure fail-close——崩溃引擎 → run failed + graph:reason-failed
    审计 + 零候选。"""
    s = _seed_and_persist(db)
    ctx = GraphContextBuilder().build(db, root_entity=s["root"])
    class Crash:
        def reasoner_id(self):
            return "crash"
        def rule_version(self):
            return "v0"
        def infer(self, parents, ctx):
            raise RuntimeError("boom")
    orch = GraphReasoningOrchestrator(db, engine=ReasoningEngine(db, provider=Crash()))
    r = orch.run(ctx)
    assert r["status"] == "failed" and r["candidates"] == []
    rows = [dict(x) for x in db.execute(
        "SELECT * FROM akb_provenance WHERE activity='graph:reason-failed'")]
    assert rows and json.loads(rows[0]["metadata_json"])["context_id"] == ctx.context_id
    # 深度越界 fail-close
    big = ctx.query_constraints | {"hops": 9}
    from agent_kb.kgraph.context import GraphReasoningContext as GRC
    import hashlib
    from agent_kb.reasoning.models import canonical_json as cj
    payload = dict(ctx.canonical_payload())
    payload["hop"] = 9
    payload["query_constraints"] = big
    c2 = cj(payload)
    bad = GRC(context_id="grc_bad", fingerprint="x", root_entity=ctx.root_entity,
              graph_fingerprint=ctx.graph_fingerprint,
              input_nodes=ctx.input_nodes, input_assertions=ctx.input_assertions,
              input_edges=ctx.input_edges, temporal_context=ctx.temporal_context,
              status_filter=ctx.status_filter, query_constraints=big,
              rule_set_version=ctx.rule_set_version, provenance=ctx.provenance,
              hop=9)
    with pytest.raises(GraphOrchestrationError, match="E-V06-DEPTH-OVERFLOW"):
        GraphReasoningOrchestrator(db).run(bad)


def test_oc_cmp_009_no_llm_dependency(db):
    """OC-CMP-009：no LLM dependency——源码审计零 LLM 调用 + 默认 provider deterministic。"""
    import inspect
    from agent_kb.kgraph import orchestrator as orch_mod
    src = inspect.getsource(orch_mod)
    for kw in ("openai", "anthropic", "httpx", "requests.", "api_key", "completion"):
        assert kw not in src.lower() or kw == "completion" and "completion(" not in src
    s = _seed_and_persist(db)
    ctx = GraphContextBuilder().build(db, root_entity=s["root"])
    orch = GraphReasoningOrchestrator(db)
    assert isinstance(orch.engine.provider, BuiltinRuleReasoner)
    r = orch.run(ctx)
    assert r["status"] in ("completed", "partial")


def test_oc_cmp_010_v05_regression(db):
    """OC-CMP-010：V0.5 regression——orchestration 后图/查询面零变化（候选不入图）。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    v1 = q.canonical_view()
    ctx = GraphContextBuilder().build(db, root_entity=s["root"])
    before = _snapshot(db)
    r = GraphReasoningOrchestrator(db).run(ctx)
    v2 = q.canonical_view()
    assert v1 == v2                              # 候选不入 V0.5 图（零污染）
    after = _snapshot(db)
    # kg_* 五表零变化（新候选在 akb_assertions，不在 kg_nodes）
    for t in ("kg_nodes", "kg_edges", "kg_projection_runs", "kg_invalidation_log",
              "akb_provenance"):
        if t == "akb_provenance":
            # graph:reason 审计新增是预期（provenance 保留语义）——kg 面仍零变化
            continue
        assert before[t] == after[t], t
    # 重跑 query 一致（determinism 延续）
    assert q.canonical_view() == v2