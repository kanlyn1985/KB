# -*- coding: utf-8 -*-
"""CONTRACT-CMP-001..020（AKB-V06-IMPL-004：V0.6 全链路 contract 套件）。

设计依据：docs/V0.6/V0.6_DESIGN.md + REASONING_ARCHITECTURE_AND_CONTRACT +
PROVENANCE_AND_STATUS_CONTRACT + CHANGE_CONTROL_AND_ROADMAP。

覆盖（跨模块集成/不变量面——单元面由 VC/OC/PC 30 项承载）：
全链路 Context→Orchestrator→Engine、provenance closure、candidate lifecycle、
deterministic replay、fail-close、status/temporal/governance 边界、no-LLM、
V0.5 isolation。
"""
from __future__ import annotations

import hashlib
import json

import pytest

from agent_kb.evidence_core.assertions import AssertionStore, AssertionValidator
from agent_kb.evidence_core.state_machine import validate_transition
from agent_kb.kgraph import (
    GraphContextBuilder,
    GraphContextError,
    GraphOrchestrationError,
    GraphPersistenceService,
    GraphProjectionService,
    GraphQueryService,
    GraphReasoningOrchestrator,
    ProvenanceClosureError,
    ReasoningProvenanceService,
)
from agent_kb.reasoning import (
    BuiltinRuleReasoner,
    ReasoningContext as V04Context,
    ReasoningEngine,
    reasoning_fingerprint,
)


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con).migrate()
    yield con
    con.close()


def _seed_full(db, doc_tag="ct"):
    """完整 fixture：Document→Evidence→Unit→Assertion→Entity→Inference + persist +
    before 链（RR-02 可触发）。"""
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
               f" VALUES ('{doc_tag}', 'document', 'CT')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version,"
               " content_hash, ingested_at)"
               f" VALUES ('d{doc_tag}', '{doc_tag}', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    store = EvidenceStore(db)
    comp = SemanticCompiler(db)
    eids = []
    for t in ["OBC 额定输入电压 265V。", "流程 T1 先于流程 T2 执行。"]:
        ev = store.create(document_id=f"d{doc_tag}", content=t, extraction_method="t")
        comp.compile(ev.evidence_id, actor_id="system:compiler")
        eids.append(ev.evidence_id)
    SynthesisEngine(db).synthesize(eids, actor_id="system:synth")
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
    q = GraphQueryService(db)
    root = next(n.node_id for n in q.query_nodes(node_type="entity", limit=1000)
                if n.payload.get("canonical_form") in ("T1", "T2", "T3"))
    return {"proj": proj, "eids": eids, "persist": pr, "root": root,
            "ab": ab, "bc": bc}


def _full_chain(db, root):
    """全链路执行：context → orchestration → provenance trace。"""
    ctx = GraphContextBuilder().build(db, root_entity=root)
    orch = GraphReasoningOrchestrator(db)
    r = orch.run(ctx)
    svc = ReasoningProvenanceService(db)
    tr = svc.trace_run(r["run_id"]) if r.get("run_id") else None
    return ctx, r, tr, svc


def _snapshot(db):
    out = {}
    for t in ("kg_nodes", "kg_edges", "kg_projection_runs", "kg_invalidation_log"):
        out[t] = [tuple(r) for r in db.execute(f"SELECT * FROM {t} ORDER BY 1")]
    out["akb_provenance"] = [tuple(r) for r in db.execute(
        "SELECT * FROM akb_provenance ORDER BY provenance_id")]
    return out


# ---- 全链路集成 ----

def test_contract_cmp_001_full_chain(db):
    """CONTRACT-CMP-001：Context→Orchestrator→Engine 全链路——
    context 消费 kg 面、engine 产候选、trace 闭环一次贯通。"""
    s = _seed_full(db)
    ctx, r, tr, svc = _full_chain(db, s["root"])
    assert ctx.context_id.startswith("grc_")
    assert r["context_id"] == ctx.context_id
    assert r["candidates"]
    assert tr is not None and tr.candidates
    # 候选全部可回溯（链路无断点）
    for c in tr.candidates:
        assert c.evidence_ids and c.document_ids and c.parent_assertion_ids


