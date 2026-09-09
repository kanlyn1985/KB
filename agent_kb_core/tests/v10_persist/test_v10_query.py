# -*- coding: utf-8 -*-
"""V10-QUERY-CMP-001..012（AKB-V10-IMPL-002：Persistence Query Layer）。"""
from __future__ import annotations

import sqlite3

import pytest

from agent_kb.causal import (
    CausalProjectionRuntime,
    ScalePersistenceRuntime,
)
from agent_kb.conflict import ConflictRuntime
from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.health import KnowledgeHealthRuntime
from agent_kb.hypothesis import HypothesisService
from agent_kb.storage.migrations import ALL_MIGRATIONS, SchemaMigrator
from agent_kb.storage.query import QueryError, ScaleQueryRuntime


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(
        ":memory:", isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    SchemaMigrator(con).migrate()
    con.execute("INSERT INTO akb_sources (source_id, source_type, name)"
                " VALUES ('q10', 'document', 'Q10')")
    con.execute("INSERT INTO akb_documents (document_id, source_id, version,"
                " content_hash, ingested_at) VALUES ('dq10', 'q10', '1.0',"
                " 'h', strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    ev = EvidenceStore(con).create(document_id="dq10", content="查询锚证据。",
                                   extraction_method="t")
    yield con, ev.evidence_id
    con.close()


def _seed_causal(con, eid, specs=(("Heat", "Aging"), ("Load", "Wear"),
                                  ("Vibration", "Noise"))):
    st = AssertionStore(con)
    for subj, obj in specs:
        st.create_candidate(subject_ref=subj, predicate_ref="causes",
                            object={"kind": "literal", "value": obj},
                            assertion_type="extracted", ontology_scope="test",
                            actor_id="system:seed", confidence=0.9,
                            evidence_refs=[eid])


def _seed_all(db):
    con, eid = db
    _seed_causal(con, eid)
    proj = CausalProjectionRuntime(con).project()
    ScalePersistenceRuntime(con).persist_causal_edges(proj)
    hs = HypothesisService(con)
    kh = KnowledgeHealthRuntime(con,
                                causal_runtime=CausalProjectionRuntime(con))
    for stmt in ("H: q1", "H: q2", "H: q3"):
        hyp = hs.create_hypothesis(statement=stmt, domain_ref="industrial",
                                   pack_ref="dpr_a", policy_ref="pol_b",
                                   context_ref="grc_c", origin="human")
        h = kh.create_health(target_ref=hyp.hypothesis_id,
                             target_type="hypothesis")
        ScalePersistenceRuntime(con).persist_health_signals(h)
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
    ScalePersistenceRuntime(con).persist_conflict_records(records)
    return proj, records


def test_v10_query_cmp_001_causal_query_basic(db):
    """V10-QUERY-CMP-001：causal query basic——三边全出 + has_more=False。"""
    _seed_all(db)
    r = ScaleQueryRuntime(db[0]).list_causal_edges()
    assert r["count"] == 3 and not r["has_more"] and r["next_cursor"] is None


def test_v10_query_cmp_002_causal_filter_correctness(db):
    """V10-QUERY-CMP-002：causal filter correctness——cause/effect/relation
    过滤正交。"""
    _seed_all(db)
    q = ScaleQueryRuntime(db[0])
    assert [x["cause_ref"] for x in
            q.list_causal_edges(effect_ref="Aging")["items"]] == ["Heat"]
    assert q.list_causal_edges(relation="causes")["count"] == 3
    assert q.list_causal_edges(relation="enables")["count"] == 0
    assert q.list_causal_edges(cause_ref="Load")["count"] == 1


def test_v10_query_cmp_003_health_history_query(db):
    """V10-QUERY-CMP-003：health history query——target 过滤 + 时间面（provenance
    occurred_at JOIN）。"""
    _seed_all(db)
    con = db[0]
    q = ScaleQueryRuntime(con)
    hid = con.execute("SELECT DISTINCT health_id FROM"
                      " akb_health_signals LIMIT 1").fetchone()[0]
    r = q.list_health_signals(target_ref=None)
    assert r["count"] == 12            # 3 hyp × 4 signals
    # 时间过滤（from_time=远未来 → 空；远过去 → 全量）
    assert q.list_health_signals(from_time="2999-01-01T00:00:00Z")["count"] == 0
    assert q.list_health_signals(from_time="2000-01-01T00:00:00Z")["count"] == 12


def test_v10_query_cmp_004_conflict_query(db):
    """V10-QUERY-CMP-004：conflict query——type/severity/status 过滤。"""
    _seed_all(db)
    q = ScaleQueryRuntime(db[0])
    r = q.list_conflicts(conflict_type="ASSERTION_VALUE_CONFLICT")
    assert r["count"] == 1
    assert r["items"][0]["severity"] in ("medium", "high")
    assert q.list_conflicts(status="open")["count"] == r["count"]
    assert q.list_conflicts(status="dismissed")["count"] == 0


def test_v10_query_cmp_005_cursor_pagination_correctness(db):
    """V10-QUERY-CMP-005：cursor pagination——limit=2 两页遍历无重无漏 + 零
    offset。"""
    _seed_all(db)
    q = ScaleQueryRuntime(db[0])
    page1 = q.list_causal_edges(limit=2)
    assert page1["has_more"] and page1["next_cursor"]
    page2 = q.list_causal_edges(limit=2, cursor=page1["next_cursor"])
    ids1 = [x["causal_edge_id"] for x in page1["items"]]
    ids2 = [x["causal_edge_id"] for x in page2["items"]]
    assert not set(ids1) & set(ids2)
    assert len(set(ids1) | set(ids2)) == 3


def test_v10_query_cmp_006_cursor_replay_determinism(db):
    """V10-QUERY-CMP-006：cursor replay determinism——同 cursor 重放一致。"""
    _seed_all(db)
    q = ScaleQueryRuntime(db[0])
    p1a = q.list_causal_edges(limit=2)
    p1b = q.list_causal_edges(limit=2)
    assert p1a["next_cursor"] == p1b["next_cursor"]
    p2a = q.list_causal_edges(limit=2, cursor=p1a["next_cursor"])
    p2b = q.list_causal_edges(limit=2, cursor=p1b["next_cursor"])
    assert [x["causal_edge_id"] for x in p2a["items"]] == \
        [x["causal_edge_id"] for x in p2b["items"]]


def test_v10_query_cmp_007_invalid_cursor_fail_close(db):
    """V10-QUERY-CMP-007：invalid cursor fail-close——篡改指纹/跨 query 复用/
    垃圾串全拒。"""
    _seed_all(db)
    q = ScaleQueryRuntime(db[0])
    p1 = q.list_causal_edges(limit=2)
    cur = p1["next_cursor"]
    fp, body = cur.split(".", 1)
    # 篡改 body（指纹失配）
    with pytest.raises(QueryError, match="E-V10-QUERY-CURSOR-INVALID"):
        q.list_causal_edges(limit=2, cursor="deadbeef." + body)
    # 跨 query 复用（causal cursor 用于 conflict）
    with pytest.raises(QueryError, match="E-V10-QUERY-CURSOR-INVALID"):
        q.list_conflicts(cursor=cur)
    # 垃圾串
    for bad in ("", "no-dot", "x.not-json{"):
        with pytest.raises(QueryError, match="E-V10-QUERY-CURSOR-INVALID"):
            q.list_causal_edges(cursor=bad)


def test_v10_query_cmp_008_limit_boundary(db):
    """V10-QUERY-CMP-008：limit boundary——0/负数/超帽 500 全拒；limit=500 合法。"""
    _seed_all(db)
    q = ScaleQueryRuntime(db[0])
    for bad in (0, -1, 501, "10", None):
        with pytest.raises(QueryError, match="E-V10-QUERY-PAGE-INVALID"):
            q.list_causal_edges(limit=bad)
    assert q.list_causal_edges(limit=500)["count"] == 3


def test_v10_query_cmp_009_deterministic_ordering(db):
    """V10-QUERY-CMP-009：deterministic ordering——causal/conflict PK ASC、
    health (fingerprint, signal_id) ASC；多次查询全等。"""
    _seed_all(db)
    q = ScaleQueryRuntime(db[0])
    ids1 = [x["causal_edge_id"] for x in q.list_causal_edges()["items"]]
    ids2 = [x["causal_edge_id"] for x in q.list_causal_edges()["items"]]
    assert ids1 == ids2 == sorted(ids1)
    sig_rows = q.list_health_signals()["items"]
    keys = [(x["fingerprint"], x["signal_id"]) for x in sig_rows]
    assert keys == sorted(keys)   # (fingerprint, signal_id) 联合键序
    cids = [x["conflict_id"] for x in q.list_conflicts()["items"]]
    assert cids == sorted(cids)


def test_v10_query_cmp_010_empty_result_behavior(db):
    """V10-QUERY-CMP-010：empty result behavior——count=0+has_more=False+
    cursor=None（不 fabricate）。"""
    _seed_all(db)
    q = ScaleQueryRuntime(db[0])
    r = q.list_causal_edges(cause_ref="Ghost")
    assert r["count"] == 0 and not r["has_more"] and r["next_cursor"] is None


def test_v10_query_cmp_011_read_only_isolation(db):
    """V10-QUERY-CMP-011：read-only isolation——三查询全流程 akb_assertions/
    kg_nodes/kg_edges/akb_provenance unchanged（快照实测）。"""
    _seed_all(db)
    con = db[0]
    snap = {t: [tuple(r) for r in con.execute(f"SELECT * FROM {t} ORDER BY 1")]
            for t in ("akb_assertions", "kg_nodes", "kg_edges",
                      "akb_provenance")}
    q = ScaleQueryRuntime(con)
    q.list_causal_edges(limit=2)
    q.list_causal_edges(limit=2, cursor=q.list_causal_edges(limit=1)["next_cursor"])
    q.list_health_signals()
    q.list_conflicts()
    for t, rows in snap.items():
        assert [tuple(r) for r in con.execute(
            f"SELECT * FROM {t} ORDER BY 1")] == rows, t


def test_v10_query_cmp_012_frozen_regression(db):
    """V10-QUERY-CMP-012：frozen regression——migration chain 17 + 十二 frozen
    模块零感知 + 建图回归。"""
    vers = [m.version for m in ALL_MIGRATIONS]
    assert vers == list(range(1, 18))
    m17 = [m for m in ALL_MIGRATIONS if m.version == 17][0]
    assert m17.name == "v10_query_indexes"
    # migration 16 零修改（statement 集合不变——append-only 验证）
    m16 = [m for m in ALL_MIGRATIONS if m.version == 16][0]
    assert len(m16.statements) == 11   # 三表 CREATE + 3+3+2 索引（零修改锚）
    import inspect
    import agent_kb.graph as legacy
    import agent_kb.kgraph.orchestrator as m1
    import agent_kb.domains.runtime as m2
    import agent_kb.rules.runtime as m3
    import agent_kb.policy.runtime as m4
    import agent_kb.domains.guard as m5
    import agent_kb.hypothesis.runtime as m6
    import agent_kb.hypothesis.verdict as m7
    import agent_kb.causal.projection as m8
    import agent_kb.health.runtime as m9
    import agent_kb.conflict.runtime as m10
    import agent_kb.causal.persistence as m11
    for mod in (m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11):
        assert "ScaleQueryRuntime" not in inspect.getsource(mod)
    for sym in ("ScaleQueryRuntime", "QueryCursor"):
        assert not hasattr(legacy, sym)
    # 建图回归
    from agent_kb.kgraph import (
        GraphPersistenceService, GraphProjectionService, GraphQueryService)
    con = db[0]
    GraphPersistenceService(con).persist(GraphProjectionService().process(con))
    qv = GraphQueryService(con)
    v1 = qv.canonical_view()
    _seed_all(db)
    ScaleQueryRuntime(con).list_causal_edges()
    assert qv.canonical_view() == v1