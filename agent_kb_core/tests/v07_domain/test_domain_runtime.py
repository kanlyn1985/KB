# -*- coding: utf-8 -*-
"""DP-CMP-001..010（AKB-V07-IMPL-001：DomainPack Runtime acceptance）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.domains.runtime import (
    DomainPackRuntime,
    DomainPackRuntimeError,
    LoadedPack,
)
from agent_kb.domains.schema import (
    DomainPack,
    ObjectTypeSpec,
    RelationTypeSpec,
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


def _pack(domain_id="industrial", version="1.0.0", term=None, rel_types=None) -> DomainPack:
    return DomainPack(
        domain_id=domain_id, name="Industrial Pack", version=version,
        description="V0.7 test pack",
        object_types={"Parameter": ObjectTypeSpec(name="Parameter",
                                                  description="设备参数"),
                      "Equipment": ObjectTypeSpec(name="Equipment")},
        relation_types=rel_types or {
            "has_parameter": RelationTypeSpec(
                name="has_parameter", source_types=["Equipment"],
                target_types=["Parameter"])},
        terminology={"额定电压": ["rated voltage", "nominal voltage"]})


def test_dp_cmp_001_pack_load(db):
    """DP-CMP-001：pack load——frozen DomainPack → LoadedPack（全字段）。"""
    rt = DomainPackRuntime(db)
    lp = rt.load_runtime_pack(_pack())
    assert isinstance(lp, LoadedPack)
    assert lp.domain_id == "industrial" and lp.version == "1.0.0"
    assert lp.namespace == "industrial"
    assert lp.pack_ref.startswith("dpr_")
    assert "额定电压" in lp.pack.terminology
    assert "industrial:额定电压" in lp.terminology_namespaced


def test_dp_cmp_002_schema_validation(db):
    """DP-CMP-002：schema validation——frozen schema 校验（关系端点类型检查）。"""
    rt = DomainPackRuntime(db)
    bad = DomainPack(
        domain_id="bad", name="Bad", version="1.0",
        object_types={"A": ObjectTypeSpec(name="A")},
        relation_types={"r": RelationTypeSpec(name="r", source_types=["A"],
                                              target_types=["Ghost"])})
    with pytest.raises(DomainPackRuntimeError, match="E-V07-PACK-INVALID"):
        rt.load_runtime_pack(bad)


def test_dp_cmp_003_deterministic_pack_id(db):
    """DP-CMP-003：deterministic pack_id——同 pack 跨实例/双注册全等；内容变化→变。"""
    db2 = None
    rt1 = DomainPackRuntime(db)
    lp1 = rt1.load_runtime_pack(_pack())
    lp2 = rt1.load_runtime_pack(_pack())          # 同实例重复加载（幂等）
    assert lp1.pack_ref == lp2.pack_ref
    # 跨实例
    con2 = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con2.row_factory = pytest.importorskip("sqlite3").Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con2).migrate()
    lp3 = DomainPackRuntime(con2).load_runtime_pack(_pack())
    assert lp3.pack_ref == lp1.pack_ref
    # 内容变化 → ref 变（deterministic 差异）
    lp4 = rt1.load_runtime_pack(_pack(version="1.1.0"))
    assert lp4.pack_ref != lp1.pack_ref
    con2.close()


def test_dp_cmp_004_version_conflict_fail_close(db):
    """DP-CMP-004：version 管理——同 domain 多版本共存；namespace 冲突 fail-close。"""
    rt = DomainPackRuntime(db)
    rt.load_runtime_pack(_pack(version="1.0.0"))
    rt.load_runtime_pack(_pack(version="2.0.0"))
    assert rt.get_pack("industrial").version == "2.0.0"   # 最新版本
    assert rt.get_pack("industrial", version="1.0.0").version == "1.0.0"
    # namespace 冲突：不同 domain 抢同一 ns → fail-close
    with pytest.raises(DomainPackRuntimeError,
                       match="E-V07-PACK-NAMESPACE-CONFLICT"):
        rt.load_runtime_pack(_pack(domain_id="finance"), namespace="industrial")


def test_dp_cmp_005_invalid_pack_reject(db):
    """DP-CMP-005：invalid pack reject——空 id/空 version/空术语键全拒绝。"""
    rt = DomainPackRuntime(db)
    with pytest.raises(DomainPackRuntimeError, match="E-V07-PACK-INVALID"):
        rt.load_runtime_pack(_pack(domain_id=" "))
    with pytest.raises(DomainPackRuntimeError, match="E-V07-PACK-INVALID"):
        rt.load_runtime_pack(_pack(version=" "))
    bad_term = _pack()
    object.__setattr__(bad_term, "terminology", {" ": []})
    with pytest.raises(DomainPackRuntimeError, match="E-V07-PACK-INVALID"):
        rt.load_runtime_pack(bad_term)
    # 非法 ns（含冒号）拒绝
    with pytest.raises(DomainPackRuntimeError, match="E-V07-PACK-INVALID"):
        rt.load_runtime_pack(_pack(), namespace="bad:ns")


def test_dp_cmp_006_provenance_pack_load_audit(db):
    """DP-CMP-006：provenance pack-load audit——graph:pack-load 落 akb_provenance
    （复用零第二套）；重复加载零重复审计。"""
    rt = DomainPackRuntime(db)
    rt.load_runtime_pack(_pack())
    rows = [dict(x) for x in db.execute(
        "SELECT * FROM akb_provenance WHERE activity='graph:pack-load'")]
    assert len(rows) == 1
    m = json.loads(rows[0]["metadata_json"])
    assert m["domain_ids"] == ["industrial"] and m["version"] == "1.0.0"
    assert m["namespace"] == "industrial"
    assert m["pack_ref"].startswith("dpr_")
    # 重复加载 → 零新增审计
    rt.load_runtime_pack(_pack())
    n = db.execute("SELECT COUNT(*) c FROM akb_provenance"
                   " WHERE activity='graph:pack-load'").fetchone()["c"]
    assert n == 1


def test_dp_cmp_007_canonical_ordering(db):
    """DP-CMP-007：canonical ordering——list_packs 排序稳定；terminology ns 视图
    键有序。"""
    rt = DomainPackRuntime(db)
    rt.load_runtime_pack(_pack(domain_id="zeta"))
    rt.load_runtime_pack(_pack(domain_id="alpha"))
    names = [lp.domain_id for lp in rt.list_packs()]
    assert names == sorted(names)
    lp = rt.load_runtime_pack(_pack())
    keys = list(lp.terminology_namespaced)
    assert keys == sorted(keys)


def test_dp_cmp_008_v06_reasoning_integration(db):
    """DP-CMP-008：V0.6 reasoning integration——pack 加载后 V0.6 全链路
    （context→orchestrator→provenance）行为不变；pack 提供配置不产生事实。"""
    # 复用 V0.6 fixture 模式建图
    from agent_kb.evidence_core import EvidenceStore
    from agent_kb.evidence_core.assertions import AssertionStore
    from agent_kb.kgraph import (
        GraphContextBuilder,
        GraphPersistenceService,
        GraphProjectionService,
        GraphQueryService,
        GraphReasoningOrchestrator,
        ReasoningProvenanceService,
    )
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('dp', 'document', 'DP')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version,"
               " content_hash, ingested_at) VALUES ('ddp', 'dp', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    eid = EvidenceStore(db).create(document_id="ddp", content="流程 T1 先于流程 T2。",
                                   extraction_method="t").evidence_id
    st = AssertionStore(db)
    ab = st.create_candidate(subject_ref="T1", predicate_ref="before",
                             object={"kind": "literal", "value": "T2"},
                             assertion_type="extracted", ontology_scope="test",
                             actor_id="system:seed", confidence=0.9,
                             evidence_refs=[eid])
    bc = st.create_candidate(subject_ref="T2", predicate_ref="before",
                             object={"kind": "literal", "value": "T3"},
                             assertion_type="extracted", ontology_scope="test",
                             actor_id="system:seed", confidence=0.9,
                             evidence_refs=[eid])
    GraphPersistenceService(db).persist(GraphProjectionService().process(db))
    q = GraphQueryService(db)
    root = next(n.node_id for n in q.query_nodes(node_type="entity", limit=1000)
                if n.payload.get("canonical_form") in ("T1", "T2", "T3"))
    v_before = q.canonical_view()
    # pack 加载（零图写入）
    rt = DomainPackRuntime(db)
    rt.load_runtime_pack(_pack())
    assert q.canonical_view() == v_before
    # V0.6 全链路继续工作（orchestrator 复用——pack 不改变推理语义）
    ctx = GraphContextBuilder().build(db, root_entity=root)
    r = GraphReasoningOrchestrator(db).run(ctx)
    assert r["status"] in ("completed", "partial")
    tr = ReasoningProvenanceService(db).trace_run(r["run_id"])
    assert tr.candidates
    # 候选恒 candidate（pack 未改变生命周期）
    for a in r["candidates"]:
        row = db.execute("SELECT status FROM akb_assertions WHERE assertion_id=?",
                         (a.assertion_id,)).fetchone()
        assert row["status"] == "candidate"


def test_dp_cmp_009_namespace_isolation(db):
    """DP-CMP-009：namespace isolation——同术语不同域 ns 隔离；术语视图零交叉。"""
    rt = DomainPackRuntime(db)
    ind = rt.load_runtime_pack(_pack(domain_id="industrial"))
    fin = rt.load_runtime_pack(_pack(domain_id="finance"))
    assert ind.namespace != fin.namespace
    assert all(k.startswith("industrial:") for k in ind.terminology_namespaced)
    assert all(k.startswith("finance:") for k in fin.terminology_namespaced)
    assert not (set(ind.terminology_namespaced) & set(fin.terminology_namespaced))


def test_dp_cmp_010_frozen_regression(db):
    """DP-CMP-010：frozen regression——V0.6 套件 + V0.5 面零影响（pack 加载后
    V0.6 context/orchestrator/provenance 测试套件可独立通过由全量回归保证；
    此处锚定：runtime 零触碰 frozen 文件 + legacy graph 隔离）。"""
    import agent_kb.graph as legacy
    import agent_kb.domains.schema as schema_mod
    import agent_kb.domains.loader as loader_mod
    # frozen schema/loader 文件零修改（源码审计——frozen 类字段签名不变）
    src_schema = inspect_getsource(schema_mod)
    assert "runtime" not in src_schema.lower()      # schema.py 未被 runtime 污染
    src_loader = inspect_getsource(loader_mod)
    assert "pack_ref" not in src_loader             # loader 未被 runtime 污染
    # legacy graph API 面互斥
    for sym in ("DomainPackRuntime", "LoadedPack"):
        assert not hasattr(legacy, sym)
    # graph_edges 表零变化
    before = db.execute("SELECT COUNT(*) c FROM graph_edges").fetchone()["c"]
    DomainPackRuntime(db).load_runtime_pack(_pack())
    after = db.execute("SELECT COUNT(*) c FROM graph_edges").fetchone()["c"]
    assert before == after


def inspect_getsource(module):
    import inspect
    return inspect.getsource(module)