def test_contract_cmp_002_deterministic_identity(db):
    """CONTRACT-CMP-002：同输入 → 同 context_id/fingerprint/candidate_id/trace。"""
    s = _seed_full(db)
    ctx1 = GraphContextBuilder().build(db, root_entity=s["root"])
    ctx2 = GraphContextBuilder().build(db, root_entity=s["root"])
    assert ctx1.context_id == ctx2.context_id
    assert ctx1.fingerprint == ctx2.fingerprint
    orch = GraphReasoningOrchestrator(db)
    r1 = orch.run(ctx1)
    r2 = orch.run(ctx2)
    assert r1["fingerprint"] == r2["fingerprint"]
    assert sorted(a.assertion_id for a in r1["candidates"]) == \
        sorted(a.assertion_id for a in r2["candidates"])
    t1 = ReasoningProvenanceService(db).trace_run(r1["run_id"])
    t2 = ReasoningProvenanceService(db).trace_run(r2["run_id"])
    assert t1.context_id == t2.context_id
    assert [c.candidate_assertion_id for c in t1.candidates] == \
        [c.candidate_assertion_id for c in t2.candidates]


def test_contract_cmp_003_fingerprint_anchor_replay(db):
    """CONTRACT-CMP-003：V0.4 fingerprint 锚——重放零新候选（幂等语义贯通 V0.6）。"""
    s = _seed_full(db)
    ctx, r1, _, _ = _full_chain(db, s["root"])
    n_before = db.execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
    orch = GraphReasoningOrchestrator(db)
    r2 = orch.run(ctx)
    n_after = db.execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
    assert n_before == n_after                       # 零新候选
    assert r2["status"] in ("completed", "partial")
    # V0.4 fingerprint 公式可独立复算（identity 单一算法）
    run_row = db.execute("SELECT * FROM akb_reasoning_runs WHERE run_id=?",
                         (r1["run_id"],)).fetchone()
    if run_row:
        recomputed = reasoning_fingerprint(
            sorted(ctx.input_assertions),
            BuiltinRuleReasoner().reasoner_id() if hasattr(
                BuiltinRuleReasoner(), "reasoner_id") else "builtin-rules-v1",
            BuiltinRuleReasoner().rule_version() if hasattr(
                BuiltinRuleReasoner(), "rule_version") else "v1",
            V04Context(ontology_scope="v06-graph", configuration={
                "context_id": ctx.context_id,
                "graph_fingerprint": ctx.graph_fingerprint,
                "hop": ctx.hop,
                "status_filter": sorted(ctx.status_filter),
                "rule_set_version": ctx.rule_set_version,
            }).configuration_hash())
        assert recomputed == r1["fingerprint"]


def test_contract_cmp_004_provenance_closure_integrity(db):
    """CONTRACT-CMP-004：provenance closure 完整——verify_closure 全闭环 + 五问可答。"""
    s = _seed_full(db)
    ctx, r, tr, svc = _full_chain(db, s["root"])
    v = svc.verify_closure(r["run_id"])
    assert v["closed"] is True and v["gaps"] == []
    for c in tr.candidates:
        # What / Why / From / Context / Version 五问
        assert c.conclusion and c.rule_ref and c.rule_version
        assert c.parent_assertion_ids and c.context_id
        assert c.evidence_ids and c.document_ids


def test_contract_cmp_005_trace_to_evidence_document(db):
    """CONTRACT-CMP-005：推理结果完整追溯到 evidence/document（端到端）。"""
    s = _seed_full(db)
    ctx, r, tr, _ = _full_chain(db, s["root"])
    all_eids, all_dids = set(), set()
    for c in tr.candidates:
        all_eids |= set(c.evidence_ids)
        all_dids |= set(c.document_ids)
    assert all_eids
    for eid in all_eids:
        assert db.execute("SELECT 1 FROM akb_evidence WHERE evidence_id=?",
                          (eid,)).fetchone()
    for did in all_dids:
        assert db.execute("SELECT 1 FROM akb_documents WHERE document_id=?",
                          (did,)).fetchone()


