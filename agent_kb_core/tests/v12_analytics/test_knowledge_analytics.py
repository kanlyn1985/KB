# -*- coding: utf-8 -*-
"""V12-ANALYTICS-CMP-001..012（AKB-V12-IMPL-001：Knowledge Analytics Runtime）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.analytics import (
    AnalyticsError,
    KnowledgeAnalyticsRuntime,
    analytics_report_identity,
)
from agent_kb.causal import CausalProjectionRuntime, ScalePersistenceRuntime
from agent_kb.conflict import ConflictRuntime
from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.health import KnowledgeHealthRuntime
from agent_kb.hypothesis import HypothesisService
from agent_kb.maintenance import MaintenanceProposalRuntime
from agent_kb.storage.migrations import SchemaMigrator


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(
        ":memory:", isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    SchemaMigrator(con).migrate()
    con.execute("INSERT INTO akb_sources (source_id, source_type, name)"
                " VALUES ('a12', 'document', 'A12')")
    con.execute("INSERT INTO akb_documents (document_id, source_id, version,"
                " content_hash, ingested_at) VALUES ('da12', 'a12', '1.0',"
                " 'h', strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    ev = EvidenceStore(con).create(document_id="da12", content="分析锚证据。",
                                   extraction_method="t")
    yield con, ev.evidence_id
    con.close()


import sqlite3


def _seed_rich(db):
    """种子：因果断言+健康信号+冲突+提案（全层数据）。"""
    con, eid = db
    st = AssertionStore(con)
    st.create_candidate(subject_ref="Heat", predicate_ref="causes",
                        object={"kind": "literal", "value": "Aging"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    proj = CausalProjectionRuntime(con).project()
    ScalePersistenceRuntime(con).persist_causal_edges(proj)
    hs = HypothesisService(con)
    kh = KnowledgeHealthRuntime(con, causal_runtime=CausalProjectionRuntime(con))
    hyp = hs.create_hypothesis(statement="H: A12", domain_ref="industrial",
                               pack_ref="dpr_a", policy_ref="pol_b",
                               context_ref="grc_c", origin="human")
    h = kh.create_health(target_ref=hyp.hypothesis_id,
                         target_type="hypothesis")
    ScalePersistenceRuntime(con).persist_health_signals(h)
    mp = MaintenanceProposalRuntime(con)
    proposal = mp.create_proposal_from_signal(h.health_id)
    # task start+complete（治理效率分子）
    from agent_kb.hypothesis import VerificationTaskRuntime
    tr = VerificationTaskRuntime(con)
    tr.start_task(proposal.proposal_id, actor_id="human:ops")
    tr.complete_task(proposal.proposal_id, actor_id="human:ops")
    return proj


def _snapshot(db):
    return {t: [tuple(r) for r in db.execute(f"SELECT * FROM {t} ORDER BY 1")]
            for t in ("akb_assertions", "kg_nodes", "kg_edges")}


def test_v12_analytics_cmp_001_create_report_basic(db):
    """V12-ANALYTICS-CMP-001：create report basic——五 metrics 全存在。"""
    _seed_rich(db)
    r = KnowledgeAnalyticsRuntime(db[0]).create_report()
    assert r.report_id.startswith("anr_")
    assert r.metric_count == 5
    assert {m["metric"] for m in r.metrics} == {
        "knowledge_growth", "knowledge_drift", "governance_efficiency",
        "proposal_resolution_rate", "causal_coverage_trend"}
    assert r.schema_version == 1


def test_v12_analytics_cmp_002_metric_whitelist(db):
    """V12-ANALYTICS-CMP-002：metric whitelist——非法 scope fail-close。"""
    rt = KnowledgeAnalyticsRuntime(db[0])
    with pytest.raises(AnalyticsError, match="E-V12-ANALYTICS-INVALID"):
        rt.create_report(scope="teleport")
    # 白名单内正常
    rt.create_report(scope="global")


def test_v12_analytics_cmp_003_deterministic_identity(db):
    """V12-ANALYTICS-CMP-003：deterministic identity——同状态双实例同 report_id/
    fingerprint。"""
    _seed_rich(db)
    r1 = KnowledgeAnalyticsRuntime(db[0]).create_report()
    r2 = KnowledgeAnalyticsRuntime(db[0]).create_report()
    assert r1.report_id == r2.report_id
    assert r1.fingerprint == r2.fingerprint
    # 单元级复算
    m = ({"metric": "x", "value": 1.0, "detail": "d"},)
    assert analytics_report_identity(scope="global", metrics=m) == \
        analytics_report_identity(scope="global", metrics=m)


def test_v12_analytics_cmp_004_different_snapshot(db):
    """V12-ANALYTICS-CMP-004：different snapshot——新断言 → identity 变。"""
    _seed_rich(db)
    r1 = KnowledgeAnalyticsRuntime(db[0]).create_report()
    st = AssertionStore(db[0])
    st.create_candidate(subject_ref="New", predicate_ref="has_value",
                        object={"kind": "literal", "value": "1"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[db[1]])
    r2 = KnowledgeAnalyticsRuntime(db[0]).create_report()
    assert r2.report_id != r1.report_id


def test_v12_analytics_cmp_005_canonical_ordering(db):
    """V12-ANALYTICS-CMP-005：canonical ordering——metrics 按 metric 名 ASC
    （构造顺序无关）。"""
    _seed_rich(db)
    r = KnowledgeAnalyticsRuntime(db[0]).create_report()
    names = [m["metric"] for m in r.metrics]
    assert names == sorted(names)


def test_v12_analytics_cmp_006_float_determinism(db):
    """V12-ANALYTICS-CMP-006：float determinism——round(4) 精度一致（治理效率
    比例）。"""
    _seed_rich(db)
    r1 = KnowledgeAnalyticsRuntime(db[0]).create_report()
    r2 = KnowledgeAnalyticsRuntime(db[0]).create_report()
    ge1 = {m["metric"]: m for m in r1.metrics}["governance_efficiency"]
    ge2 = {m["metric"]: m for m in r2.metrics}["governance_efficiency"]
    assert ge1["value"] == ge2["value"]
    assert round(ge1["value"], 4) == ge1["value"]


def test_v12_analytics_cmp_007_empty_knowledge_base(db):
    """V12-ANALYTICS-CMP-007：empty knowledge base——zero metrics 零 fabricate。"""
    r = KnowledgeAnalyticsRuntime(db[0]).create_report()
    m = {x["metric"]: x for x in r.metrics}
    assert m["knowledge_growth"]["value"] == 0.0
    assert "assertions=0" in m["knowledge_growth"]["detail"]
    assert m["knowledge_drift"]["value"] == 0.0
    assert m["governance_efficiency"]["value"] == 0.0


def test_v12_analytics_cmp_008_no_mutation_assertions(db):
    """V12-ANALYTICS-CMP-008：no mutation assertions——报告全流程
    akb_assertions unchanged。"""
    _seed_rich(db)
    snap = [tuple(r) for r in db[0].execute(
        "SELECT * FROM akb_assertions ORDER BY 1")]
    rt = KnowledgeAnalyticsRuntime(db[0])
    rt.create_report()
    rt.create_report()
    assert [tuple(r) for r in db[0].execute(
        "SELECT * FROM akb_assertions ORDER BY 1")] == snap


def test_v12_analytics_cmp_009_no_mutation_graph(db):
    """V12-ANALYTICS-CMP-009：no mutation graph——kg_nodes/kg_edges 一致。"""
    _seed_rich(db)
    n_n = db[0].execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"]
    n_e = db[0].execute("SELECT COUNT(*) c FROM kg_edges").fetchone()["c"]
    KnowledgeAnalyticsRuntime(db[0]).create_report()
    assert db[0].execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"] == n_n
    assert db[0].execute("SELECT COUNT(*) c FROM kg_edges").fetchone()["c"] == n_e


def test_v12_analytics_cmp_010_no_governance_bridge(db):
    """V12-ANALYTICS-CMP-010：no governance bridge——analytics 零产生 proposal/
    task（Proposal ≠ Decision）。"""
    _seed_rich(db)
    before_p = db[0].execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                             " activity='graph:maintenance-proposal-create'"
                             ).fetchone()["c"]
    before_t = db[0].execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                             " activity LIKE 'graph:verification-task-%'"
                             ).fetchone()["c"]
    KnowledgeAnalyticsRuntime(db[0]).create_report()
    assert db[0].execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                         " activity='graph:maintenance-proposal-create'"
                         ).fetchone()["c"] == before_p
    assert db[0].execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                         " activity LIKE 'graph:verification-task-%'"
                         ).fetchone()["c"] == before_t


def test_v12_analytics_cmp_011_provenance_audit(db):
    """V12-ANALYTICS-CMP-011：provenance audit——graph:analytics-report-create
    落 akb_provenance（report_id/scope/metric_names/fingerprint/actor）+ 幂等。"""
    _seed_rich(db)
    r = KnowledgeAnalyticsRuntime(db[0]).create_report()
    rows = [dict(x) for x in db[0].execute(
        "SELECT * FROM akb_provenance WHERE activity ="
        " 'graph:analytics-report-create'")]
    assert len(rows) == 1
    m = json.loads(rows[0]["metadata_json"])
    assert m["report_id"] == r.report_id
    assert m["scope"] == "global"
    assert m["fingerprint"] == r.fingerprint
    assert len(m["metric_names"]) == 5
    # 幂等（重复 create 零重复审计）
    KnowledgeAnalyticsRuntime(db[0]).create_report()
    n2 = db[0].execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                       " activity='graph:analytics-report-create'"
                       ).fetchone()["c"]
    assert n2 == 1


def test_v12_analytics_cmp_012_frozen_regression(db):
    """V12-ANALYTICS-CMP-012：frozen regression——V0.5..V0.11 frozen 模块零感知
    + legacy 互斥 + 建图回归。"""
    import inspect
    import agent_kb.graph as legacy
    import agent_kb.kgraph.orchestrator as m1
    import agent_kb.domains.runtime as m2
    import agent_kb.rules.runtime as m3
    import agent_kb.policy.runtime as m4
    import agent_kb.domains.guard as m5
    import agent_kb.hypothesis.runtime as m6
    import agent_kb.hypothesis.verification as m7
    import agent_kb.hypothesis.verdict as m8
    import agent_kb.causal.projection as m9
    import agent_kb.health.runtime as m10
    import agent_kb.conflict.runtime as m11
    import agent_kb.storage.query as m12
    import agent_kb.storage.registry_snapshot as m13
    import agent_kb.maintenance.runtime as m14
    for mod in (m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11, m12, m13, m14):
        assert "KnowledgeAnalyticsRuntime" not in inspect.getsource(mod)
    for sym in ("KnowledgeAnalyticsRuntime", "KnowledgeMetricReport"):
        assert not hasattr(legacy, sym)
    # 建图回归
    from agent_kb.kgraph import (
        GraphPersistenceService, GraphProjectionService, GraphQueryService)
    con = db[0]
    GraphPersistenceService(con).persist(GraphProjectionService().process(con))
    qv = GraphQueryService(con)
    v1 = qv.canonical_view()
    _seed_rich(db)
    KnowledgeAnalyticsRuntime(con).create_report()
    assert qv.canonical_view() == v1