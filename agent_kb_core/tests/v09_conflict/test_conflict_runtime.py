# -*- coding: utf-8 -*-
"""CF-CMP-001..010（AKB-V09-IMPL-003：ConflictRuntime v2 acceptance）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.causal import CausalProjectionRuntime
from agent_kb.conflict import (
    ConflictError,
    ConflictRuntime,
    conflict_identity,
)
from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.storage.migrations import SchemaMigrator


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    SchemaMigrator(con).migrate()
    con.execute("INSERT INTO akb_sources (source_id, source_type, name)"
                " VALUES ('cf', 'document', 'CF')")
    con.execute("INSERT INTO akb_documents (document_id, source_id, version,"
                " content_hash, ingested_at) VALUES ('dcf', 'cf', '1.0', 'h',"
                " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    ev = EvidenceStore(con).create(document_id="dcf", content="冲突锚证据。",
                                   extraction_method="t")
    yield con, ev.evidence_id
    con.close()


def _snapshot(db):
    return {t: [tuple(r) for r in db.execute(f"SELECT * FROM {t} ORDER BY 1")]
            for t in ("akb_assertions", "kg_nodes", "kg_edges")}


def test_cf_cmp_001_basic_conflict_creation(db):
    """CF-CMP-001：basic conflict creation——值冲突 → ConflictRecord 全字段。"""
    con, eid = db
    st = AssertionStore(con)
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "20"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "25"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    rt = ConflictRuntime(con)
    records = rt.detect()
    assert records
    rec = [r for r in records if r.conflict_type == "ASSERTION_VALUE_CONFLICT"
           and r.target_refs == ("Temp",)][0]
    assert rec.conflict_id.startswith("cf_")
    assert rec.status == "open"            # 无 resolution 状态
    assert rec.severity == "medium"
    assert len(rec.source_refs) == 2


def test_cf_cmp_002_deterministic_conflict_id(db):
    """CF-CMP-002：deterministic conflict_id——同输入跨实例全等；输入变→变。"""
    con, eid = db
    st = AssertionStore(con)
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "20"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "25"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    r1 = ConflictRuntime(con).detect()
    r2 = ConflictRuntime(con).detect()
    assert [x.conflict_id for x in r1] == [x.conflict_id for x in r2]
    # 单元级 + 输入变化
    kw = dict(conflict_type="ASSERTION_VALUE_CONFLICT",
              source_refs=("a", "b"), target_refs=("T",),
              created_from_snapshot="snap_x")
    assert conflict_identity(**kw) == conflict_identity(**kw)
    assert conflict_identity(**kw) != conflict_identity(**{
        **kw, "created_from_snapshot": "snap_y"})


def test_cf_cmp_003_same_snapshot_rebuild(db):
    """CF-CMP-003：same snapshot rebuild——同投影/库面 → 同记录集。"""
    con, eid = db
    st = AssertionStore(con)
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "20"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "25"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    r1 = ConflictRuntime(con).detect()
    r2 = ConflictRuntime(con).detect()
    assert [x.fingerprint for x in r1] == [x.fingerprint for x in r2]


def test_cf_cmp_004_assertion_value_conflict_detection(db):
    """CF-CMP-004：assertion value conflict detection——同 subject+predicate
    不同值 → 记录；单值 → 零记录。"""
    con, eid = db
    st = AssertionStore(con)
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "20"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    assert not [r for r in ConflictRuntime(con).detect()
                if r.conflict_type == "ASSERTION_VALUE_CONFLICT"]
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "25"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    recs = [r for r in ConflictRuntime(con).detect()
            if r.conflict_type == "ASSERTION_VALUE_CONFLICT"]
    assert recs and recs[0].metadata and dict(recs[0].metadata)["values"] == \
        ["20", "25"]


def test_cf_cmp_005_causal_mechanism_conflict_detection(db):
    """CF-CMP-005：causal mechanism conflict detection——同 effect 多因果源 →
    CAUSAL_MECHANISM_CONFLICT（消费 CausalProjection）。"""
    con, eid = db
    st = AssertionStore(con)
    st.create_candidate(subject_ref="Overheat", predicate_ref="causes",
                        object={"kind": "literal", "value": "Aging"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    st.create_candidate(subject_ref="Overload", predicate_ref="causes",
                        object={"kind": "literal", "value": "Aging"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    recs = [r for r in ConflictRuntime(con).detect()
            if r.conflict_type == "CAUSAL_MECHANISM_CONFLICT"]
    assert recs
    rec = [r for r in recs if r.target_refs == ("Aging",)][0]
    assert rec.causal_refs and all(c.startswith("ce_") for c in rec.causal_refs)
    assert dict(rec.metadata)["detection"] == \
        "condition-set-mutual-exclusion"


def test_cf_cmp_006_unknown_conflict_type_rejection(db):
    """CF-CMP-006：unknown conflict type rejection——非白名单 fail-close。"""
    rt = ConflictRuntime(db[0])
    with pytest.raises(ConflictError, match="E-V09-CONFLICT-INVALID"):
        rt.detect(conflict_type="TELEPORT_CONFLICT")
    # 白名单类型正常
    rt.detect(conflict_type="ASSERTION_VALUE_CONFLICT")
    # 坏 id 读面拒绝
    with pytest.raises(ConflictError, match="E-V09-CONFLICT-INVALID"):
        rt.get_record("bad-id")


def test_cf_cmp_007_conflict_not_mutation(db):
    """CF-CMP-007：conflict ≠ mutation——检测全流程 akb_assertions/kg_nodes/
    kg_edges unchanged（Conflict ≠ Resolution ≠ Truth ≠ Mutation）。"""
    con, eid = db
    st = AssertionStore(con)
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "20"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "25"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    snap = _snapshot(con)
    ConflictRuntime(con).detect()
    assert snap["akb_assertions"] == [
        tuple(r) for r in con.execute("SELECT * FROM akb_assertions ORDER BY 1")]
    assert snap["kg_nodes"] == [
        tuple(r) for r in con.execute("SELECT * FROM kg_nodes ORDER BY 1")]
    assert snap["kg_edges"] == [
        tuple(r) for r in con.execute("SELECT * FROM kg_edges ORDER BY 1")]


def test_cf_cmp_008_provenance_audit(db):
    """CF-CMP-008：provenance audit——graph:conflict-detect 落 akb_provenance
    （conflict_id/type/source/target/severity/fingerprint）。"""
    con, eid = db
    st = AssertionStore(con)
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "20"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "25"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    records = ConflictRuntime(con).detect()
    rows = [dict(x) for x in con.execute(
        "SELECT * FROM akb_provenance WHERE activity='graph:conflict-detect'")]
    assert len(rows) == 1
    m = json.loads(rows[0]["metadata_json"])
    assert set(m["conflicts"]) == {r.conflict_id for r in records}
    assert m["snapshot"] == records[0].created_from_snapshot


def test_cf_cmp_009_immutable_conflict_record(db):
    """CF-CMP-009：immutable conflict record——frozen dataclass 赋值拒绝 +
    重复检测零重复审计（确定性检测）。"""
    con, eid = db
    st = AssertionStore(con)
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "20"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "25"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    rec = ConflictRuntime(con).detect()[0]
    with pytest.raises(Exception):
        rec.status = "dismissed"  # type: ignore[misc]
    ConflictRuntime(con).detect()
    n = con.execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                    " activity='graph:conflict-detect'").fetchone()["c"]
    # 第二次检测（同状态）——确定性检测不重复落审计（幂等语义与 projection 一致）
    assert n == 1


def test_cf_cmp_010_frozen_regression(db):
    """CF-CMP-010：frozen regression——V0.5..V0.9causal/health frozen 模块零感知
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
    import agent_kb.health.runtime as m12
    # frozen V0.5..V0.8 十模块：零字符串感知
    for mod in (m1, m2, m3, m4, m5, m6, m7, m8, m9, m10):
        assert "ConflictRuntime" not in inspect.getsource(mod)
    # V0.9 IMPL-001/002 模块：零语义依赖（不 import conflict——单向依赖保持；
    # docstring 中的 MIGRATION 决策文字引用不算依赖）
    for mod in (m11, m12):
        src_mod = inspect.getsource(mod)
        assert "from agent_kb.conflict" not in src_mod
        assert "import conflict" not in src_mod
    for sym in ("ConflictRuntime", "ConflictRecord"):
        assert not hasattr(legacy, sym)
    # 建图回归：检测后投影/查询面不变
    from agent_kb.kgraph import (
        GraphPersistenceService, GraphProjectionService, GraphQueryService)
    con = db[0]
    GraphPersistenceService(con).persist(GraphProjectionService().process(con))
    q = GraphQueryService(con)
    v1 = q.canonical_view()
    ConflictRuntime(con).detect()
    assert q.canonical_view() == v1