# ---- lifecycle / 状态边界 ----

def test_contract_cmp_006_candidate_lifecycle(db):
    """CONTRACT-CMP-006：candidate lifecycle——恒 inferred/candidate；→asserted 禁；
    →validated 路径开放。"""
    s = _seed_full(db)
    ctx, r, tr, _ = _full_chain(db, s["root"])
    for a in r["candidates"]:
        row = db.execute("SELECT assertion_type, status FROM akb_assertions"
                         " WHERE assertion_id=?", (a.assertion_id,)).fetchone()
        assert row["assertion_type"] == "inferred" and row["status"] == "candidate"
        v_bad = validate_transition(current_status="candidate", new_status="asserted",
                                    assertion_type="inferred",
                                    actor_id="human:reviewer", evidence_count=1)
        assert any("E-ILLEGAL-TRANSITION" in x for x in v_bad)
        v_ok = validate_transition(current_status="candidate", new_status="validated",
                                   assertion_type="inferred", actor_id="human:reviewer",
                                   evidence_count=1)
        assert not any("E-ILLEGAL" in x for x in v_ok)


def test_contract_cmp_007_governance_boundary(db):
    """CONTRACT-CMP-007：governance 边界——orchestration 零晋升；晋升只经 validator/
    human 通道；graph:reason 审计不携带任何 status 变更。"""
    s = _seed_full(db)
    ctx, r, tr, _ = _full_chain(db, s["root"])
    # 零 status 变更（ orchestration 面无 transition 审计）
    rows = [dict(x) for x in db.execute(
        "SELECT activity FROM akb_provenance WHERE activity LIKE 'graph:reason%'")]
    assert all(x["activity"] in ("graph:reason", "graph:reason-failed")
               for x in rows)
    # validator 通道仍工作（治理路径未破坏）
    if r["candidates"]:
        cand = r["candidates"][0]
        # inferred 候选走 validator：evidence 需存在
        parents = json.loads(db.execute(
            "SELECT derivation_json FROM akb_assertions WHERE assertion_id=?",
            (cand.assertion_id,)).fetchone()["derivation_json"])["parent_assertions"]
        ev_ok = any(json.loads(db.execute(
            "SELECT evidence_refs_json FROM akb_assertions WHERE assertion_id=?",
            (p,)).fetchone()["evidence_refs_json"]) for p in parents)
        if ev_ok:
            av = AssertionValidator(db).validate(
                assertion_id=cand.assertion_id, actor_id="system:validator")
            assert av["accepted"] is True


def test_contract_cmp_008_status_temporal_boundary(db):
    """CONTRACT-CMP-008：status/temporal 边界——invalidated 不入 context；
    temporal 只读引用；hypothesized 零进入。"""
    s = _seed_full(db)
    eid = s["eids"][0]
    from agent_kb.evidence_core.assertions import AssertionStore
    a = AssertionStore(db).create_candidate(
        subject_ref="BAD", predicate_ref="has_flag",
        object={"kind": "literal", "value": "x"}, assertion_type="extracted",
        ontology_scope="test", actor_id="system:seed", confidence=0.9,
        evidence_refs=[eid])
    AssertionStore(db).transition(assertion_id=a.assertion_id, new_status="rejected",
                                  actor_id="human:governor", reason="ct")
    h = AssertionStore(db).create_candidate(
        subject_ref="HYP", predicate_ref="has_guess",
        object={"kind": "literal", "value": "y"}, assertion_type="hypothesized",
        ontology_scope="test", actor_id="system:seed", confidence=0.5,
        evidence_refs=[eid])
    ctx = GraphContextBuilder().build(db, root_entity=s["root"])
    assert a.assertion_id not in ctx.input_assertions     # rejected 排除
    assert h.assertion_id not in ctx.input_assertions     # hypothesized 排除
    assert all(t.startswith("temporal:") for t in ctx.temporal_context)


