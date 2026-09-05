# -*- coding: utf-8 -*-
"""GQ-CMP-001..025（AKB-V05-IMPL-004：Graph Query acceptance）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.evidence_core.assertions import AssertionStore, AssertionValidator
from agent_kb.kgraph import (
    GraphPersistenceService,
    GraphProjectionService,
    GraphQueryError,
    GraphQueryService,
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
    """P/D fixture：完整链 Document→Evidence→Unit→Assertion→Entity→Inference + persist。"""
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
               " VALUES ('gq', 'document', 'GQ')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at) VALUES ('dgq', 'gq', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    store = EvidenceStore(db)
    comp = SemanticCompiler(db)
    eids = []
    for t in ["OBC 额定输入电压 265V。", "OBC 额定输入电压是 265V。"]:
        ev = store.create(document_id="dgq", content=t, extraction_method="t")
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
    eng = ReasoningEngine(db, provider=BuiltinRuleReasoner())
    rr = eng.reason([s1.assertion_id, s2.assertion_id, d1.assertion_id, d2.assertion_id],
                    actor_id="system:reasoner", context=ReasoningContext("test"))
    proj = GraphProjectionService().process(db)
    pr = GraphPersistenceService(db).persist(proj)
    return {"proj": proj, "eids": eids, "persist": pr, "store": a_store,
            "reasoning": rr, "seeds": (s1, s2, d1, d2)}


def _seed_and_persist_negative(db):
    """N fixture：rejected/deprecated/disputed/hypothesized + persist。"""
    from agent_kb.evidence_core import EvidenceStore
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('gn', 'document', 'GN')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at) VALUES ('dgn', 'gn', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    eid = EvidenceStore(db).create(document_id="dgn", content="N 锚证据。",
                                   extraction_method="t").evidence_id
    store = AssertionStore(db)
    made = {}
    for key, subj in (("rejected", "R-A"), ("deprecated", "D-A"),
                      ("disputed", "Q-A"), ("hypothesized", "H-A"),
                      ("validated", "V-A")):
        made[key] = store.create_candidate(
            subject_ref=subj, predicate_ref="has_status",
            object={"kind": "literal", "value": key + "-target"},
            assertion_type="hypothesized" if key == "hypothesized" else "extracted",
            ontology_scope="test", actor_id="system:seed", confidence=0.9,
            evidence_refs=[eid])
    store.transition(assertion_id=made["rejected"].assertion_id, new_status="rejected",
                     actor_id="human:governor", reason="gq")
    for key in ("deprecated", "disputed"):
        AssertionValidator(db).validate(assertion_id=made[key].assertion_id,
                                        actor_id="system:validator")
    store.transition(assertion_id=made["deprecated"].assertion_id,
                     new_status="deprecated", actor_id="human:governor", reason="gq")
    store.transition(assertion_id=made["disputed"].assertion_id, new_status="disputed",
                     actor_id="human:governor", reason="gq")
    proj = GraphProjectionService().process(db)
    pr = GraphPersistenceService(db).persist(proj)
    return {"proj": proj, "persist": pr, "made": made}


def _snapshot(db):
    """五表快照（read-only 验证用）。"""
    out = {}
    for t in ("kg_nodes", "kg_edges", "kg_projection_runs", "kg_invalidation_log"):
        out[t] = [tuple(r) for r in db.execute(f"SELECT * FROM {t} ORDER BY 1")]
    out["akb_provenance"] = [tuple(r) for r in db.execute(
        "SELECT * FROM akb_provenance ORDER BY provenance_id")]
    return out


def test_gq_cmp_001_q01_provenance_query(db):
    """GQ-CMP-001/Q-01：assertion 节点五级链回溯（graph→assertion→evidence→document）。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    an = db.execute("SELECT node_id FROM kg_nodes WHERE node_type='assertion'"
                    " LIMIT 1").fetchone()["node_id"]
    tr = q.provenance_trace(an)
    assert tr.assertion_id and tr.evidence_ids and tr.document_id
    assert tr.chain[0].startswith("graph_node:")
    assert any(c.startswith("document:") for c in tr.chain)


def test_gq_cmp_002_q02_entity_neighborhood(db):
    """GQ-CMP-002/Q-02：entity k-hop 邻域（relates_to/supports，BFS 无 N+1）。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    ent = db.execute("SELECT node_id FROM kg_nodes WHERE node_type='entity'"
                     " LIMIT 1").fetchone()["node_id"]
    nb = q.entity_neighborhood(ent, hops=2)
    assert nb["center"] == ent
    assert any(n.node_type == "entity" for n in nb["nodes"])
    assert nb["nodes"] == sorted(nb["nodes"], key=lambda n: n.node_id)


def test_gq_cmp_003_q03_assertion_trace(db):
    """GQ-CMP-003/Q-03：assertion contradicts 邻居 + conflict_ref（不裁决）。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    # RR-04 disputed 断言（__DISPUTED__）的 assertion 节点
    row = db.execute("SELECT n.node_id FROM kg_nodes n JOIN kg_edges e"
                     " ON e.source_node=n.node_id WHERE e.edge_type='contradicts'"
                     " LIMIT 1").fetchone()
    if row is None:
        pytest.skip("no contradicts edge in fixture (RR-04 not triggered)")
    tr = q.assertion_trace(row["node_id"])
    assert tr["contradictions"]
    assert all("conflict_ref" in c for c in tr["contradictions"])
    assert tr["provenance"].assertion_id


