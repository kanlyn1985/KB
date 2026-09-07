# -*- coding: utf-8 -*-
"""VT-CMP-001..010（AKB-V08-IMPL-002：VerificationTask Runtime acceptance）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.hypothesis import (
    HypothesisService,
    VerificationTaskError,
    VerificationTaskRuntime,
    verification_task_identity,
)


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con).migrate()
    yield con
    con.close()


@pytest.fixture
def svc(db):
    return HypothesisService(db)


@pytest.fixture
def rt(db, svc):
    return VerificationTaskRuntime(db, hypothesis_service=svc)


@pytest.fixture
def hyp(svc):
    return svc.create_hypothesis(
        statement="H: VT 锚定猜想", domain_ref="industrial",
        pack_ref="dpr_a", policy_ref="pol_b", context_ref="grc_c",
        origin="human")


def _kw(hyp_id, **over):
    base = dict(hypothesis_id=hyp_id, task_type="evidence_review",
                spec="复核 OBC 高湿绝缘裕度证据链",
                evidence_requirements=("evd_a", "evd_b"))
    base.update(over)
    return base


def test_vt_cmp_001_task_create(db, rt, svc, hyp):
    """VT-CMP-001：task create——全字段 + status=created。"""
    t = rt.create_task(**_kw(hyp.hypothesis_id))
    assert t.task_id.startswith("vt_")
    assert t.status == "created"
    assert t.hypothesis_id == hyp.hypothesis_id
    assert t.task_type == "evidence_review"
    assert t.evidence_requirements == ("evd_a", "evd_b")
    assert t.created_by


def test_vt_cmp_002_deterministic_id(db, rt, svc, hyp):
    """VT-CMP-002：deterministic id——同输入跨实例全等；输入变化 → id 变。"""
    t1 = rt.create_task(**_kw(hyp.hypothesis_id))
    t2 = VerificationTaskRuntime(db, hypothesis_service=svc).create_task(
        **_kw(hyp.hypothesis_id))
    assert t1.task_id == t2.task_id
    assert t1.task_id == verification_task_identity(
        hypothesis_id=hyp.hypothesis_id, task_type="evidence_review",
        spec="复核 OBC 高湿绝缘裕度证据链",
        evidence_requirements=("evd_a", "evd_b"))
    t3 = rt.create_task(**_kw(hyp.hypothesis_id, spec="另一验证规格"))
    assert t3.task_id != t1.task_id


def test_vt_cmp_003_duplicate_create_idempotent(db, rt, hyp):
    """VT-CMP-003：duplicate create idempotent——重复创建同 task + 零重复审计。"""
    rt.create_task(**_kw(hyp.hypothesis_id))
    n1 = db.execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                    " activity='graph:verification-task-create'").fetchone()["c"]
    rt.create_task(**_kw(hyp.hypothesis_id))
    n2 = db.execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                    " activity='graph:verification-task-create'").fetchone()["c"]
    assert n1 == n2 == 1


def test_vt_cmp_004_lifecycle_transition(db, rt, hyp):
    """VT-CMP-004：lifecycle——created→running→completed / →failed / →cancelled。"""
    t = rt.create_task(**_kw(hyp.hypothesis_id))
    assert rt.start_task(t.task_id, actor_id="human:reviewer").status == "running"
    assert rt.complete_task(t.task_id, actor_id="human:reviewer").status == "completed"
    t2 = rt.create_task(**_kw(hyp.hypothesis_id, spec="失败路径规格"))
    assert rt.start_task(t2.task_id, actor_id="human:reviewer").status == "running"
    assert rt.fail_task(t2.task_id, actor_id="human:reviewer").status == "failed"
    t3 = rt.create_task(**_kw(hyp.hypothesis_id, spec="取消路径规格"))
    assert rt.start_task(t3.task_id, actor_id="human:reviewer").status == "running"
    assert rt.cancel_task(t3.task_id, actor_id="human:reviewer").status == "cancelled"
    t4 = rt.create_task(**_kw(hyp.hypothesis_id, spec="created 直接取消"))
    assert rt.cancel_task(t4.task_id, actor_id="human:reviewer").status == "cancelled"


def test_vt_cmp_005_invalid_transition_fail_close(db, rt, hyp):
    """VT-CMP-005：invalid transition fail-close——completed→running、failed→
    completed、cancelled→任意 全拒绝（E-V08-TASK-INVALID-TRANSITION）。"""
    t = rt.create_task(**_kw(hyp.hypothesis_id))
    rt.start_task(t.task_id, actor_id="human:reviewer")
    rt.complete_task(t.task_id, actor_id="human:reviewer")
    for bad in ("running", "failed", "cancelled"):
        with pytest.raises(VerificationTaskError,
                           match="E-V08-TASK-INVALID-TRANSITION"):
            if bad == "running":
                rt.start_task(t.task_id, actor_id="human:reviewer")
            elif bad == "failed":
                rt.fail_task(t.task_id, actor_id="human:reviewer")
            else:
                rt.cancel_task(t.task_id, actor_id="human:reviewer")
    t2 = rt.create_task(**_kw(hyp.hypothesis_id, spec="failed 补测试"))
    rt.start_task(t2.task_id, actor_id="human:reviewer")
    rt.fail_task(t2.task_id, actor_id="human:reviewer")
    with pytest.raises(VerificationTaskError,
                       match="E-V08-TASK-INVALID-TRANSITION"):
        rt.complete_task(t2.task_id, actor_id="human:reviewer")
    t3 = rt.create_task(**_kw(hyp.hypothesis_id, spec="cancelled 补测试"))
    rt.cancel_task(t3.task_id, actor_id="human:reviewer")
    for op in ("start", "complete", "fail", "cancel"):
        with pytest.raises(VerificationTaskError,
                           match="E-V08-TASK-INVALID-TRANSITION"):
            getattr(rt, f"{op}_task")(t3.task_id, actor_id="human:reviewer")


def test_vt_cmp_006_hypothesis_binding_validation(db, rt):
    """VT-CMP-006：hypothesis binding validation——不存在 hypothesis 拒绝
    （E-V08-HYPOTHESIS-NOT-FOUND）；非法 task_type/spec/requirements 拒绝。"""
    with pytest.raises(VerificationTaskError, match="E-V08-HYPOTHESIS-NOT-FOUND"):
        rt.create_task(**_kw("hyp_ghost"))
    with pytest.raises(VerificationTaskError, match="E-V08-TASK-INVALID"):
        rt.create_task(**_kw("hyp_ghost", task_type="teleport"))
    with pytest.raises(VerificationTaskError, match="E-V08-TASK-INVALID"):
        rt.create_task(**_kw("hyp_ghost", spec=" "))
    with pytest.raises(VerificationTaskError, match="E-V08-TASK-INVALID"):
        rt.create_task(**_kw("hyp_ghost", evidence_requirements=()))


def test_vt_cmp_007_provenance_audit(db, rt, hyp):
    """VT-CMP-007：provenance audit——五个活动全进 akb_provenance（task_id/
    hypothesis_id/transition/requirements/actor）。"""
    t = rt.create_task(**_kw(hyp.hypothesis_id))
    rt.start_task(t.task_id, actor_id="human:reviewer")
    rt.complete_task(t.task_id, actor_id="human:reviewer")
    rows = [dict(x) for x in db.execute(
        "SELECT * FROM akb_provenance WHERE activity LIKE"
        " 'graph:verification-task-%' ORDER BY occurred_at")]
    acts = {r["activity"] for r in rows}
    assert acts == {"graph:verification-task-create",
                    "graph:verification-task-start",
                    "graph:verification-task-complete"}
    mc = json.loads(rows[0]["metadata_json"])
    assert mc["task_id"] == t.task_id
    assert mc["hypothesis_id"] == hyp.hypothesis_id
    assert mc["evidence_requirements"] == ["evd_a", "evd_b"]
    ms = json.loads(rows[1]["metadata_json"])
    assert ms["from_status"] == "created" and ms["to_status"] == "running"


def test_vt_cmp_008_no_assertion_leakage(db, rt, hyp):
    """VT-CMP-008：no assertion leakage——task 全生命周期零 akb_assertions/kg_*
    写入 + 零 hypothesis 状态修改。"""
    n_a = db.execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
    n_n = db.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"]
    h_before = rt._hs.get_hypothesis(hyp.hypothesis_id).status
    t = rt.create_task(**_kw(hyp.hypothesis_id))
    rt.start_task(t.task_id, actor_id="human:reviewer")
    rt.complete_task(t.task_id, actor_id="human:reviewer")
    assert db.execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"] == n_a
    assert db.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"] == n_n
    assert rt._hs.get_hypothesis(hyp.hypothesis_id).status == h_before


def test_vt_cmp_009_replay_determinism(db, rt, svc, hyp):
    """VT-CMP-009：replay determinism——跨实例重放状态一致（seq 锚重放）+
    canonical ordering。"""
    t = rt.create_task(**_kw(hyp.hypothesis_id))
    rt.start_task(t.task_id, actor_id="human:reviewer")
    rt.complete_task(t.task_id, actor_id="human:reviewer")
    t2 = VerificationTaskRuntime(db, hypothesis_service=svc).get_task(t.task_id)
    assert t2.status == "completed"
    assert t2.evidence_requirements == ("evd_a", "evd_b")   # canonical 序
    # 多任务重放互不串扰（seq 单调重放）
    t_b = rt.create_task(**_kw(hyp.hypothesis_id, spec="第二任务"))
    assert rt.get_task(t.task_id).status == "completed"
    assert rt.get_task(t_b.task_id).status == "created"
    # 不存在 → None（不 fabricate）
    assert rt.get_task("vt_nonexistent") is None


def test_vt_cmp_010_frozen_regression(db, rt, svc, hyp):
    """VT-CMP-010：frozen regression——V0.5/V0.6/V0.7 frozen 模块零感知
    （单向依赖）+ legacy 零引用 + 建图回归。"""
    import inspect
    import agent_kb.graph as legacy
    import agent_kb.kgraph.orchestrator as orch_mod
    import agent_kb.kgraph.context as ctx_mod
    import agent_kb.domains.runtime as dom_mod
    import agent_kb.rules.runtime as rules_mod
    import agent_kb.policy.runtime as pol_mod
    import agent_kb.domains.guard as guard_mod
    for mod in (orch_mod, ctx_mod, dom_mod, rules_mod, pol_mod, guard_mod):
        src = inspect.getsource(mod)
        assert "VerificationTask" not in src
    for sym in ("VerificationTaskRuntime", "VerificationTask"):
        assert not hasattr(legacy, sym)
    # 建图回归：task 活动后投影/查询面不变
    from agent_kb.kgraph import (
        GraphPersistenceService, GraphProjectionService, GraphQueryService)
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('vt', 'document', 'VT')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version,"
               " content_hash, ingested_at) VALUES ('dvt', 'vt', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    eid = EvidenceStore(db).create(document_id="dvt", content="VT 锚定。",
                                   extraction_method="t").evidence_id
    GraphPersistenceService(db).persist(GraphProjectionService().process(db))
    q = GraphQueryService(db)
    v1 = q.canonical_view()
    t = rt.create_task(**_kw(hyp.hypothesis_id))
    rt.start_task(t.task_id, actor_id="human:reviewer")
    rt.complete_task(t.task_id, actor_id="human:reviewer")
    assert q.canonical_view() == v1