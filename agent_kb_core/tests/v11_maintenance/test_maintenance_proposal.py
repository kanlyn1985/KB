# -*- coding: utf-8 -*-
"""V11-MAINT-CMP-001..012（AKB-V11-IMPL-001：Maintenance Proposal Runtime）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.causal import CausalProjectionRuntime
from agent_kb.conflict import ConflictRuntime
from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.health import KnowledgeHealthRuntime
from agent_kb.hypothesis import (
    HypothesisService,
    VerificationTaskRuntime,
)
from agent_kb.maintenance import (
    MaintenanceProposalError,
    MaintenanceProposalRuntime,
)
from agent_kb.storage.migrations import SchemaMigrator


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(
        ":memory:", isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    SchemaMigrator(con).migrate()
    con.execute("INSERT INTO akb_sources (source_id, source_type, name)"
                " VALUES ('m11', 'document', 'M11')")
    con.execute("INSERT INTO akb_documents (document_id, source_id, version,"
                " content_hash, ingested_at) VALUES ('dm11', 'm11', '1.0',"
                " 'h', strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    ev = EvidenceStore(con).create(document_id="dm11", content="维护锚证据。",
                                   extraction_method="t")
    yield con, ev.evidence_id
    con.close()


import sqlite3


def _seed_signal(db):
    con, eid = db
    hs = HypothesisService(con)
    hyp = hs.create_hypothesis(statement="H: M11 信号锚", domain_ref=
                               "industrial", pack_ref="dpr_a",
                               policy_ref="pol_b", context_ref="grc_c",
                               origin="human")
    kh = KnowledgeHealthRuntime(con, causal_runtime=CausalProjectionRuntime(con))
    h = kh.create_health(target_ref=hyp.hypothesis_id,
                         target_type="hypothesis")
    # 提案消费的是 V0.10 持久面——先落库（设计 ARCHITECTURE §2 数据流）
    from agent_kb.causal import ScalePersistenceRuntime
    ScalePersistenceRuntime(con).persist_health_signals(h)
    return hyp, h


def _seed_conflict(db):
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
    ScalePersist = pytest.importorskip("agent_kb.causal")
    from agent_kb.causal import ScalePersistenceRuntime
    ScalePersistenceRuntime(con).persist_conflict_records(records)
    return records


def test_v11_maint_cmp_001_create_from_signal(db):
    """V11-MAINT-CMP-001：create proposal from health signal——全字段。"""
    hyp, h = _seed_signal(db)
    rt = MaintenanceProposalRuntime(db[0])
    p = rt.create_proposal_from_signal(h.health_id,
                                       actor_id="human:ops")
    assert p.proposal_id.startswith("vt_")     # V0.8 task 通道 identity
    assert p.source_type == "health_signal"
    assert p.source_id.startswith(h.health_id)   # 信号行粒度（诚实语义）
    assert p.proposal_type == "maintenance_review"
    assert p.status == "created"
    assert "Please review" in p.spec
    assert p.priority in ("low", "medium", "high")


def test_v11_maint_cmp_002_create_from_conflict(db):
    """V11-MAINT-CMP-002：create proposal from conflict——conflict status 零
    变更（Conflict ≠ Resolution）+ entity 锚 fail-close（P1 默认档）+
    hypothesis 型 conflict target 正路。"""
    records = _seed_conflict(db)
    con = db[0]
    rt = MaintenanceProposalRuntime(con)
    # entity 型 target（Temp）→ fail-close（零 fabricate 锚）
    with pytest.raises(MaintenanceProposalError,
                       match="E-V11-MAINTENANCE-INVALID"):
        rt.create_proposal_from_conflict(records[0].conflict_id)
    # hypothesis 型 target（实存 hypothesis）→ 正路提案
    hs = HypothesisService(con)
    hyp = hs.create_hypothesis(statement="H: conflict target", domain_ref=
                               "industrial", pack_ref="dpr_a",
                               policy_ref="pol_b", context_ref="grc_c",
                               origin="human")
    # 构造 target=hyp 的冲突行（持久面直接落——同 V0.10 persist 语义）
    con.execute(
        "INSERT INTO akb_conflict_records (conflict_id, conflict_type,"
        " source_refs_json, target_refs_json, severity, status,"
        " evidence_refs_json, fingerprint, created_from_snapshot,"
        " provenance_ref) VALUES (?, 'ASSERTION_VALUE_CONFLICT', '[]', ?,"
        " 'medium', 'open', '[]', 'fpx', 'snap_x', 'prov_x')",
        ("cf_test_hyp", json.dumps([hyp.hypothesis_id])))
    p = rt.create_proposal_from_conflict("cf_test_hyp", actor_id="human:ops")
    assert p.source_type == "conflict_record"
    assert p.proposal_type == "maintenance_review"   # 零 resolution/truth_choice
    assert "Please review" in p.spec and "confirmed" not in p.spec
    # conflict status 零变更（Conflict ≠ Resolution）
    row = con.execute("SELECT status FROM akb_conflict_records WHERE"
                      " conflict_id='cf_test_hyp'").fetchone()
    assert row["status"] == "open"


def test_v11_maint_cmp_003_deterministic_proposal_id(db):
    """V11-MAINT-CMP-003：deterministic proposal_id——同信号跨实例全等；不同
    信号不同 id。"""
    hyp, h = _seed_signal(db)
    p1 = MaintenanceProposalRuntime(db[0]).create_proposal_from_signal(
        h.health_id)
    p2 = MaintenanceProposalRuntime(db[0]).create_proposal_from_signal(
        h.health_id)
    assert p1.proposal_id == p2.proposal_id
    # 不同信号（不同 hypothesis）→ 不同提案
    hs = HypothesisService(db[0])
    hyp2 = hs.create_hypothesis(statement="H: M11 信号锚 2", domain_ref=
                                "industrial", pack_ref="dpr_a",
                                policy_ref="pol_b", context_ref="grc_c",
                                origin="human")
    kh = KnowledgeHealthRuntime(db[0], causal_runtime=CausalProjectionRuntime(
        db[0]))
    h2 = kh.create_health(target_ref=hyp2.hypothesis_id,
                          target_type="hypothesis")
    from agent_kb.causal import ScalePersistenceRuntime
    ScalePersistenceRuntime(db[0]).persist_health_signals(h2)
    p3 = MaintenanceProposalRuntime(db[0]).create_proposal_from_signal(
        h2.health_id)
    assert p3.proposal_id != p1.proposal_id


def test_v11_maint_cmp_004_fingerprint_stability(db):
    """V11-MAINT-CMP-004：fingerprint stability——同输入同 fingerprint。"""
    hyp, h = _seed_signal(db)
    p1 = MaintenanceProposalRuntime(db[0]).create_proposal_from_signal(
        h.health_id)
    p2 = MaintenanceProposalRuntime(db[0]).create_proposal_from_signal(
        h.health_id)
    assert p1.fingerprint == p2.fingerprint
    assert len(p1.fingerprint) == 16


def test_v11_maint_cmp_005_immutable_proposal(db):
    """V11-MAINT-CMP-005：immutable proposal——frozen dataclass 赋值拒绝。"""
    hyp, h = _seed_signal(db)
    p = MaintenanceProposalRuntime(db[0]).create_proposal_from_signal(
        h.health_id)
    with pytest.raises(Exception):
        p.status = "completed"  # type: ignore[misc]


def test_v11_maint_cmp_006_proposal_to_task(db):
    """V11-MAINT-CMP-006：proposal -> VerificationTask——task 实存 + task_type
    白名单 + 生命周期零自动迁移。"""
    hyp, h = _seed_signal(db)
    rt = MaintenanceProposalRuntime(db[0])
    p = rt.create_proposal_from_signal(h.health_id)
    tr = VerificationTaskRuntime(db[0])
    t = tr.get_task(p.proposal_id)
    assert t is not None and t.task_type == "maintenance_review"
    assert t.status == "created"               # 零自动迁移（human-only）
    # 枚举扩展后原 task_type 行为不变（V0.8 原有类型仍可用）
    t2 = tr.create_task(hypothesis_id=hyp.hypothesis_id,
                        task_type="evidence_review", spec="legacy path",
                        evidence_requirements=(db[1],))
    assert t2.task_type == "evidence_review"


def test_v11_maint_cmp_007_no_assertion_mutation(db):
    """V11-MAINT-CMP-007：no assertion mutation——提案全流程 akb_assertions
    unchanged。"""
    records = _seed_conflict(db)
    con = db[0]
    snap = [tuple(r) for r in con.execute(
        "SELECT * FROM akb_assertions ORDER BY 1")]
    rt = MaintenanceProposalRuntime(con)
    # conflict 提案：entity 锚 fail-close（零 fabricate——P1 默认档）
    with pytest.raises(MaintenanceProposalError,
                       match="E-V11-MAINTENANCE-INVALID"):
        rt.create_proposal_from_conflict(records[0].conflict_id)
    hyp, h = _seed_signal(db)
    rt.create_proposal_from_signal(h.health_id)
    assert [tuple(r) for r in con.execute(
        "SELECT * FROM akb_assertions ORDER BY 1")] == snap


def test_v11_maint_cmp_008_no_graph_mutation(db):
    """V11-MAINT-CMP-008：no graph mutation——kg_nodes/kg_edges unchanged +
    hypothesis 状态零变化。"""
    con = db[0]
    hyp, h = _seed_signal(db)
    records = _seed_conflict(db)
    n_n = con.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"]
    n_e = con.execute("SELECT COUNT(*) c FROM kg_edges").fetchone()["c"]
    h_status_before = HypothesisService(con).get_hypothesis(
        hyp.hypothesis_id).status
    rt = MaintenanceProposalRuntime(con)
    with pytest.raises(MaintenanceProposalError,
                       match="E-V11-MAINTENANCE-INVALID"):
        rt.create_proposal_from_conflict(records[0].conflict_id)
    rt.create_proposal_from_signal(h.health_id)
    assert con.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"] == n_n
    assert con.execute("SELECT COUNT(*) c FROM kg_edges").fetchone()["c"] == n_e
    assert HypothesisService(con).get_hypothesis(
        hyp.hypothesis_id).status == h_status_before


def test_v11_maint_cmp_009_provenance_audit(db):
    """V11-MAINT-CMP-009：provenance audit——graph:maintenance-proposal-create
    落 akb_provenance（proposal_id/source/target/spec/priority）。"""
    hyp, h = _seed_signal(db)
    p = MaintenanceProposalRuntime(db[0]).create_proposal_from_signal(
        h.health_id)
    rows = [dict(x) for x in db[0].execute(
        "SELECT * FROM akb_provenance WHERE activity ="
        " 'graph:maintenance-proposal-create'")]
    assert len(rows) == 1
    m = json.loads(rows[0]["metadata_json"])
    assert m["proposal_id"] == p.proposal_id
    assert m["source_id"].startswith(h.health_id)   # 信号行粒度
    assert m["spec"] == p.spec and m["priority"] == p.priority


def test_v11_maint_cmp_010_invalid_source_fail_close(db):
    """V11-MAINT-CMP-010：invalid source fail-close——不存在 signal/conflict/
    未知 source_type/非法 limit/坏 cursor 全拒（E-V11-MAINTENANCE-INVALID）。"""
    con = db[0]
    rt = MaintenanceProposalRuntime(con)
    with pytest.raises(MaintenanceProposalError,
                       match="E-V11-MAINTENANCE-INVALID"):
        rt.create_proposal_from_signal("khs_ghost")
    with pytest.raises(MaintenanceProposalError,
                       match="E-V11-MAINTENANCE-INVALID"):
        rt.create_proposal_from_conflict("cf_ghost")
    with pytest.raises(MaintenanceProposalError,
                       match="E-V11-MAINTENANCE-INVALID"):
        rt.list_proposals(source_type="teleport")
    with pytest.raises(MaintenanceProposalError,
                       match="E-V11-MAINTENANCE-INVALID"):
        rt.list_proposals(limit=501)
    with pytest.raises(MaintenanceProposalError,
                       match="E-V11-MAINTENANCE-INVALID"):
        rt.list_proposals(cursor="garbage-no-dot")
    with pytest.raises(MaintenanceProposalError,
                       match="E-V11-MAINTENANCE-INVALID"):
        rt.get_proposal("bad-id")


def test_v11_maint_cmp_011_cursor_query_deterministic(db):
    """V11-MAINT-CMP-011：cursor query deterministic——分页无重无漏 + 重放一致 +
    conflict proposal 锚 fail-close（P1 默认档诚实边界）。"""
    con = db[0]
    rt = MaintenanceProposalRuntime(con)
    # conflict proposal：entity 型 target 无 hypothesis 锚 → fail-close
    records = _seed_conflict(db)
    with pytest.raises(MaintenanceProposalError,
                       match="E-V11-MAINTENANCE-INVALID"):
        rt.create_proposal_from_conflict(records[0].conflict_id)
    # hypothesis 型信号 ×3 → 分页验证
    hs = HypothesisService(con)
    kh = KnowledgeHealthRuntime(con, causal_runtime=CausalProjectionRuntime(con))
    from agent_kb.causal import ScalePersistenceRuntime
    ids = []
    for stmt in ("H: q1", "H: q2", "H: q3"):
        hyp = hs.create_hypothesis(statement=stmt, domain_ref="industrial",
                                   pack_ref="dpr_a", policy_ref="pol_b",
                                   context_ref="grc_c", origin="human")
        h = kh.create_health(target_ref=hyp.hypothesis_id,
                             target_type="hypothesis")
        ScalePersistenceRuntime(con).persist_health_signals(h)
        p = rt.create_proposal_from_signal(h.health_id)
        ids.append(p.proposal_id)
    q = rt.list_proposals(limit=2)
    assert q["has_more"] and q["next_cursor"]
    q2 = rt.list_proposals(limit=2, cursor=q["next_cursor"])
    ids1 = {i["proposal_id"] for i in q["items"]}
    ids2 = {i["proposal_id"] for i in q2["items"]}
    assert not ids1 & ids2 and len(ids1 | ids2) == 3
    # 重放一致
    q1b = rt.list_proposals(limit=2)
    assert q1b["next_cursor"] == q["next_cursor"]
    # source_type 过滤
    assert rt.list_proposals(source_type="health_signal")["count"] == 3


def test_v11_maint_cmp_012_frozen_regression(db):
    """V11-MAINT-CMP-012：frozen regression——frozen 模块零 MaintenanceProposal
    感知（枚举扩展除外）+ legacy 互斥 + 建图回归。"""
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
    import agent_kb.storage.query as m11
    for mod in (m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11):
        assert "MaintenanceProposal" not in inspect.getsource(mod)
    # verification.py 枚举扩展是唯一授权变更（验证生命周期零变化：类方法集不变）
    import agent_kb.hypothesis.verification as m12
    assert "maintenance_review" in inspect.getsource(m12)
    for sym in ("MaintenanceProposalRuntime", "MaintenanceProposal"):
        assert not hasattr(legacy, sym)
    # 建图回归
    from agent_kb.kgraph import (
        GraphPersistenceService, GraphProjectionService, GraphQueryService)
    con = db[0]
    GraphPersistenceService(con).persist(GraphProjectionService().process(con))
    qv = GraphQueryService(con)
    v1 = qv.canonical_view()
    hyp, h = _seed_signal(db)
    MaintenanceProposalRuntime(con).create_proposal_from_signal(h.health_id)
    assert qv.canonical_view() == v1