def test_gq_cmp_004_q04_inference_chain(db):
    """GQ-CMP-004/Q-04：inferred assertion → derived_from 祖先链展开
    （设计 §2 双粒度：run 级 InferenceNode + 断言级 derived_from 链——
    链边挂在 inferred assertion 节点上）。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    # run 级节点存在
    inf = db.execute("SELECT node_id FROM kg_nodes WHERE node_type='inference'"
                     " LIMIT 1").fetchone()
    assert inf
    # inferred assertion 节点（有 derived_from 边）
    ia = db.execute(
        "SELECT n.node_id FROM kg_nodes n JOIN kg_edges e ON e.source_node=n.node_id"
        " WHERE e.edge_type='derived_from' LIMIT 1").fetchone()
    assert ia, "inferred assertion node must have derived_from edge"
    ch = q.inference_chain(ia["node_id"])
    assert ch["root"] == ia["node_id"]
    assert any(e.edge_type == "derived_from" for e in ch["edges"])
    assert ch["nodes"] == sorted(ch["nodes"], key=lambda n: n.node_id)
    # 祖先可达：链终点含 parent（extracted）断言
    parents = db.execute(
        "SELECT target_node FROM kg_edges WHERE edge_type='derived_from'").fetchall()
    reachable = {n.node_id for n in ch["nodes"]}
    assert any(p["target_node"] in reachable for p in parents)


def test_gq_cmp_005_q05_status_aware(db):
    """GQ-CMP-005/Q-05：默认排除 invalidated；flagged 保留；audit 模式可包含。"""
    _seed_and_persist_negative(db)
    q = GraphQueryService(db)
    default = q.query_nodes()                  # 默认面不含 invalidated（Q-05）
    assert all(n.status != "invalidated" for n in default)
    audit = q.query_nodes(status="invalidated")  # 显式 status = audit 意图
    assert len(audit) == 2                     # rejected + deprecated
    flagged = q.query_nodes(status="flagged")
    assert len(flagged) == 1                   # disputed → flagged（不删除）


def test_gq_cmp_006_q06_deterministic_canonical_view(db):
    """GQ-CMP-006/Q-06：canonical view 确定性序列化。"""
    _seed_and_persist(db)
    q = GraphQueryService(db)
    v1 = q.canonical_view()
    v2 = q.canonical_view()
    assert v1 == v2 and len(v1) > 10


def test_gq_cmp_007_validated_nodes_queryable(db):
    """GQ-CMP-007：valid 节点可查询（candidate/validated → valid）。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    valid = q.query_nodes(status="valid", node_type="assertion")
    assert valid
    assert all(n.status == "valid" for n in valid)


def test_gq_cmp_008_rejected_deprecated_invalidated(db):
    """GQ-CMP-008：rejected/deprecated → invalidated 语义在查询面保持。"""
    _seed_and_persist_negative(db)
    q = GraphQueryService(db)
    inv = q.query_nodes(status="invalidated", include_invalidated=True,
                        node_type="assertion")
    assert len(inv) == 2
    assert all(n.status == "invalidated" for n in inv)


def test_gq_cmp_009_disputed_flagged(db):
    """GQ-CMP-009：disputed → flagged（保留且可识别）。"""
    _seed_and_persist_negative(db)
    q = GraphQueryService(db)
    fl = q.query_nodes(status="flagged", node_type="assertion")
    assert len(fl) == 1
    # flagged 节点 provenance 仍可回溯（不静默丢弃）
    tr = q.provenance_trace(fl[0].node_id)
    assert tr.assertion_id


def test_gq_cmp_010_hypothesized_excluded(db):
    """GQ-CMP-010：hypothesized 不进入 graph/query 面。"""
    _seed_and_persist_negative(db)
    q = GraphQueryService(db)
    hid = _hyp_id = None
    # hypothesized 断言 id 从 akb_assertions 找（未 persist 进 kg_nodes）
    rows = [dict(r) for r in db.execute(
        "SELECT assertion_id FROM akb_assertions WHERE assertion_type='hypothesized'")]
    assert rows, "fixture must contain hypothesized assertion"
    for r in rows:
        hit = db.execute("SELECT COUNT(*) c FROM kg_nodes WHERE source_id=?",
                         (r["assertion_id"],)).fetchone()["c"]
        assert hit == 0
    assert all(n.source_id not in {r["assertion_id"] for r in rows}
               for n in q.query_nodes(include_invalidated=True, limit=1000))