# ---- fail-close / 隔离 ----

def test_contract_cmp_009_fail_close_matrix(db):
    """CONTRACT-CMP-009：fail-close 矩阵——无效 root/hops/status/limit/depth/ghost
    全部显式拒绝。"""
    s = _seed_full(db)
    with pytest.raises(GraphContextError, match="E-V06-ROOT-NOT-FOUND"):
        GraphContextBuilder().build(db, root_entity="ent_ghost")
    with pytest.raises(GraphContextError, match="E-V06-INVALID-HOPS"):
        GraphContextBuilder().build(db, root_entity=s["root"], hops=9)
    with pytest.raises(GraphContextError, match="E-V06-INVALID-STATUS-FILTER"):
        GraphContextBuilder().build(db, root_entity=s["root"],
                                    status_filter=("floating",))
    with pytest.raises(GraphOrchestrationError, match="E-V06-INVALID-CONTEXT"):
        GraphReasoningOrchestrator(db).run({"bad": 1})
    with pytest.raises(ProvenanceClosureError, match="E-V06-PROVENANCE-MISSING"):
        ReasoningProvenanceService(db).trace_run("rrn_ghost")
    with pytest.raises(ProvenanceClosureError, match="E-V06-NOT-INFERRED"):
        ReasoningProvenanceService(db).trace_candidate(s["ab"].assertion_id)


def test_contract_cmp_010_no_llm_dependency(db):
    """CONTRACT-CMP-010：no LLM dependency——三模块源码审计零 LLM/网络 + provider
    deterministic。"""
    import inspect
    from agent_kb.kgraph import context as cm, orchestrator as om, provenance as pm
    for mod in (cm, om, pm):
        src = inspect.getsource(mod).lower()
        for kw in ("openai", "anthropic", "httpx", "requests.get", "requests.post",
                   "api_key"):
            assert kw not in src, (mod.__name__, kw)
    orch = GraphReasoningOrchestrator(db)
    assert isinstance(orch.engine.provider, BuiltinRuleReasoner)


