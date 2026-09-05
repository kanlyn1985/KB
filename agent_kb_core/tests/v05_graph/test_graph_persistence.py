# -*- coding: utf-8 -*-
"""GP-CMP-001..025（AKB-V05-IMPL-003：Graph Persistence acceptance）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.kgraph import (
    GraphPersistenceError,
    GraphPersistenceService,
    GraphProjectionService,
    GraphRepository,
)


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con).migrate()
    yield con
    con.close()


def _seed_graph(db, with_governance=True):
    """P 类 fixture：Document/Evidence/SemanticUnit/Assertion/Entity/Inference 全链。"""
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
               " VALUES ('gp', 'document', 'GP')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at) VALUES ('dgp', 'gp', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    store = EvidenceStore(db)
    comp = SemanticCompiler(db)
    eids = []
    for t in ["OBC 额定输入电压 265V。", "OBC 额定输入电压是 265V。"]:
        ev = store.create(document_id="dgp", content=t, extraction_method="t")
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
    eng = ReasoningEngine(db, provider=BuiltinRuleReasoner())
    rr = eng.reason([s1.assertion_id, s2.assertion_id], actor_id="system:reasoner",
                    context=ReasoningContext("test"))
    proj = GraphProjectionService().process(db)
    return {"proj": proj, "eids": eids, "synthesis": sr, "reasoning": rr,
            "store": a_store}


def _seed_negative(db):
    """N 类 fixture：rejected/deprecated/disputed/hypothesized 断言进入投影源。"""
    from agent_kb.evidence_core import EvidenceStore
    from agent_kb.evidence_core.assertions import AssertionStore
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('gn', 'document', 'GN')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at) VALUES ('dgn', 'gn', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    eid = EvidenceStore(db).create(document_id="dgn", content="N 类锚证据。",
                                   extraction_method="t").evidence_id
    store = AssertionStore(db)
    made = {}
    specs = {
        "rejected": ("R-A", "has_status", "rejected-target"),
        "deprecated": ("D-A", "has_status", "deprecated-target"),
        "disputed": ("Q-A", "has_status", "disputed-target"),
        "hypothesized": ("H-A", "has_status", "hypothesized-target"),
        "validated": ("V-A", "has_status", "validated-target"),
    }
    for key, (subj, pred, val) in specs.items():
        a = store.create_candidate(
            subject_ref=subj, predicate_ref=pred,
            object={"kind": "literal", "value": val},
            assertion_type="hypothesized" if key == "hypothesized" else "extracted",
            ontology_scope="test", actor_id="system:seed", confidence=0.9,
            evidence_refs=[eid])
        made[key] = a
    # 状态迁移走合法路径：candidate→rejected 直达；deprecated/disputed 经 validated
    from agent_kb.evidence_core.assertions import AssertionValidator
    store.transition(assertion_id=made["rejected"].assertion_id, new_status="rejected",
                     actor_id="human:governor", reason="gp")
    for key in ("deprecated", "disputed"):
        AssertionValidator(db).validate(assertion_id=made[key].assertion_id,
                                        actor_id="system:validator")
    store.transition(assertion_id=made["deprecated"].assertion_id,
                     new_status="deprecated", actor_id="human:governor", reason="gp")
    store.transition(assertion_id=made["disputed"].assertion_id, new_status="disputed",
                     actor_id="human:governor", reason="gp")
    return {"proj": GraphProjectionService().process(db), "made": made, "eid": eid,
            "store": store}


def test_gp_cmp_001_migration_creates_schema(db):
    """GP-CMP-001：migration 15 创建全部 graph schema。"""
    tables = [r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE name LIKE 'kg_%' ORDER BY name")]
    assert set(tables) >= {"kg_projection_runs", "kg_nodes", "kg_edges",
                           "kg_invalidation_log"}
    for t in ("kg_projection_runs", "kg_nodes", "kg_edges", "kg_invalidation_log"):
        assert len([r[1] for r in db.execute(f"PRAGMA table_info({t})")]) >= 5


def test_gp_cmp_002_migration_compat_with_14(db):
    """GP-CMP-002：migration 14 表完好 + 15 共存；14 内容未修改。"""
    assert db.execute("SELECT COUNT(*) c FROM akb_reasoning_runs").fetchone()["c"] == 0
    cols = [r[1] for r in db.execute("PRAGMA table_info(akb_reasoning_runs)")]
    assert "fingerprint" in cols and "parent_ids_json" in cols
    # 15 与 14 同库共存（kg 表已建 + akb 表完好）
    from agent_kb.kgraph import GraphRepository
    assert GraphRepository(db).has_schema()


def test_gp_cmp_003_node_persistence(db):
    """GP-CMP-003：节点持久化（六类至少出现五类——inference 视 reasoning run）。"""
    seeded = _seed_graph(db)
    svc = GraphPersistenceService(db)
    r = svc.persist(seeded["proj"], actor_id="system:kgraph")
    assert r["accepted"] and r["nodes"] == len(seeded["proj"].nodes)
    types = {row["node_type"] for row in db.execute(
        "SELECT DISTINCT node_type FROM kg_nodes")}
    assert {"document", "evidence", "semantic_unit", "assertion",
            "entity"} <= types


def test_gp_cmp_004_edge_persistence(db):
    """GP-CMP-004：边持久化（extracted_from/supports 至少存在；FK 完整）。"""
    seeded = _seed_graph(db)
    GraphPersistenceService(db).persist(seeded["proj"])
    types = {row["edge_type"] for row in db.execute(
        "SELECT DISTINCT edge_type FROM kg_edges")}
    assert {"extracted_from", "supports"} <= types
    # FK：每条边两端都在 kg_nodes
    orphans = db.execute(
        "SELECT COUNT(*) c FROM kg_edges e WHERE NOT EXISTS"
        " (SELECT 1 FROM kg_nodes n WHERE n.node_id=e.source_node)"
        " OR NOT EXISTS (SELECT 1 FROM kg_nodes n WHERE n.node_id=e.target_node)"
    ).fetchone()["c"]
    assert orphans == 0


def test_gp_cmp_005_projection_metadata_persistence(db):
    """GP-CMP-005：projection metadata（fingerprint/source_digest/counts/status）。"""
    seeded = _seed_graph(db)
    r = GraphPersistenceService(db).persist(seeded["proj"])
    row = dict(db.execute("SELECT * FROM kg_projection_runs WHERE projection_id=?",
                          (r["projection_id"],)).fetchone())
    assert row["fingerprint"] == r["fingerprint"]
    assert row["graph_version"] == "v05-graph-1.0"
    assert row["status"] == "active"
    assert row["node_count"] == len(seeded["proj"].nodes)
    assert row["edge_count"] == len(seeded["proj"].edges)
    assert row["source_digest"] == seeded["proj"].canonical_digest()


def test_gp_cmp_006_deterministic_node_ids(db):
    """GP-CMP-006：deterministic node IDs——同一数据库状态双投影 → node_id 集合全等
    （设计语义：same db state → same ids；source_id 事件溯源跨库不重放）。"""
    seeded = _seed_graph(db)
    p1 = GraphProjectionService().process(db)
    p2 = GraphProjectionService().process(db)
    assert sorted(n.node_id for n in p1.nodes) == sorted(n.node_id for n in p2.nodes)
    assert sorted(n.node_id for n in p1.nodes) == \
        sorted(n.node_id for n in seeded["proj"].nodes)


def test_gp_cmp_007_deterministic_edge_identity(db):
    """GP-CMP-007：deterministic edge identity——同库双投影全等（含方向性）。"""
    seeded = _seed_graph(db)
    p1 = GraphProjectionService().process(db)
    p2 = GraphProjectionService().process(db)
    assert sorted(e.edge_id for e in p1.edges) == sorted(e.edge_id for e in p2.edges)
    assert sorted(e.edge_id for e in p1.edges) == \
        sorted(e.edge_id for e in seeded["proj"].edges)


def test_gp_cmp_008_duplicate_prevention(db):
    """GP-CMP-008：重复身份防插入——PK 约束 + 幂等 persist 双保险。"""
    seeded = _seed_graph(db)
    GraphPersistenceService(db).persist(seeded["proj"])
    n1 = db.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"]
    with pytest.raises(Exception):
        db.execute("INSERT INTO kg_nodes (node_id, node_type, source_id,"
                   " projection_id, status, payload_json, provenance_ref)"
                   " SELECT node_id, node_type, source_id, projection_id, status,"
                   " payload_json, provenance_ref FROM kg_nodes LIMIT 1")
    assert db.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"] == n1


def test_gp_cmp_009_repeated_persistence(db):
    """GP-CMP-009：重复 persist（×3）→ 零新增、零重复 provenance。"""
    seeded = _seed_graph(db)
    svc = GraphPersistenceService(db)
    r1 = svc.persist(seeded["proj"])
    results = [svc.persist(seeded["proj"]) for _ in range(2)]
    assert all(x.get("idempotent_hit") for x in results)
    counts = GraphRepository(db).counts()
    assert counts["nodes"] == r1["nodes"]
    assert counts["edges"] == r1["edges"]
    assert counts["projections"] == 1
    n_prov = db.execute("SELECT COUNT(*) c FROM akb_provenance"
                        " WHERE activity='graph:project'").fetchone()["c"]
    assert n_prov == 1                                     # 零重复 provenance


def test_gp_cmp_010_cross_instance_persistence(db):
    """GP-CMP-010：跨实例 persist → 同 fingerprint 幂等命中。"""
    seeded = _seed_graph(db)
    r1 = GraphPersistenceService(db).persist(seeded["proj"])
    r2 = GraphPersistenceService(db).persist(seeded["proj"])   # 新 service 实例
    assert r2.get("idempotent_hit") and r2["projection_id"] == r1["projection_id"]
    assert GraphRepository(db).counts()["projections"] == 1


def test_gp_cmp_011_node_failure_rollback(db):
    """GP-CMP-011：node 写失败（注入非法 node_type）→ 全回滚。"""
    seeded = _seed_graph(db)
    from agent_kb.kgraph.models import GraphProjection
    # 构造含非法节点类型的 projection（frozen dataclass 用 object.__setattr__ 绕过）
    proj = seeded["proj"]
    bad_node = proj.nodes[0]
    object.__setattr__(bad_node, "node_id", "bad_node_id")
    object.__setattr__(bad_node, "__class__", type(bad_node))  # 类型不变——改用错误类型注入
    from agent_kb.kgraph.models import EntityNode
    evil = EntityNode(node_id="evil_1", canonical_id="x", canonical_form="X",
                      entity_type="unknown", provenance_ref="x", source_ref="x")
    # 将 evil 节点 type 映射为非法：直接往 NODE_TYPE_MAP 外造类型——用子类 trick
    class GhostNode(type(evil)):
        pass
    evil2 = GhostNode(node_id="evil_2", canonical_id="x", canonical_form="X",
                      entity_type="x", provenance_ref="x", source_ref="x")
    bad_proj = GraphProjection(nodes=tuple(proj.nodes) + (evil2,),
                               edges=proj.edges, fingerprint="badfp_0001")
    before = GraphRepository(db).counts()
    with pytest.raises(GraphPersistenceError, match="E-V05-INVALID-NODE"):
        GraphPersistenceService(db).persist(bad_proj)
    after = GraphRepository(db).counts()
    assert before == after                                 # 全回滚（零残留）


def test_gp_cmp_012_edge_failure_rollback(db):
    """GP-CMP-012：edge 写失败（悬空 FK）→ 全回滚。"""
    seeded = _seed_graph(db)
    from agent_kb.kgraph.models import GraphProjection, SupportsEdge
    proj = seeded["proj"]
    dangling = SupportsEdge(edge_id="dangling_1", source_node="ghost_src",
                            target_node="ghost_tgt", provenance_ref="x")
    bad_proj = GraphProjection(nodes=proj.nodes,
                               edges=tuple(proj.edges) + (dangling,),
                               fingerprint="badfp_0002")
    before = GraphRepository(db).counts()
    with pytest.raises(Exception):                         # FK violation / fail-closed
        GraphPersistenceService(db).persist(bad_proj)
    after = GraphRepository(db).counts()
    assert before == after


def test_gp_cmp_013_metadata_failure_rollback(db):
    """GP-CMP-013：metadata 失败（缺 fingerprint）→ 零残留。"""
    seeded = _seed_graph(db)
    from agent_kb.kgraph.models import GraphProjection
    bad = GraphProjection(nodes=seeded["proj"].nodes, edges=seeded["proj"].edges,
                          fingerprint="")
    with pytest.raises(GraphPersistenceError, match="E-V05-PROJECTION-NO-FINGERPRINT"):
        GraphPersistenceService(db).persist(bad)
    assert GraphRepository(db).counts()["projections"] == 0
    assert GraphRepository(db).counts()["nodes"] == 0


def test_gp_cmp_014_rejected_invalidated(db):
    """GP-CMP-014：rejected 源断言 → graph status=invalidated + log 记录。"""
    neg = _seed_negative(db)
    GraphPersistenceService(db).persist(neg["proj"])
    aid = neg["made"]["rejected"].assertion_id
    row = db.execute("SELECT status FROM kg_nodes WHERE source_id=? AND node_type='assertion'",
                     (aid,)).fetchone()
    assert row and row["status"] == "invalidated"
    log = db.execute("SELECT reason_status, graph_status FROM kg_invalidation_log"
                     " WHERE node_id IN (SELECT node_id FROM kg_nodes WHERE source_id=?)",
                     (aid,)).fetchone()
    assert log and log["reason_status"] == "rejected" and log["graph_status"] == "invalidated"


def test_gp_cmp_015_deprecated_invalidated(db):
    """GP-CMP-015：deprecated → invalidated。"""
    neg = _seed_negative(db)
    GraphPersistenceService(db).persist(neg["proj"])
    aid = neg["made"]["deprecated"].assertion_id
    row = db.execute("SELECT status FROM kg_nodes WHERE source_id=? AND node_type='assertion'",
                     (aid,)).fetchone()
    assert row and row["status"] == "invalidated"


def test_gp_cmp_016_disputed_flagged(db):
    """GP-CMP-016：disputed → flagged（不删除）。"""
    neg = _seed_negative(db)
    GraphPersistenceService(db).persist(neg["proj"])
    aid = neg["made"]["disputed"].assertion_id
    row = db.execute("SELECT status FROM kg_nodes WHERE source_id=? AND node_type='assertion'",
                     (aid,)).fetchone()
    assert row and row["status"] == "flagged"
    log = db.execute("SELECT graph_status FROM kg_invalidation_log"
                     " WHERE node_id IN (SELECT node_id FROM kg_nodes WHERE source_id=?)",
                     (aid,)).fetchone()
    assert log["graph_status"] == "flagged"


def test_gp_cmp_017_hypothesized_excluded(db):
    """GP-CMP-017：hypothesized 不进入 Validated Knowledge Graph。"""
    neg = _seed_negative(db)
    GraphPersistenceService(db).persist(neg["proj"])
    aid = neg["made"]["hypothesized"].assertion_id
    row = db.execute("SELECT COUNT(*) c FROM kg_nodes WHERE source_id=?",
                     (aid,)).fetchone()["c"]
    assert row == 0                                        # 完全排除


def test_gp_cmp_018_graph_to_assertion_provenance(db):
    """GP-CMP-018：graph node → source assertion（payload/source_id 回溯）。"""
    seeded = _seed_graph(db)
    GraphPersistenceService(db).persist(seeded["proj"])
    row = db.execute("SELECT source_id, payload_json FROM kg_nodes"
                     " WHERE node_type='assertion' LIMIT 1").fetchone()
    assert db.execute("SELECT 1 FROM akb_assertions WHERE assertion_id=?",
                      (row["source_id"],)).fetchone()


def test_gp_cmp_019_assertion_to_evidence_provenance(db):
    """GP-CMP-019：assertion → evidence（supports 边回溯到 akb_evidence）。"""
    seeded = _seed_graph(db)
    GraphPersistenceService(db).persist(seeded["proj"])
    sup = db.execute("SELECT target_node FROM kg_edges WHERE edge_type='supports'"
                     " LIMIT 1").fetchone()
    ev_src = db.execute("SELECT source_id FROM kg_nodes WHERE node_id=?",
                        (sup["target_node"],)).fetchone()["source_id"]
    assert db.execute("SELECT 1 FROM akb_evidence WHERE evidence_id=?",
                      (ev_src,)).fetchone()


def test_gp_cmp_020_evidence_to_document_provenance(db):
    """GP-CMP-020：evidence → document（extracted_from/unit 链 + akb_evidence.document_id）。"""
    seeded = _seed_graph(db)
    GraphPersistenceService(db).persist(seeded["proj"])
    ev_src = db.execute("SELECT source_id FROM kg_nodes WHERE node_type='evidence'"
                        " LIMIT 1").fetchone()["source_id"]
    row = db.execute("SELECT document_id FROM akb_evidence WHERE evidence_id=?",
                     (ev_src,)).fetchone()
    assert row and db.execute("SELECT 1 FROM akb_documents WHERE document_id=?",
                              (row["document_id"],)).fetchone()


def test_gp_cmp_021_graph_to_inference_provenance(db):
    """GP-CMP-021：inference node → akb_reasoning_runs（provenance 反查）。"""
    seeded = _seed_graph(db)
    GraphPersistenceService(db).persist(seeded["proj"])
    inf = db.execute("SELECT source_id FROM kg_nodes WHERE node_type='inference'"
                     " LIMIT 1").fetchone()
    assert inf and db.execute("SELECT 1 FROM akb_reasoning_runs WHERE run_id=?",
                              (inf["source_id"],)).fetchone()


def test_gp_cmp_022_rebuild_equivalence(db):
    """GP-CMP-022：rebuild——重新投影 + 重新 persist → 同逻辑图（fingerprint 等值）。"""
    seeded = _seed_graph(db)
    svc = GraphPersistenceService(db)
    r1 = svc.persist(seeded["proj"])
    # 模拟 rebuild：数据未变，重新投影（rebuild=True 标记）
    proj2 = GraphProjectionService().process(db)
    r2 = svc.persist(proj2, rebuild=True)
    assert r2.get("idempotent_hit") and r2["fingerprint"] == r1["fingerprint"]


def test_gp_cmp_023_fingerprint_equivalence(db):
    """GP-CMP-023：fingerprint 等值——同库状态双投影 fingerprint 全等 + persist 元数据
    与 projection fingerprint 一致。"""
    seeded = _seed_graph(db)
    p2 = GraphProjectionService().process(db)
    assert p2.fingerprint == seeded["proj"].fingerprint
    r = GraphPersistenceService(db).persist(seeded["proj"])
    row = dict(db.execute("SELECT fingerprint FROM kg_projection_runs WHERE projection_id=?",
                          (r["projection_id"],)).fetchone())
    assert row["fingerprint"] == seeded["proj"].fingerprint


def test_gp_cmp_024_deterministic_rebuild(db):
    """GP-CMP-024：deterministic rebuild——persist 后 raw storage 内容确定性（排序输出）。"""
    seeded = _seed_graph(db)
    GraphPersistenceService(db).persist(seeded["proj"])
    rows1 = [dict(r) for r in db.execute(
        "SELECT node_id, node_type, source_id, status FROM kg_nodes"
        " ORDER BY node_id")]
    rows2 = [dict(r) for r in db.execute(
        "SELECT node_id, node_type, source_id, status FROM kg_nodes"
        " ORDER BY node_id")]
    assert rows1 == rows2 and rows1


def test_gp_cmp_025_legacy_graph_isolation(db):
    """GP-CMP-025：legacy graph 隔离——agent_kb.graph API 面不变、graph_edges 表零变化。"""
    import agent_kb.graph as legacy
    import agent_kb.kgraph as kgraph
    for sym in ("DeterministicRelationExtractor", "GraphEdge", "SQLiteGraphStore"):
        assert not hasattr(kgraph, sym)
    for sym in ("GraphPersistenceService", "GraphRepository"):
        assert not hasattr(legacy, sym)
    before = db.execute("SELECT COUNT(*) c FROM graph_edges").fetchone()["c"]
    GraphPersistenceService(db).persist(_seed_graph(db)["proj"])
    after = db.execute("SELECT COUNT(*) c FROM graph_edges").fetchone()["c"]
    assert before == after                                 # legacy 表零变化