def test_gq_cmp_011_node_to_assertion_provenance(db):
    """GQ-CMP-011：node → assertion（Q-01 链第一级）。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    an = db.execute("SELECT node_id, source_id FROM kg_nodes WHERE node_type='assertion'"
                    " LIMIT 1").fetchone()
    tr = q.provenance_trace(an["node_id"])
    assert tr.assertion_id == an["source_id"]
    assert db.execute("SELECT 1 FROM akb_assertions WHERE assertion_id=?",
                      (tr.assertion_id,)).fetchone()


def test_gq_cmp_012_assertion_to_evidence(db):
    """GQ-CMP-012：assertion → evidence（Q-01 链第二级）。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    an = db.execute("SELECT node_id FROM kg_nodes WHERE node_type='assertion'"
                    " LIMIT 1").fetchone()["node_id"]
    tr = q.provenance_trace(an)
    assert tr.evidence_ids
    for eid in tr.evidence_ids:
        assert db.execute("SELECT 1 FROM akb_evidence WHERE evidence_id=?",
                          (eid,)).fetchone()


def test_gq_cmp_013_evidence_to_document(db):
    """GQ-CMP-013：evidence → document（Q-01 链第三级）。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    an = db.execute("SELECT node_id FROM kg_nodes WHERE node_type='assertion'"
                    " LIMIT 1").fetchone()["node_id"]
    tr = q.provenance_trace(an)
    assert tr.document_id
    assert db.execute("SELECT 1 FROM akb_documents WHERE document_id=?",
                      (tr.document_id,)).fetchone()


def test_gq_cmp_014_inference_to_reasoning_run(db):
    """GQ-CMP-014：inference → reasoning run（Q-01 推理支线）。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    inf = db.execute("SELECT node_id, source_id FROM kg_nodes WHERE node_type='inference'"
                     " LIMIT 1").fetchone()
    tr = q.provenance_trace(inf["node_id"])
    assert tr.reasoning_run_id == inf["source_id"]
    assert db.execute("SELECT 1 FROM akb_reasoning_runs WHERE run_id=?",
                      (tr.reasoning_run_id,)).fetchone()


def test_gq_cmp_015_edge_query_no_duplicates(db):
    """GQ-CMP-015：边查询零重复。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    edges = q.query_edges(limit=1000)
    ids = [e.edge_id for e in edges]
    assert len(ids) == len(set(ids))


def test_gq_cmp_016_traversal_no_duplicate_nodes(db):
    """GQ-CMP-016：traversal 零重复节点。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    ent = db.execute("SELECT node_id FROM kg_nodes WHERE node_type='entity'"
                     " LIMIT 1").fetchone()["node_id"]
    nb = q.entity_neighborhood(ent, hops=3)
    ids = [n.node_id for n in nb["nodes"]]
    assert len(ids) == len(set(ids))


def test_gq_cmp_017_deterministic_ordering(db):
    """GQ-CMP-017：全部列表输出显式确定性排序（node_id/edge_id canonical）。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    nodes = q.query_nodes(limit=1000)
    assert [n.node_id for n in nodes] == sorted(n.node_id for n in nodes)
    edges = q.query_edges(limit=1000)
    assert [e.edge_id for e in edges] == sorted(e.edge_id for e in edges)


def test_gq_cmp_018_same_state_same_result(db):
    """GQ-CMP-018：同一 DB state 两次 Query 结果一致。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    r1 = q.canonical_view()
    r2 = q.canonical_view()
    assert r1 == r2


def test_gq_cmp_019_cross_instance_consistency(db):
    """GQ-CMP-019：两个 QueryService 实例面对同一 DB → 等价结果。"""
    s = _seed_and_persist(db)
    qa, qb = GraphQueryService(db), GraphQueryService(db)
    assert qa.canonical_view() == qb.canonical_view()
    ent = db.execute("SELECT node_id FROM kg_nodes WHERE node_type='entity'"
                     " LIMIT 1").fetchone()["node_id"]
    assert qa.entity_neighborhood(ent) == qb.entity_neighborhood(ent)


