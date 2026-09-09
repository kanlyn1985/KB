# -*- coding: utf-8 -*-
"""V12-ANALYTICS-QUERY-CMP-001..012（AKB-V12-IMPL-002：Analytics Query Layer）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.analytics import (
    AnalyticsQueryError,
    AnalyticsQueryRuntime,
    KnowledgeAnalyticsRuntime,
)
from agent_kb.causal import CausalProjectionRuntime, ScalePersistenceRuntime
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
                " VALUES ('q12', 'document', 'Q12')")
    con.execute("INSERT INTO akb_documents (document_id, source_id, version,"
                " content_hash, ingested_at) VALUES ('dq12', 'q12', '1.0',"
                " 'h', strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    ev = EvidenceStore(con).create(document_id="dq12", content="查询锚证据。",
                                   extraction_method="t")
    yield con, ev.evidence_id
    con.close()


import sqlite3


def _make_reports(db, n=5):
    """生成 n 份报告（每份间插入新断言改变状态）。"""
    con, eid = db
    st = AssertionStore(con)
    rt = KnowledgeAnalyticsRuntime(con)
    ids = []
    for i in range(n):
        if i:
            st.create_candidate(subject_ref=f"S{i}", predicate_ref="has_value",
                                object={"kind": "literal", "value": str(i)},
                                assertion_type="extracted",
                                ontology_scope="test", actor_id="system:seed",
                                confidence=0.9, evidence_refs=[eid])
        r = rt.create_report()
        ids.append(r.report_id)
    return ids


def test_v12_analytics_query_cmp_001_basic_query(db):
    """V12-ANALYTICS-QUERY-CMP-001：basic report query——5 报告全查 + page 正确。"""
    ids = _make_reports(db, 5)
    page = AnalyticsQueryRuntime(db[0]).list_reports()
    assert len(page.items) == 5 and not page.has_more and page.next_cursor is None
    assert [i["report_id"] for i in page.items] == sorted(ids)


def test_v12_analytics_query_cmp_002_scope_filtering(db):
    """V12-ANALYTICS-QUERY-CMP-002：scope filtering——精确匹配。"""
    _make_reports(db, 2)
    q = AnalyticsQueryRuntime(db[0])
    assert len(q.list_reports(scope="global").items) == 2
    assert len(q.list_reports(scope="domain:x").items) == 0


def test_v12_analytics_query_cmp_003_metric_filtering(db):
    """V12-ANALYTICS-QUERY-CMP-003：metric filtering——白名单通过 + 未知拒绝。"""
    _make_reports(db, 2)
    q = AnalyticsQueryRuntime(db[0])
    assert len(q.list_reports(metric="knowledge_growth").items) == 2
    with pytest.raises(AnalyticsQueryError, match="E-V12-QUERY-INVALID"):
        q.list_reports(metric="teleport_metric")


def test_v12_analytics_query_cmp_004_cursor_pagination(db):
    """V12-ANALYTICS-QUERY-CMP-004：cursor pagination——5 报告 limit=2 三页
    无重无漏。"""
    ids = set(_make_reports(db, 5))
    q = AnalyticsQueryRuntime(db[0])
    seen = []
    cursor = None
    for _ in range(3):
        page = q.list_reports(limit=2, cursor=cursor)
        seen += [i["report_id"] for i in page.items]
        if not page.has_more:
            break
        cursor = page.next_cursor
    assert len(seen) == 5 and len(set(seen)) == 5 and set(seen) == ids


def test_v12_analytics_query_cmp_005_cursor_replay(db):
    """V12-ANALYTICS-QUERY-CMP-005：cursor replay——同 cursor same output。"""
    _make_reports(db, 5)
    q = AnalyticsQueryRuntime(db[0])
    p1a = q.list_reports(limit=2)
    p1b = q.list_reports(limit=2)
    assert p1a.next_cursor == p1b.next_cursor
    p2a = q.list_reports(limit=2, cursor=p1a.next_cursor)
    p2b = q.list_reports(limit=2, cursor=p1b.next_cursor)
    assert [i["report_id"] for i in p2a.items] == \
        [i["report_id"] for i in p2b.items]


def test_v12_analytics_query_cmp_006_invalid_cursor(db):
    """V12-ANALYTICS-QUERY-CMP-006：invalid cursor——篡改指纹/错 query kind/
    非法 JSON 全拒。"""
    _make_reports(db, 3)
    q = AnalyticsQueryRuntime(db[0])
    cur = q.list_reports(limit=2).next_cursor
    fp, body = cur.split(".", 1)
    with pytest.raises(AnalyticsQueryError,
                       match="E-V12-QUERY-CURSOR-INVALID"):
        q.list_reports(limit=2, cursor="deadbeef." + body)
    with pytest.raises(AnalyticsQueryError,
                       match="E-V12-QUERY-CURSOR-INVALID"):
        q.list_reports(limit=2, cursor="x.not-json{")
    # V0.10 causal 模式 cursor kind 不匹配
    wrong = '{"kind": "causal_edges", "last_key": "ce_x"}'
    wrong_cur = __import__("hashlib").sha256(
        wrong.encode()).hexdigest()[:8] + "." + wrong
    with pytest.raises(AnalyticsQueryError,
                       match="E-V12-QUERY-CURSOR-INVALID"):
        q.list_reports(limit=2, cursor=wrong_cur)


def test_v12_analytics_query_cmp_007_deterministic_ordering(db):
    """V12-ANALYTICS-QUERY-CMP-007：deterministic ordering——report_id ASC
    多次查询一致。"""
    _make_reports(db, 4)
    q = AnalyticsQueryRuntime(db[0])
    ids1 = [i["report_id"] for i in q.list_reports().items]
    ids2 = [i["report_id"] for i in q.list_reports().items]
    assert ids1 == ids2 == sorted(ids1)


def test_v12_analytics_query_cmp_008_empty_result(db):
    """V12-ANALYTICS-QUERY-CMP-008：empty result——items=[]/cursor=None/
    has_more=False 零 fabricate。"""
    q = AnalyticsQueryRuntime(db[0])
    page = q.list_reports()
    assert page.items == () and page.next_cursor is None and not page.has_more


def test_v12_analytics_query_cmp_009_readonly_isolation(db):
    """V12-ANALYTICS-QUERY-CMP-009：readonly isolation——查询全流程
    akb_assertions/kg_nodes/kg_edges unchanged。"""
    _make_reports(db, 3)
    con = db[0]
    snap = {t: [tuple(r) for r in con.execute(f"SELECT * FROM {t} ORDER BY 1")]
            for t in ("akb_assertions", "kg_nodes", "kg_edges")}
    q = AnalyticsQueryRuntime(con)
    q.list_reports()
    q.list_reports(limit=2, cursor=q.list_reports(limit=1).next_cursor)
    for t, rows in snap.items():
        assert [tuple(r) for r in con.execute(
            f"SELECT * FROM {t} ORDER BY 1")] == rows, t


def test_v12_analytics_query_cmp_010_no_governance_bridge(db):
    """V12-ANALYTICS-QUERY-CMP-010：no governance bridge——查询零产生
    proposal/task/maintenance action（计数实测）。"""
    _make_reports(db, 3)
    con = db[0]
    counts_before = {act: con.execute(
        "SELECT COUNT(*) c FROM akb_provenance WHERE activity = ?",
        (act,)).fetchone()["c"]
        for act in ("graph:maintenance-proposal-create",
                    "graph:verification-task-create",
                    "graph:maintenance-proposal-create")}
    AnalyticsQueryRuntime(con).list_reports()
    for act, n in counts_before.items():
        assert con.execute(
            "SELECT COUNT(*) c FROM akb_provenance WHERE activity = ?",
            (act,)).fetchone()["c"] == n, act


def test_v12_analytics_query_cmp_011_provenance_replay(db):
    """V12-ANALYTICS-QUERY-CMP-011：provenance replay——同 provenance 恢复同
    report identity（跨 runtime 实例）。"""
    _make_reports(db, 3)
    q1 = AnalyticsQueryRuntime(db[0]).list_reports()
    q2 = AnalyticsQueryRuntime(db[0]).list_reports()
    assert [i["report_id"] for i in q1.items] == \
        [i["report_id"] for i in q2.items]
    assert [i["fingerprint"] for i in q1.items] == \
        [i["fingerprint"] for i in q2.items]


def test_v12_analytics_query_cmp_012_frozen_regression(db):
    """V12-ANALYTICS-QUERY-CMP-012：frozen regression——V0.5..V0.11 frozen
    模块零感知（analytics/runtime.py 内部复用除外）+ legacy 互斥 + 建图回归。"""
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
    import agent_kb.causal.persistence as m10
    import agent_kb.health.runtime as m11
    import agent_kb.conflict.runtime as m12
    import agent_kb.storage.query as m13
    import agent_kb.storage.registry_snapshot as m14
    import agent_kb.maintenance.runtime as m15
    import agent_kb.analytics.runtime as m16
    for mod in (m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11, m12, m13, m14,
                m15, m16):
        assert "AnalyticsQueryRuntime" not in inspect.getsource(mod)
    for sym in ("AnalyticsQueryRuntime", "AnalyticsQueryCursor"):
        assert not hasattr(legacy, sym)
    # 建图回归
    from agent_kb.kgraph import (
        GraphPersistenceService, GraphProjectionService, GraphQueryService)
    con = db[0]
    GraphPersistenceService(con).persist(GraphProjectionService().process(con))
    qv = GraphQueryService(con)
    v1 = qv.canonical_view()
    _make_reports(db, 2)
    AnalyticsQueryRuntime(con).list_reports()
    assert qv.canonical_view() == v1