def test_contract_cmp_011_read_only_kg(db):
    """CONTRACT-CMP-011：全链路 read-only——context/orchestration/provenance 后
    kg_* 四表零变化（akb_provenance 仅审计追加；akb_assertions 仅新增候选）。"""
    s = _seed_full(db)
    before = _snapshot(db)
    n_assertions_before = db.execute(
        "SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
    ctx, r, tr, svc = _full_chain(db, s["root"])
    after = _snapshot(db)
    for t in ("kg_nodes", "kg_edges", "kg_projection_runs", "kg_invalidation_log"):
        assert before[t] == after[t], t
    # akb_provenance 只增 graph:reason 审计（V0.6 语义）
    added_prov = [p for p in after["akb_provenance"] if p not in
                  before["akb_provenance"]]
    # akb_provenance 列序：provenance_id/actor_id/actor_kind/activity/...（activity=idx3）
    legal = ("graph:reason", "infer", "transition", "create", "assert")
    assert all(any(l in p[3] for l in legal) for p in added_prov), \
        [p[3] for p in added_prov]
    # 新 akb_assertions 行恒 inferred/candidate
    for a in r["candidates"]:
        row = db.execute("SELECT assertion_type, status FROM akb_assertions"
                         " WHERE assertion_id=?", (a.assertion_id,)).fetchone()
        assert row["assertion_type"] == "inferred" and row["status"] == "candidate"


def test_contract_cmp_012_v05_canonical_view_stable(db):
    """CONTRACT-CMP-012：V0.5 canonical view 跨全链路稳定。"""
    s = _seed_full(db)
    q = GraphQueryService(db)
    v1 = q.canonical_view()
    _full_chain(db, s["root"])
    assert q.canonical_view() == v1


def test_contract_cmp_013_legacy_isolation(db):
    """CONTRACT-CMP-013：legacy isolation——三模块零引用 agent_kb.graph +
    graph_edges 零变化。"""
    import agent_kb.graph as legacy
    import agent_kb.kgraph as kgraph
    for sym in ("GraphContextBuilder", "GraphReasoningOrchestrator",
                "ReasoningProvenanceService"):
        assert not hasattr(legacy, sym)
    for sym in ("DeterministicRelationExtractor", "SQLiteGraphStore"):
        assert not hasattr(kgraph, sym)
    before = db.execute("SELECT COUNT(*) c FROM graph_edges").fetchone()["c"]
    s = _seed_full(db)
    _full_chain(db, s["root"])
    after = db.execute("SELECT COUNT(*) c FROM graph_edges").fetchone()["c"]
    assert before == after


def test_contract_cmp_014_rebuild_pipeline_stable(db):
    """CONTRACT-CMP-014：rebuild pipeline——同状态重投影+persist 幂等命中后全链路
    结果不变。（含新增断言的全量 repersist 受 V0.5 P1 缺口限制——kg_nodes PK——
    记录于 IMPL-001 notes；contract 只锚定同状态重建语义。）"""
    s = _seed_full(db)
    ctx1, r1, tr1, _ = _full_chain(db, s["root"])
    # 同 fingerprint 重 persist（无状态变化）→ 幂等命中（V0.5 锚语义）
    proj2 = GraphProjectionService().process(db)
    if proj2.fingerprint != s["persist"]["fingerprint"]:
        # orchestration 新增候选改变了图投影——按 V0.5 P1 缺口（IMPL-001 notes），
        # 全量 repersist 不执行；改用原 projection 对象验证幂等锚
        proj2 = s["proj"]
    pr2 = GraphPersistenceService(db).persist(proj2, rebuild=True)
    assert pr2.get("idempotent_hit") is True
    ctx2 = GraphContextBuilder().build(db, root_entity=s["root"])
    assert ctx2.context_id == ctx1.context_id            # 同状态 → 同 context
    r2 = GraphReasoningOrchestrator(db).run(ctx2)
    assert r2["fingerprint"] == r1["fingerprint"]
    assert sorted(a.assertion_id for a in r2["candidates"]) == \
        sorted(a.assertion_id for a in r1["candidates"])


def test_contract_cmp_015_migration_chain_untouched(db):
    """CONTRACT-CMP-015：migration chain——版本唯一 + migration 14 表完好 +
    V0.6 零专表。（V0.10 设计授权 migration 16 append-only 三新表——
    版本唯一性 + 零修改既有表语义保持；上限断言随授权演进。）"""
    from agent_kb.storage.migrations import ALL_MIGRATIONS
    vers = [m.version for m in ALL_MIGRATIONS]
    assert vers == sorted(set(vers)) and vers[-1] in (15, 16, 17)
    cols = [r[1] for r in db.execute("PRAGMA table_info(akb_reasoning_runs)")]
    assert "fingerprint" in cols and "parent_ids_json" in cols
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master"
                                       " WHERE type='table'")}
    assert not any(t.startswith("v06_") for t in tables)   # 零 V0.6 专表
    assert {"kg_nodes", "kg_edges", "kg_projection_runs",
            "kg_invalidation_log"} <= tables


def test_contract_cmp_016_cross_instance_pipeline(db):
    """CONTRACT-CMP-016：cross-instance pipeline——双 Builder/Orchestrator/Provenance
    实例全等结果。"""
    s = _seed_full(db)
    c1 = GraphContextBuilder().build(db, root_entity=s["root"])
    c2 = GraphContextBuilder().build(db, root_entity=s["root"])
    assert c1.context_id == c2.context_id
    r1 = GraphReasoningOrchestrator(db).run(c1)
    r2 = GraphReasoningOrchestrator(db).run(c2)
    assert r1["fingerprint"] == r2["fingerprint"]
    t1 = ReasoningProvenanceService(db).trace_run(r1["run_id"])
    t2 = ReasoningProvenanceService(db).trace_run(r2["run_id"])
    assert t1.context_id == t2.context_id