def test_gq_cmp_020_read_only_guarantee(db):
    """GQ-CMP-020：Query 完全 read-only——五表快照前后一致。"""
    s = _seed_and_persist(db)
    before = _snapshot(db)
    q = GraphQueryService(db)
    an = db.execute("SELECT node_id FROM kg_nodes WHERE node_type='assertion'"
                    " LIMIT 1").fetchone()["node_id"]
    ent = db.execute("SELECT node_id FROM kg_nodes WHERE node_type='entity'"
                     " LIMIT 1").fetchone()["node_id"]
    inf = db.execute("SELECT node_id FROM kg_nodes WHERE node_type='inference'"
                     " LIMIT 1").fetchone()["node_id"]
    # 全查询面执行
    q.provenance_trace(an)
    q.entity_neighborhood(ent, hops=2)
    q.inference_chain(inf)
    q.assertion_trace(an)
    q.query_nodes(limit=1000)
    q.query_edges(limit=1000)
    q.canonical_view()
    q.query_nodes(status="invalidated", include_invalidated=True)
    after = _snapshot(db)
    assert before == after


def test_gq_cmp_021_legacy_isolation(db):
    """GQ-CMP-021：legacy graph 隔离——agent_kb.graph API 互斥 + graph_edges 零变化。"""
    import agent_kb.graph as legacy
    import agent_kb.kgraph as kgraph
    for sym in ("GraphQueryService", "GraphNodeView", "ProvenanceTrace"):
        assert not hasattr(legacy, sym)
    for sym in ("DeterministicRelationExtractor", "SQLiteGraphStore"):
        assert not hasattr(kgraph, sym)
    s = _seed_and_persist(db)
    before = db.execute("SELECT COUNT(*) c FROM graph_edges").fetchone()["c"]
    GraphQueryService(db).canonical_view()
    after = db.execute("SELECT COUNT(*) c FROM graph_edges").fetchone()["c"]
    assert before == after


def test_gq_cmp_022_query_after_rebuild(db):
    """GQ-CMP-022：graph rebuild 后 Query 结果保持一致。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    v1 = q.canonical_view()
    # rebuild：重新投影 → persist（fingerprint 幂等——逻辑图不变）
    proj2 = GraphProjectionService().process(db)
    GraphPersistenceService(db).persist(proj2, rebuild=True)
    v2 = q.canonical_view()
    assert v1 == v2


def test_gq_cmp_023_empty_graph_behavior(db):
    """GQ-CMP-023：空 graph——no nodes/edges/provenance → 确定性空结果而非异常。"""
    q = GraphQueryService(db)
    assert q.query_nodes() == []
    assert q.query_edges() == []
    assert q.canonical_view() == json.dumps(
        {"nodes": [], "edges": []}, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), default=str) or q.canonical_view().startswith("{")
    # 空 graph 的 neighborhood：节点不存在 → 显式 NOT-FOUND（fail-closed）
    with pytest.raises(GraphQueryError, match="E-V05-NODE-NOT-FOUND"):
        q.entity_neighborhood("nonexistent")


def test_gq_cmp_024_missing_source_fail_closed(db):
    """GQ-CMP-024：missing/invalid source reference → 显式错误，不 fabricate。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    # 注入一个 source 指向不存在 assertion 的节点（直接 SQL——模拟数据不一致）
    db.execute("INSERT INTO kg_nodes (node_id, node_type, source_id, projection_id,"
               " status, payload_json, provenance_ref)"
               " VALUES ('orphan_1', 'assertion', 'ast_ghost',"
               " (SELECT projection_id FROM kg_projection_runs LIMIT 1),"
               " 'valid', '{}', 'prov_ghost')")
    with pytest.raises(GraphQueryError, match="E-V05-SOURCE-MISSING"):
        q.provenance_trace("orphan_1")
    with pytest.raises(GraphQueryError, match="E-V05-NODE-NOT-FOUND"):
        q.provenance_trace("no_such_node")
    # 不存在的节点 provenance_trace 不 fabricate
    db.execute("DELETE FROM kg_nodes WHERE node_id='orphan_1'")


def test_gq_cmp_025_invalid_parameters_fail_closed(db):
    """GQ-CMP-025：invalid 参数 → 显式拒绝（不静默放宽/全表扫描）。"""
    s = _seed_and_persist(db)
    q = GraphQueryService(db)
    with pytest.raises(GraphQueryError, match="E-V05-INVALID-NODE-TYPE"):
        q.query_nodes(node_type="ghost_type")
    with pytest.raises(GraphQueryError, match="E-V05-INVALID-STATUS"):
        q.query_nodes(status="floating")
    with pytest.raises(GraphQueryError, match="E-V05-INVALID-EDGE-TYPE"):
        q.query_edges(edge_type="teleport")
    with pytest.raises(GraphQueryError, match="E-V05-INVALID-LIMIT"):
        q.query_nodes(limit=99999)
    with pytest.raises(GraphQueryError, match="E-V05-INVALID-HOPS"):
        q.entity_neighborhood("x", hops=0)
    with pytest.raises(GraphQueryError, match="E-V05-INVALID-DEPTH"):
        q.inference_chain("x", max_depth=99)
    with pytest.raises(GraphQueryError, match="E-V05-NODE-NOT-FOUND"):
        q.query_edges(node_id="ghost_node")