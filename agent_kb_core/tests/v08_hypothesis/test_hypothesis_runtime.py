# -*- coding: utf-8 -*-
"""HY-CMP-001..010（AKB-V08-IMPL-001：Hypothesis Runtime acceptance）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.hypothesis import (
    HypothesisError,
    HypothesisService,
    hypothesis_identity,
)


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con).migrate()
    yield con
    con.close()


def _kw(**over):
    base = dict(statement="H: OBC 在高湿环境下绝缘裕度下降 30%",
                domain_ref="industrial", pack_ref="dpr_abc123",
                policy_ref="pol_def456", context_ref="grc_789abc",
                origin="reasoning")
    base.update(over)
    return base


def test_hy_cmp_001_create_hypothesis(db):
    """HY-CMP-001：create hypothesis——全字段 + status=open。"""
    svc = HypothesisService(db)
    h = svc.create_hypothesis(**_kw())
    assert h.hypothesis_id.startswith("hyp_")
    assert h.status == "open"
    assert h.statement == _kw()["statement"]
    assert h.domain_ref == "industrial" and h.pack_ref == "dpr_abc123"
    assert h.policy_ref == "pol_def456" and h.context_ref == "grc_789abc"
    assert h.origin == "reasoning"


def test_hy_cmp_002_deterministic_id(db):
    """HY-CMP-002：deterministic id——同五元组跨实例/双 service 全等。"""
    svc1 = HypothesisService(db)
    h1 = svc1.create_hypothesis(**_kw())
    h2 = HypothesisService(db).create_hypothesis(**_kw())
    assert h1.hypothesis_id == h2.hypothesis_id
    assert h1.hypothesis_id == hypothesis_identity(**{
        k: _kw()[k] for k in ("statement", "domain_ref", "pack_ref",
                              "policy_ref", "context_ref")})
    # 输入变化 → id 变
    h3 = svc1.create_hypothesis(**_kw(statement="H: 另一猜想"))
    assert h3.hypothesis_id != h1.hypothesis_id


def test_hy_cmp_003_duplicate_create_idempotent(db):
    """HY-CMP-003：duplicate create idempotent——重复创建同 hypothesis + 零重复审计。"""
    svc = HypothesisService(db)
    h1 = svc.create_hypothesis(**_kw())
    n1 = db.execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                    " activity='graph:hypothesis-create'").fetchone()["c"]
    h2 = svc.create_hypothesis(**_kw())
    n2 = db.execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                    " activity='graph:hypothesis-create'").fetchone()["c"]
    assert h1.hypothesis_id == h2.hypothesis_id and n1 == n2 == 1


def test_hy_cmp_004_lifecycle_transition(db):
    """HY-CMP-004：lifecycle transition——open→supported/refuted/withdrawn 全合法。"""
    svc = HypothesisService(db)
    h = svc.create_hypothesis(**_kw(statement="H1"))
    h2 = svc.transition_status(h.hypothesis_id, new_status="supported",
                               actor_id="human:reviewer")
    assert h2.status == "supported"
    h3 = svc.create_hypothesis(**_kw(statement="H2"))
    assert svc.transition_status(h3.hypothesis_id, new_status="refuted",
                                 actor_id="human:reviewer").status == "refuted"
    h4 = svc.create_hypothesis(**_kw(statement="H3"))
    assert svc.withdraw_hypothesis(h4.hypothesis_id,
                                   actor_id="human:reviewer").status == "withdrawn"


def test_hy_cmp_005_invalid_transition_fail_close(db):
    """HY-CMP-005：invalid transition fail-close——closed 无出边 + 断言域状态禁入。"""
    svc = HypothesisService(db)
    h = svc.create_hypothesis(**_kw(statement="H4"))
    svc.transition_status(h.hypothesis_id, new_status="supported",
                          actor_id="human:reviewer")
    # supported → 任何迁移拒绝（closed 无出边）
    for bad in ("asserted", "validated", "inferred", "open", "refuted"):
        with pytest.raises(HypothesisError, match="E-V08-INVALID-TRANSITION"):
            svc.transition_status(h.hypothesis_id, new_status=bad,
                                  actor_id="human:reviewer")
    # 断言域状态直接拒绝（即使 open）
    h2 = svc.create_hypothesis(**_kw(statement="H5"))
    for bad in ("asserted", "validated", "inferred"):
        with pytest.raises(HypothesisError, match="E-V08-INVALID-TRANSITION"):
            svc.transition_status(h2.hypothesis_id, new_status=bad,
                                  actor_id="human:reviewer")
    # withdraw 后再 withdraw 拒绝
    h3 = svc.create_hypothesis(**_kw(statement="H6"))
    svc.withdraw_hypothesis(h3.hypothesis_id, actor_id="human:reviewer")
    with pytest.raises(HypothesisError, match="E-V08-INVALID-TRANSITION"):
        svc.withdraw_hypothesis(h3.hypothesis_id, actor_id="human:reviewer")


def test_hy_cmp_006_provenance_audit(db):
    """HY-CMP-006：provenance audit——create/withdraw 记录全字段（id/actor/domain/
    context/pack/policy）。"""
    svc = HypothesisService(db)
    h = svc.create_hypothesis(**_kw())
    rows = [dict(x) for x in db.execute(
        "SELECT * FROM akb_provenance WHERE activity='graph:hypothesis-create'")]
    assert len(rows) == 1
    m = json.loads(rows[0]["metadata_json"])
    assert m["hypothesis_id"] == h.hypothesis_id
    assert m["domain_ref"] == "industrial" and m["pack_ref"] == "dpr_abc123"
    assert m["policy_ref"] == "pol_def456" and m["context_ref"] == "grc_789abc"
    assert "actor" in m
    svc.withdraw_hypothesis(h.hypothesis_id, actor_id="human:reviewer")
    rows_w = [dict(x) for x in db.execute(
        "SELECT * FROM akb_provenance WHERE activity='graph:hypothesis-withdraw'")]
    assert len(rows_w) == 1
    mw = json.loads(rows_w[0]["metadata_json"])
    assert mw["from_status"] == "open" and mw["to_status"] == "withdrawn"


def test_hy_cmp_007_no_assertion_leakage(db):
    """HY-CMP-007：no assertion leakage——hypothesis 全生命周期零 akb_assertions
    写入。"""
    n_before = db.execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
    svc = HypothesisService(db)
    h = svc.create_hypothesis(**_kw())
    svc.transition_status(h.hypothesis_id, new_status="supported",
                          actor_id="human:reviewer")
    svc.withdraw_hypothesis(svc.create_hypothesis(**_kw(statement="H7")).hypothesis_id,
                            actor_id="human:reviewer")
    n_after = db.execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
    assert n_before == n_after
    # akb_assertions 中零 hypothesis 痕迹
    n = db.execute("SELECT COUNT(*) c FROM akb_assertions WHERE canonical_json"
                   " LIKE '%hyp_%' OR canonical_json LIKE '%H:%'").fetchone()["c"]
    assert n == 0


def test_hy_cmp_008_no_graph_leakage(db):
    """HY-CMP-008：no graph leakage——hypothesis 全生命周期零 kg_* 写入。"""
    n_nodes = db.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"]
    n_edges = db.execute("SELECT COUNT(*) c FROM kg_edges").fetchone()["c"]
    svc = HypothesisService(db)
    h = svc.create_hypothesis(**_kw())
    svc.transition_status(h.hypothesis_id, new_status="supported",
                          actor_id="human:reviewer")
    assert db.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"] == n_nodes
    assert db.execute("SELECT COUNT(*) c FROM kg_edges").fetchone()["c"] == n_edges


def test_hy_cmp_009_withdraw(db):
    """HY-CMP-009：withdraw——open→withdrawn + 状态重建正确 + closed 拒绝再变。"""
    svc = HypothesisService(db)
    h = svc.create_hypothesis(**_kw(statement="H8"))
    w = svc.withdraw_hypothesis(h.hypothesis_id, actor_id="human:reviewer")
    assert w.status == "withdrawn"
    # 重建（新 service 实例）状态一致（provenance 重放确定性）
    w2 = HypothesisService(db).get_hypothesis(h.hypothesis_id)
    assert w2.status == "withdrawn"
    # get 不存在 → None（不 fabricate）
    assert HypothesisService(db).get_hypothesis("hyp_nonexistent") is None


def test_hy_cmp_010_frozen_regression(db):
    """HY-CMP-010：frozen regression——V0.5/V0.6/V0.7 零感知（单向依赖）+
    legacy 零引用 + 建图回归。"""
    import inspect
    import agent_kb.graph as legacy
    import agent_kb.kgraph.orchestrator as orch_mod
    import agent_kb.kgraph.context as ctx_mod
    import agent_kb.domains.runtime as dom_mod
    import agent_kb.rules.runtime as rules_mod
    import agent_kb.policy.runtime as pol_mod
    import agent_kb.domains.guard as guard_mod
    for mod in (orch_mod, ctx_mod, dom_mod, rules_mod, pol_mod, guard_mod):
        assert "HypothesisService" not in inspect.getsource(mod) \
            and "hypothesis" not in inspect.getsource(mod).lower().replace(
                "graph:hypothesis", "")
    for sym in ("HypothesisService", "Hypothesis"):
        assert not hasattr(legacy, sym)
    # 建图回归：hypothesis 活动后投影/查询面不变
    from agent_kb.kgraph import (
        GraphPersistenceService, GraphProjectionService, GraphQueryService)
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('hy', 'document', 'HY')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version,"
               " content_hash, ingested_at) VALUES ('dhy', 'hy', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    eid = EvidenceStore(db).create(document_id="dhy", content="锚定证据。",
                                   extraction_method="t").evidence_id
    GraphPersistenceService(db).persist(GraphProjectionService().process(db))
    q = GraphQueryService(db)
    v1 = q.canonical_view()
    svc = HypothesisService(db)
    h = svc.create_hypothesis(**_kw(statement="H9"))
    svc.transition_status(h.hypothesis_id, new_status="refuted",
                          actor_id="human:reviewer")
    assert q.canonical_view() == v1