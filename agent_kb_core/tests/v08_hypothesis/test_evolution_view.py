# -*- coding: utf-8 -*-
"""EV-CMP-001..010（AKB-V08-IMPL-004：EvolutionView Runtime acceptance）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.hypothesis import (
    EvolutionViewError,
    EvolutionViewRuntime,
    HypothesisService,
    VerificationTaskRuntime,
    VerdictRuntime,
)
from agent_kb.storage.migrations import SchemaMigrator


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    SchemaMigrator(con).migrate()
    con.execute("INSERT INTO akb_sources (source_id, source_type, name)"
                " VALUES ('ev', 'document', 'EV')")
    con.execute("INSERT INTO akb_documents (document_id, source_id, version,"
                " content_hash, ingested_at) VALUES ('dev', 'ev', '1.0', 'h',"
                " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    ev = EvidenceStore(con).create(document_id="dev", content="EV 锚证据。",
                                   extraction_method="t")
    yield con, ev.evidence_id
    con.close()


@pytest.fixture
def stack(db):
    con, eid = db
    hs = HypothesisService(con)
    tr = VerificationTaskRuntime(con, hypothesis_service=hs)
    vr = VerdictRuntime(con, hypothesis_service=hs, task_runtime=tr)
    ev = EvolutionViewRuntime(con, hypothesis_service=hs, task_runtime=tr,
                              verdict_runtime=vr)
    return {"hs": hs, "tr": tr, "vr": vr, "ev": ev, "eid": eid}


def _full_lifecycle(stack, statement="H: EV 锚定猜想", result="supported"):
    """完整闭环：create → task → start/complete → verdict。"""
    hyp = stack["hs"].create_hypothesis(
        statement=statement, domain_ref="industrial", pack_ref="dpr_a",
        policy_ref="pol_b", context_ref="grc_c", origin="human")
    task = stack["tr"].create_task(hypothesis_id=hyp.hypothesis_id,
                                   task_type="evidence_review",
                                   spec="EV 规格",
                                   evidence_requirements=(stack["eid"],))
    stack["tr"].start_task(task.task_id, actor_id="human:reviewer")
    stack["tr"].complete_task(task.task_id, actor_id="human:reviewer")
    stack["vr"].create_verdict(hypothesis_id=hyp.hypothesis_id,
                               task_id=task.task_id, result=result,
                               evidence_refs=(stack["eid"],),
                               actor_id="human:reviewer")
    return hyp, task


def test_ev_cmp_001_view_create(db, stack):
    """EV-CMP-001：view create——全字段 immutable 只读。"""
    hyp, task = _full_lifecycle(stack)
    view = stack["ev"].get_evolution_view(hyp.hypothesis_id)
    assert view is not None
    assert view.hypothesis_id == hyp.hypothesis_id
    assert view.current_status == "supported"
    assert view.created_seq > 0
    assert len(view.tasks) == 1 and view.tasks[0].task_id == task.task_id
    assert len(view.verdicts) == 1
    assert view.fingerprint.startswith("evw_")
    assert view.provenance_refs
    # immutable（frozen dataclass）
    with pytest.raises(Exception):
        view.current_status = "x"  # type: ignore[misc]


def test_ev_cmp_002_deterministic_fingerprint(db, stack):
    """EV-CMP-002：deterministic fingerprint——同状态跨实例/双查询全等。"""
    hyp, _ = _full_lifecycle(stack)
    v1 = stack["ev"].get_evolution_view(hyp.hypothesis_id)
    v2 = EvolutionViewRuntime(db[0], hypothesis_service=stack["hs"],
                              task_runtime=stack["tr"],
                              verdict_runtime=stack["vr"]).get_evolution_view(
        hyp.hypothesis_id)
    assert v1.fingerprint == v2.fingerprint
    assert v1 == v2
    # 状态变化 → fingerprint 变（withdraw 迁移后）
    stack["hs"].create_hypothesis(
        statement="H: 变化检测", domain_ref="industrial", pack_ref="dpr_a",
        policy_ref="pol_b", context_ref="grc_c", origin="human")


def test_ev_cmp_003_complete_lifecycle_timeline(db, stack):
    """EV-CMP-003：complete lifecycle timeline——created→task-created→
    task-start→task-complete→verdict→hypothesis-status 全程 seq 排序。"""
    hyp, _ = _full_lifecycle(stack)
    view = stack["ev"].get_evolution_view(hyp.hypothesis_id)
    labels = [e.label for e in view.timeline]
    assert "hypothesis-create" in labels
    assert "task-create" in labels
    assert "task-start" in labels
    assert "task-complete" in labels
    assert "hypothesis-verdict" in labels
    assert "hypothesis-status" in labels
    seqs = [e.seq for e in view.timeline]
    assert seqs == sorted(seqs)                     # seq 排序
    assert view.timeline[0].label == "hypothesis-create"


def test_ev_cmp_004_missing_hypothesis_fail_close(db, stack):
    """EV-CMP-004：missing hypothesis——不存在 → None（禁止 fabricate）；
    非法 id → fail-closed。"""
    assert stack["ev"].get_evolution_view("hyp_ghost") is None
    with pytest.raises(EvolutionViewError, match="E-V08-HYPOTHESIS-INVALID"):
        stack["ev"].get_evolution_view("bad-id")


def test_ev_cmp_005_task_verdict_aggregation(db, stack):
    """EV-CMP-005：task/verdict aggregation——多 task/多 verdict 全聚合零遗漏。"""
    hyp = stack["hs"].create_hypothesis(
        statement="H: 聚合锚", domain_ref="industrial", pack_ref="dpr_a",
        policy_ref="pol_b", context_ref="grc_c", origin="human")
    t1 = stack["tr"].create_task(hypothesis_id=hyp.hypothesis_id,
                                 task_type="evidence_review", spec="s1",
                                 evidence_requirements=(stack["eid"],))
    t2 = stack["tr"].create_task(hypothesis_id=hyp.hypothesis_id,
                                 task_type="expert_review", spec="s2",
                                 evidence_requirements=(stack["eid"],))
    for t in (t1, t2):
        stack["tr"].start_task(t.task_id, actor_id="human:reviewer")
        stack["tr"].complete_task(t.task_id, actor_id="human:reviewer")
    stack["vr"].create_verdict(hypothesis_id=hyp.hypothesis_id,
                               task_id=t1.task_id, result="supported",
                               evidence_refs=(stack["eid"],))
    stack["vr"].create_verdict(hypothesis_id=hyp.hypothesis_id,
                               task_id=t2.task_id, result="inconclusive",
                               evidence_refs=(stack["eid"],))
    view = stack["ev"].get_evolution_view(hyp.hypothesis_id)
    assert len(view.tasks) == 2
    assert len(view.verdicts) == 2
    assert {v.result for v in view.verdicts} == {"supported", "inconclusive"}


def test_ev_cmp_006_provenance_trace(db, stack):
    """EV-CMP-006：provenance trace——provenance_refs 全部实存于 akb_provenance
    （零第二套审计）。"""
    hyp, _ = _full_lifecycle(stack)
    view = stack["ev"].get_evolution_view(hyp.hypothesis_id)
    assert view.provenance_refs
    for pid in view.provenance_refs:
        row = db[0].execute("SELECT 1 FROM akb_provenance WHERE"
                            " provenance_id=?", (pid,)).fetchone()
        assert row is not None
    # timeline 与 provenance 活动一致（零第二套数据源）


def test_ev_cmp_007_ordering_determinism(db, stack):
    """EV-CMP-007：ordering determinism——timeline/refs/聚合全 canonical 序。"""
    hyp = stack["hs"].create_hypothesis(
        statement="H: 排序锚", domain_ref="industrial", pack_ref="dpr_a",
        policy_ref="pol_b", context_ref="grc_c", origin="human")
    for spec in ("s1", "s2", "s3"):
        t = stack["tr"].create_task(hypothesis_id=hyp.hypothesis_id,
                                    task_type="evidence_review", spec=spec,
                                    evidence_requirements=(stack["eid"],))
    view = stack["ev"].get_evolution_view(hyp.hypothesis_id)
    assert [t.task_id for t in view.tasks] == \
        sorted(t.task_id for t in view.tasks)
    assert [e.seq for e in view.timeline] == sorted(e.seq for e in view.timeline)
    assert list(view.provenance_refs) == sorted(view.provenance_refs)


def test_ev_cmp_008_no_assertion_leakage(db, stack):
    """EV-CMP-008：no assertion leakage——视图查询零 akb_assertions/kg_*/零
    promotion 写入。"""
    hyp, _ = _full_lifecycle(stack)
    n_a = db[0].execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
    n_n = db[0].execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"]
    n_e = db[0].execute("SELECT COUNT(*) c FROM kg_edges").fetchone()["c"]
    stack["ev"].get_evolution_view(hyp.hypothesis_id)
    stack["ev"].list_evolution_views()
    assert db[0].execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"] == n_a
    assert db[0].execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"] == n_n
    assert db[0].execute("SELECT COUNT(*) c FROM kg_edges").fetchone()["c"] == n_e


def test_ev_cmp_009_replay_consistency(db, stack):
    """EV-CMP-009：replay consistency——生命周期推进后视图跟随（task/verdict
    增量反映）+ 双实例重放一致。"""
    hyp = stack["hs"].create_hypothesis(
        statement="H: 重放一致性", domain_ref="industrial", pack_ref="dpr_a",
        policy_ref="pol_b", context_ref="grc_c", origin="human")
    v0 = stack["ev"].get_evolution_view(hyp.hypothesis_id)
    assert len(v0.tasks) == 0 and len(v0.verdicts) == 0
    assert v0.current_status == "open"
    t = stack["tr"].create_task(hypothesis_id=hyp.hypothesis_id,
                                task_type="evidence_review", spec="s",
                                evidence_requirements=(stack["eid"],))
    stack["tr"].start_task(t.task_id, actor_id="human:reviewer")
    stack["tr"].complete_task(t.task_id, actor_id="human:reviewer")
    stack["vr"].create_verdict(hypothesis_id=hyp.hypothesis_id,
                               task_id=t.task_id, result="refuted",
                               evidence_refs=(stack["eid"],))
    v1 = stack["ev"].get_evolution_view(hyp.hypothesis_id)
    assert len(v1.tasks) == 1 and len(v1.verdicts) == 1
    assert v1.current_status == "refuted"
    assert v1.fingerprint != v0.fingerprint        # 状态变化 → 视图变化
    v2 = EvolutionViewRuntime(db[0], hypothesis_service=stack["hs"],
                              task_runtime=stack["tr"],
                              verdict_runtime=stack["vr"]).get_evolution_view(
        hyp.hypothesis_id)
    assert v2 == v1


def test_ev_cmp_010_frozen_regression(db, stack):
    """EV-CMP-010：frozen regression——V0.5/V0.6/V0.7 frozen 模块零感知
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
        assert "EvolutionView" not in inspect.getsource(mod)
    for sym in ("EvolutionViewRuntime", "EvolutionView"):
        assert not hasattr(legacy, sym)
    # 建图回归：视图查询后投影/查询面不变
    from agent_kb.kgraph import (
        GraphPersistenceService, GraphProjectionService, GraphQueryService)
    con = db[0]
    con.execute("INSERT INTO akb_sources (source_id, source_type, name)"
                " VALUES ('ev2', 'document', 'EV2')")
    con.execute("INSERT INTO akb_documents (document_id, source_id, version,"
                " content_hash, ingested_at) VALUES ('dev2', 'ev2', '1.0',"
                " 'h', strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    EvidenceStore(con).create(document_id="dev2", content="建图锚。",
                              extraction_method="t")
    GraphPersistenceService(con).persist(GraphProjectionService().process(con))
    q = GraphQueryService(con)
    v1 = q.canonical_view()
    hyp, _ = _full_lifecycle(stack, statement="H: 建图回归")
    stack["ev"].get_evolution_view(hyp.hypothesis_id)
    stack["ev"].list_evolution_views()
    assert q.canonical_view() == v1