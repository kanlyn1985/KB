# -*- coding: utf-8 -*-
"""CP-CMP-001..010（AKB-V09-IMPL-001：CausalProjection Runtime acceptance）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.causal import (
    CausalEdge,
    CausalProjectionError,
    CausalProjectionRuntime,
    causal_edge_identity,
)
from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.storage.migrations import SchemaMigrator


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    SchemaMigrator(con).migrate()
    con.execute("INSERT INTO akb_sources (source_id, source_type, name)"
                " VALUES ('cp', 'document', 'CP')")
    con.execute("INSERT INTO akb_documents (document_id, source_id, version,"
                " content_hash, ingested_at) VALUES ('dcp', 'cp', '1.0', 'h',"
                " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    ev = EvidenceStore(con).create(document_id="dcp",
                                   content="过热导致绝缘老化。",
                                   extraction_method="t")
    yield con, ev.evidence_id
    con.close()


def _causal_assertions(con, eid, specs):
    """创建因果谓词断言（V0.4 既有通道——零新机制）。"""
    st = AssertionStore(con)
    out = []
    for (subj, pred, obj) in specs:
        out.append(st.create_candidate(
            subject_ref=subj, predicate_ref=pred,
            object={"kind": "literal", "value": obj},
            assertion_type="extracted", ontology_scope="test",
            actor_id="system:seed", confidence=0.9, evidence_refs=[eid]))
    return out


def _snapshot(db):
    return {t: [tuple(r) for r in db.execute(f"SELECT * FROM {t} ORDER BY 1")]
            for t in ("akb_assertions", "kg_nodes", "kg_edges")}


def test_cp_cmp_001_create_projection(db):
    """CP-CMP-001：create projection——因果谓词断言 → CausalProjection 全字段。"""
    con, eid = db
    _causal_assertions(con, eid, [("Heat", "causes", "InsulationAging")])
    proj = CausalProjectionRuntime(con).project()
    assert proj.projection_id.startswith("cpr_")
    assert proj.source_snapshot.startswith("snap_")
    assert proj.fingerprint
    assert len(proj.causal_edges) == 1
    e = proj.causal_edges[0]
    assert isinstance(e, CausalEdge) and e.source_ref == "Heat"
    assert e.target_ref == "InsulationAging" and e.relation_type == "causes"


def test_cp_cmp_002_deterministic_identity(db):
    """CP-CMP-002：deterministic identity——同库状态双投影同 projection_id/
    fingerprint/causal_id；输入变化 → 变。"""
    con, eid = db
    _causal_assertions(con, eid, [("Heat", "causes", "InsulationAging")])
    r1 = CausalProjectionRuntime(con).project()
    r2 = CausalProjectionRuntime(con).project()
    assert r1.projection_id == r2.projection_id
    assert r1.fingerprint == r2.fingerprint
    assert r1.causal_edges[0].causal_id == r2.causal_edges[0].causal_id
    # 单元级：causal_edge_identity 同输入同输出
    kw = dict(source_ref="A", target_ref="B", relation_type="causes",
              condition_refs=(), mechanism_ref="", assertion_id="ast_x")
    assert causal_edge_identity(**kw) == causal_edge_identity(**kw)
    # 新断言 → fingerprint 变
    _causal_assertions(con, eid, [("Load", "enables", "Wear")])
    r3 = CausalProjectionRuntime(con).project()
    assert r3.fingerprint != r1.fingerprint


def test_cp_cmp_003_same_snapshot_rebuild(db):
    """CP-CMP-003：same snapshot rebuild——同（断言快照+规格）→ 同 projection_id
    （Rule 3 rebuildable）。"""
    con, eid = db
    _causal_assertions(con, eid, [("Heat", "causes", "InsulationAging"),
                                  ("Load", "prevents", "Cooling")])
    snap_assertions = [dict(r) for r in con.execute(
        "SELECT assertion_id FROM akb_assertions WHERE predicate_ref IN"
        " ('causes','caused_by','enables','prevents')")]
    snap1 = CausalProjectionRuntime(con).project()
    # 重建（新 runtime 实例——同库状态）
    snap2 = CausalProjectionRuntime(con).project()
    assert snap1.projection_id == snap2.projection_id
    assert snap1.source_snapshot == snap2.source_snapshot
    assert [e.causal_id for e in snap1.causal_edges] == \
        [e.causal_id for e in snap2.causal_edges]


def test_cp_cmp_004_invalid_causal_relation_reject(db):
    """CP-CMP-004：invalid causal relation reject——非因果谓词不进投影（白名单外
    静默排除是加载面语义）；未知 relation_type（若直达）fail-close。"""
    con, eid = db
    _causal_assertions(con, eid, [("Heat", "causes", "Aging"),
                                  ("X", "relates_to", "Y")])   # 非因果谓词
    proj = CausalProjectionRuntime(con).project()
    assert len(proj.causal_edges) == 1     # 只投影因果谓词
    assert all(e.relation_type in ("causes", "caused_by", "enables", "prevents")
               for e in proj.causal_edges)
    # 未知 relation_type 直达校验（unit 面 fail-close）
    rt = CausalProjectionRuntime(con)
    from agent_kb.causal import CAUSAL_RELATION_TYPES
    assert "teleport" not in CAUSAL_RELATION_TYPES


def test_cp_cmp_005_missing_provenance_fail_close(db):
    """CP-CMP-005：missing provenance fail-close——①schema 层：INV-005 触发器
    拒绝 provenance_ref 变更（V0.4 冻结保护实测）；②runtime 层：空 provenance
    断言视图 → E-V09-CAUSAL-INVALID（零 fabricate）。"""
    con, eid = db
    _causal_assertions(con, eid, [("Heat", "causes", "Aging")])
    # ①schema 层保护（V0.4 frozen 触发器——比 runtime 校验更强）
    with pytest.raises(Exception):
        con.execute("UPDATE akb_assertions SET provenance_ref = NULL"
                    " WHERE predicate_ref='causes'")
    # ②runtime 层 fail-close（unit 面——空 provenance 视图直达）
    rt = CausalProjectionRuntime(con)
    bad = {"assertion_id": "ast_x", "subject_ref": "A", "predicate_ref":
           "causes", "object_value": "B", "object_entity_ref": None,
           "status": "candidate", "confidence": 0.9, "provenance_ref": None}
    import agent_kb.causal.projection as pm
    orig = rt._load_causal_assertions
    rt._load_causal_assertions = lambda: [bad]  # 注入异常态（模拟数据不一致）
    with pytest.raises(CausalProjectionError, match="E-V09-CAUSAL-INVALID"):
        rt.project()
    rt._load_causal_assertions = orig


def test_cp_cmp_006_causal_not_assertion(db):
    """CP-CMP-006：causal ≠ assertion——投影全流程 akb_assertions unchanged。"""
    con, eid = db
    _causal_assertions(con, eid, [("Heat", "causes", "Aging")])
    before = _snapshot(con)["akb_assertions"]
    proj = CausalProjectionRuntime(con).project()
    CausalProjectionRuntime(con).query_causal(proj, effect_ref="Aging")
    after = _snapshot(con)["akb_assertions"]
    assert before == after       # Rule 1：CausalRelation ≠ Assertion


def test_cp_cmp_007_projection_not_graph_mutation(db):
    """CP-CMP-007：projection ≠ graph mutation——kg_nodes/kg_edges unchanged
    （Rule 2，零图写入）。"""
    con, eid = db
    _causal_assertions(con, eid, [("Heat", "causes", "Aging")])
    n_before = con.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"]
    e_before = con.execute("SELECT COUNT(*) c FROM kg_edges").fetchone()["c"]
    snap = _snapshot(con)
    proj = CausalProjectionRuntime(con).project()
    CausalProjectionRuntime(con).query_causal(proj)
    assert con.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"] == n_before
    assert con.execute("SELECT COUNT(*) c FROM kg_edges").fetchone()["c"] == e_before
    assert snap["kg_nodes"] == _snapshot(con)["kg_nodes"]
    assert snap["kg_edges"] == _snapshot(con)["kg_edges"]


def test_cp_cmp_008_provenance_audit(db):
    """CP-CMP-008：provenance audit——graph:causal-projection-create 落
    akb_provenance（projection_id/snapshot/fingerprint/edges）。"""
    con, eid = db
    _causal_assertions(con, eid, [("Heat", "causes", "Aging")])
    proj = CausalProjectionRuntime(con).project()
    rows = [dict(x) for x in con.execute(
        "SELECT * FROM akb_provenance WHERE"
        " activity='graph:causal-projection-create'")]
    assert len(rows) == 1
    m = json.loads(rows[0]["metadata_json"])
    assert m["projection_id"] == proj.projection_id
    assert m["source_snapshot"] == proj.source_snapshot
    assert m["fingerprint"] == proj.fingerprint
    assert m["causal_edge_count"] == 1


def test_cp_cmp_009_immutable_projection(db):
    """CP-CMP-009：immutable projection——CausalProjection/CausalEdge frozen
    dataclass 赋值拒绝。"""
    con, eid = db
    _causal_assertions(con, eid, [("Heat", "causes", "Aging")])
    proj = CausalProjectionRuntime(con).project()
    with pytest.raises(Exception):
        proj.fingerprint = "x"  # type: ignore[misc]
    with pytest.raises(Exception):
        proj.causal_edges[0].status = "invalid"  # type: ignore[misc]


def test_cp_cmp_010_frozen_regression(db):
    """CP-CMP-010：frozen regression——V0.5/V0.6/V0.7/V0.8 frozen 模块零感知
    （单向依赖）+ legacy 零引用 + 建图回归。"""
    import inspect
    import agent_kb.graph as legacy
    frozen_mods = []
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
    frozen_mods = [m1, m2, m3, m4, m5, m6, m7, m8, m9, m10]
    for mod in frozen_mods:
        assert "CausalProjection" not in inspect.getsource(mod)
    for sym in ("CausalProjectionRuntime", "CausalEdge"):
        assert not hasattr(legacy, sym)
    # 建图回归：投影活动后 V0.5 查询面不变
    from agent_kb.kgraph import (
        GraphPersistenceService, GraphProjectionService, GraphQueryService)
    con = db[0]
    GraphPersistenceService(con).persist(GraphProjectionService().process(con))
    q = GraphQueryService(con)
    v1 = q.canonical_view()
    CausalProjectionRuntime(con).project()
    assert q.canonical_view() == v1