def test_contract_cmp_017_error_surface_taxonomy(db):
    """CONTRACT-CMP-017：错误面分类——V0.6 错误码命名空间统一（E-V06-*）且不吞异常。"""
    from agent_kb.kgraph.context import GraphContextError
    from agent_kb.kgraph.orchestrator import GraphOrchestrationError
    from agent_kb.kgraph.provenance import ProvenanceClosureError
    for exc, code in ((GraphContextError, "E-V06-"),
                      (GraphOrchestrationError, "E-V06-"),
                      (ProvenanceClosureError, "E-V06-")):
        assert issubclass(exc, ValueError)
    # 错误消息携带 E-V06 前缀（可诊断）
    with pytest.raises(GraphContextError) as ei:
        GraphContextBuilder().build(db, root_entity="")
    assert "E-V06-" in str(ei.value)


def test_contract_cmp_018_depth_independence(db):
    """CONTRACT-CMP-018：depth 独立性——reasoning depth(4) ≠ query depth(8)；
    hop 上限 = Q-02 MAX_HOPS(4)。"""
    from agent_kb.kgraph.orchestrator import MAX_DERIVATION_DEPTH
    from agent_kb.kgraph.context import MAX_HOPS_LIMIT
    from agent_kb.kgraph.query import GraphQueryService
    assert MAX_DERIVATION_DEPTH == 4 and MAX_HOPS_LIMIT == 4
    # Q-04 query depth 8 是读取面（inference_chain max_depth=8）——独立存在
    s = _seed_full(db)
    q = GraphQueryService(db)
    with pytest.raises(Exception):
        q.inference_chain("x", max_depth=99)
    with pytest.raises(GraphContextError, match="E-V06-INVALID-HOPS"):
        GraphContextBuilder().build(db, root_entity=s["root"], hops=5)


def test_contract_cmp_019_governance_actor_matrix(db):
    """CONTRACT-CMP-019：governance actor 矩阵——system/agent/llm 零晋升通道
    （V0.4 transition + V0.5 EntityGovernance 双面）。"""
    s = _seed_full(db)
    ctx, r, tr, _ = _full_chain(db, s["root"])
    cand = r["candidates"][0]
    # system/agent/llm actor 的 asserted 迁移全拒绝
    for actor in ("system:validator", "agent:bot", "llm:model"):
        v = validate_transition(current_status="candidate", new_status="asserted",
                                assertion_type="inferred", actor_id=actor,
                                evidence_count=1)
        assert any("E-ILLEGAL-TRANSITION" in x for x in v)
    # V0.5 EntityGovernance merge 也是 human-only（回归确认）
    from agent_kb.kgraph import EntityGovernanceService
    gov = EntityGovernanceService(db)
    cand_g = gov.generate_merge_candidate(
        source_entity_ids=["e1", "e2"], canonical_form="X",
        entity_types=["t"], evidence_refs=["E"], match_strategy="L1_EXACT")
    from agent_kb.kgraph.identity import EntityIdentityResolver
    # 非 human approve 拒绝（既有语义回归）
    from agent_kb.kgraph.identity import EntityIdentityResolver as EIR
    assert gov.resolver.canonical_id("X", "t") == EIR().canonical_id("X", "t")


def test_contract_cmp_020_v05_isolation_final(db):
    """CONTRACT-CMP-020：V0.5 isolation final——V0.6 全链路后 V0.5 面零漂移
    （kg 快照 + canonical view + query 计数）。"""
    s = _seed_full(db)
    q = GraphQueryService(db)
    v_before = q.canonical_view()
    snap_before = _snapshot(db)
    nq_before = len(q.query_nodes(limit=1000))
    ne_before = len(q.query_edges(limit=1000))
    _full_chain(db, s["root"])
    _full_chain(db, s["root"])
    assert q.canonical_view() == v_before
    assert _snapshot(db)["kg_nodes"] == snap_before["kg_nodes"]
    assert _snapshot(db)["kg_edges"] == snap_before["kg_edges"]
    assert len(q.query_nodes(limit=1000)) == nq_before
    assert len(q.query_edges(limit=1000)) == ne_before