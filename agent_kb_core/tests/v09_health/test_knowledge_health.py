# -*- coding: utf-8 -*-
"""KH-CMP-001..010（AKB-V09-IMPL-002：KnowledgeHealth Runtime acceptance）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.causal import CausalProjectionRuntime
from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.health import (
    KnowledgeHealthError,
    KnowledgeHealthRuntime,
)
from agent_kb.hypothesis import (
    HypothesisService,
    VerificationTaskRuntime,
    VerdictRuntime,
)
from agent_kb.storage.migrations import SchemaMigrator


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    SchemaMigrator(con).migrate()
    con.execute("INSERT INTO akb_sources (source_id, source_type, name)"
                " VALUES ('kh', 'document', 'KH')")
    con.execute("INSERT INTO akb_documents (document_id, source_id, version,"
                " content_hash, ingested_at) VALUES ('dkh', 'kh', '1.0', 'h',"
                " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    ev = EvidenceStore(con).create(document_id="dkh", content="因果锚证据。",
                                   extraction_method="t")
    yield con, ev.evidence_id
    con.close()


@pytest.fixture
def stack(db):
    con, eid = db
    st = AssertionStore(con)
    a = st.create_candidate(subject_ref="Heat", predicate_ref="causes",
                            object={"kind": "literal", "value": "Aging"},
                            assertion_type="extracted", ontology_scope="test",
                            actor_id="system:seed", confidence=0.9,
                            evidence_refs=[eid])
    proj = CausalProjectionRuntime(con).project()
    hs = HypothesisService(con)
    tr = VerificationTaskRuntime(con, hypothesis_service=hs)
    vr = VerdictRuntime(con, hypothesis_service=hs, task_runtime=tr)
    kh = KnowledgeHealthRuntime(con, causal_runtime=CausalProjectionRuntime(con))
    return {"st": st, "a": a, "eid": eid, "proj": proj, "hs": hs, "tr": tr,
            "vr": vr, "kh": kh}


def test_kh_cmp_001_create_health(db, stack):
    """KH-CMP-001：create health——全字段 immutable + status/score 聚合。"""
    con, eid = db
    h = stack["kh"].create_health(target_ref=stack["a"].assertion_id,
                                  target_type="assertion")
    assert h.health_id.startswith("khs_")
    assert h.target_ref == stack["a"].assertion_id
    assert h.target_type == "assertion"
    assert {s["type"] for s in h.signals} == {"stability", "verification",
                                              "conflict", "causal_coverage"}
    assert 0.0 <= h.score <= 1.0 and h.status in ("healthy", "watch", "degraded")
    assert len(h.fingerprint) == 16       # canonical hash 截断（无时间戳）


def test_kh_cmp_002_deterministic_identity(db, stack):
    """KH-CMP-002：deterministic identity——同状态双实例同 health_id/fingerprint。"""
    h1 = stack["kh"].create_health(target_ref=stack["a"].assertion_id)
    h2 = KnowledgeHealthRuntime(db[0], causal_runtime=CausalProjectionRuntime(
        db[0])).create_health(target_ref=stack["a"].assertion_id)
    assert h1.health_id == h2.health_id
    assert h1.fingerprint == h2.fingerprint


def test_kh_cmp_003_same_snapshot_rebuild(db, stack):
    """KH-CMP-003：same snapshot rebuild——同（target+snapshot+causal+provenance）
    → 同 health_id（Rule 3）。"""
    h1 = stack["kh"].create_health(target_ref=stack["a"].assertion_id)
    proj2 = CausalProjectionRuntime(db[0]).project()
    h2 = KnowledgeHealthRuntime(db[0], causal_runtime=CausalProjectionRuntime(
        db[0])).create_health(target_ref=stack["a"].assertion_id,
                              causal_projection=proj2)
    assert h1.health_id == h2.health_id


def test_kh_cmp_004_stability_signal(db, stack):
    """KH-CMP-004：stability signal——transition 审计计数单调递减稳定性。"""
    h1 = stack["kh"].create_health(target_ref=stack["a"].assertion_id)
    s1 = {s["type"]: s for s in h1.signals}["stability"]
    v1 = s1["value"]
    # 断言失效 → transition 审计增加 → stability 下降
    stack["st"].transition(assertion_id=stack["a"].assertion_id,
                           new_status="rejected",
                           actor_id="human:reviewer", reason="kh")
    h2 = stack["kh"].create_health(target_ref=stack["a"].assertion_id)
    s2 = {s["type"]: s for s in h2.signals}["stability"]
    assert s2["value"] < v1
    assert "transitions=" in s2["detail"]


def test_kh_cmp_005_verification_signal(db, stack):
    """KH-CMP-005：verification signal——hypothesis/verdict 关联计数。"""
    hyp = stack["hs"].create_hypothesis(
        statement="H: Heat causes Aging 关联验证", domain_ref="industrial",
        pack_ref="dpr_a", policy_ref="pol_b", context_ref="grc_c",
        origin="human")
    task = stack["tr"].create_task(hypothesis_id=hyp.hypothesis_id,
                                   task_type="evidence_review",
                                   spec="验证 Heat→Aging",
                                   evidence_requirements=(stack["eid"],))
    stack["tr"].start_task(task.task_id, actor_id="human:reviewer")
    stack["tr"].complete_task(task.task_id, actor_id="human:reviewer")
    # verdict metadata 携带 target（statement 含 Heat causes Aging）
    stack["vr"].create_verdict(hypothesis_id=hyp.hypothesis_id,
                               task_id=task.task_id, result="supported",
                               evidence_refs=(stack["eid"],))
    # 关联语义：verdict 的 hypothesis statement 含目标名 Heat（同 verification
    # runtime 侧匹配 target 名——确定性文本关联）
    h2 = stack["kh"].create_health(target_ref="Heat", target_type="entity")
    s2 = {s["type"]: s for s in h2.signals}["verification"]
    assert s2["value"] >= 1 and "verdicts=" in s2["detail"]


def test_kh_cmp_006_causal_coverage_signal(db, stack):
    """KH-CMP-006：causal coverage signal——目标在 CausalProjection 的边数。"""
    # assertion id 不在因果边（causal 边端点是 subject/object 值）——
    # 以目标值视角查询（Heat 在投影 source 侧）
    proj = stack["proj"]
    edge_heat = [e for e in proj.causal_edges if e.source_ref == "Heat"]
    assert edge_heat, "fixture must have Heat causal edge"
    # 通过 statement 关联：verification 信号已验；此处验证 coverage 信号结构
    h = stack["kh"].create_health(target_ref=stack["a"].assertion_id)
    s = {s["type"]: s for s in h.signals}["causal_coverage"]
    assert "causal_edges=" in s["detail"] and s["value"] >= 0
    # 直接覆盖：以 Heat（投影内 source）为目标
    h2 = stack["kh"].create_health(target_ref="Heat", target_type="entity")
    s2 = {s["type"]: s for s in h2.signals}["causal_coverage"]
    assert s2["value"] >= 1


def test_kh_cmp_007_health_not_mutation(db, stack):
    """KH-CMP-007：health ≠ mutation——akb_assertions/kg_* unchanged
    （Health ≠ Truth ≠ Mutation）。"""
    con = db[0]
    snap = {t: [tuple(r) for r in con.execute(f"SELECT * FROM {t} ORDER BY 1")]
            for t in ("akb_assertions", "kg_nodes", "kg_edges")}
    n_n = con.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"]
    stack["kh"].create_health(target_ref=stack["a"].assertion_id)
    stack["kh"].create_health(target_ref="Heat", target_type="entity")
    assert snap["akb_assertions"] == [
        tuple(r) for r in con.execute("SELECT * FROM akb_assertions ORDER BY 1")]
    assert snap["kg_nodes"] == [
        tuple(r) for r in con.execute("SELECT * FROM kg_nodes ORDER BY 1")]
    assert snap["kg_edges"] == [
        tuple(r) for r in con.execute("SELECT * FROM kg_edges ORDER BY 1")]
    assert con.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"] == n_n


def test_kh_cmp_008_provenance_audit(db, stack):
    """KH-CMP-008：provenance audit——graph:knowledge-health-create 落
    akb_provenance（health_id/target/signals/score/fingerprint）。"""
    h = stack["kh"].create_health(target_ref=stack["a"].assertion_id)
    rows = [dict(x) for x in db[0].execute(
        "SELECT * FROM akb_provenance WHERE"
        " activity='graph:knowledge-health-create'")]
    assert len(rows) == 1
    m = json.loads(rows[0]["metadata_json"])
    assert m["health_id"] == h.health_id
    assert m["target_ref"] == stack["a"].assertion_id
    assert m["score"] == h.score and m["fingerprint"] == h.fingerprint


def test_kh_cmp_009_immutable_health(db, stack):
    """KH-CMP-009：immutable health object——frozen dataclass 赋值拒绝 +
    幂等（重复 create 零重复审计）。"""
    h = stack["kh"].create_health(target_ref=stack["a"].assertion_id)
    with pytest.raises(Exception):
        h.score = 0.99  # type: ignore[misc]
    n1 = db[0].execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                       " activity='graph:knowledge-health-create'").fetchone()["c"]
    stack["kh"].create_health(target_ref=stack["a"].assertion_id)
    n2 = db[0].execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                       " activity='graph:knowledge-health-create'").fetchone()["c"]
    assert n1 == n2


def test_kh_cmp_010_frozen_regression(db, stack):
    """KH-CMP-010：frozen regression——V0.5..V0.9causal frozen 模块零感知
    （单向依赖）+ legacy 零引用 + 建图回归。"""
    import inspect
    import agent_kb.graph as legacy
    import agent_kb.kgraph.orchestrator as m1
    import agent_kb.kgraph.context as m2
    import agent_kb.domains.runtime as m3
    import agent_kb.rules.runtime as m4
    import agent_kb.policy.runtime as m5
    import agent_kb.domains.guard as m6
    import agent_kb.hypothesis.runtime as m7
    import agent_kb.hypothesis.verification as m8
    import agent_kb.hypothesis.verdict as m9
    import agent_kb.hypothesis.evolution as m10
    import agent_kb.causal.projection as m11
    for mod in (m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11):
        assert "KnowledgeHealthRuntime" not in inspect.getsource(mod)
    for sym in ("KnowledgeHealthRuntime", "KnowledgeHealth"):
        assert not hasattr(legacy, sym)
    # 建图回归：health 活动后投影/查询面不变
    from agent_kb.kgraph import (
        GraphPersistenceService, GraphProjectionService, GraphQueryService)
    con = db[0]
    GraphPersistenceService(con).persist(GraphProjectionService().process(con))
    q = GraphQueryService(con)
    v1 = q.canonical_view()
    stack["kh"].create_health(target_ref=stack["a"].assertion_id)
    assert q.canonical_view() == v1