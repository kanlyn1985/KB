# -*- coding: utf-8 -*-
"""VD-CMP-001..010（AKB-V08-IMPL-003：Verdict Runtime acceptance）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.hypothesis import (
    HypothesisService,
    VerdictError,
    VerdictRuntime,
    VerificationTaskRuntime,
    verdict_identity,
)
from agent_kb.storage.migrations import SchemaMigrator


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    SchemaMigrator(con).migrate()
    # 锚定 evidence（verdict evidence_refs 校验面）
    con.execute("INSERT INTO akb_sources (source_id, source_type, name)"
                " VALUES ('vd', 'document', 'VD')")
    con.execute("INSERT INTO akb_documents (document_id, source_id, version,"
                " content_hash, ingested_at) VALUES ('dvd', 'vd', '1.0', 'h',"
                " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    ev = EvidenceStore(con).create(document_id="dvd", content="验证锚证据。",
                                   extraction_method="t")
    yield con, ev.evidence_id
    con.close()


@pytest.fixture
def stack(db):
    con, eid = db
    hs = HypothesisService(con)
    hyp = hs.create_hypothesis(
        statement="H: VD 锚定猜想", domain_ref="industrial", pack_ref="dpr_a",
        policy_ref="pol_b", context_ref="grc_c", origin="human")
    tr = VerificationTaskRuntime(con, hypothesis_service=hs)
    task = tr.create_task(hypothesis_id=hyp.hypothesis_id,
                          task_type="evidence_review",
                          spec="VD 验证规格",
                          evidence_requirements=(eid,))
    vr = VerdictRuntime(con, hypothesis_service=hs, task_runtime=tr)
    return {"hs": hs, "tr": tr, "vr": vr, "hyp": hyp, "task": task, "eid": eid}


def _complete(stack):
    stack["tr"].start_task(stack["task"].task_id, actor_id="human:reviewer")
    stack["tr"].complete_task(stack["task"].task_id, actor_id="human:reviewer")


def test_vd_cmp_001_verdict_create(db, stack):
    """VD-CMP-001：verdict create——全字段 + hypothesis 迁移 open→supported。"""
    _complete(stack)
    v = stack["vr"].create_verdict(
        hypothesis_id=stack["hyp"].hypothesis_id,
        task_id=stack["task"].task_id, result="supported",
        evidence_refs=(stack["eid"],), reason="证据充分",
        actor_id="human:reviewer")
    assert v.verdict_id.startswith("vrd_")
    assert v.result == "supported" and v.actor == "human:reviewer"
    assert v.evidence_refs == (stack["eid"],)
    assert v.created_seq > 0
    # 迁移驱动：hypothesis open → supported
    assert stack["hs"].get_hypothesis(
        stack["hyp"].hypothesis_id).status == "supported"


def test_vd_cmp_002_deterministic_id(db, stack):
    """VD-CMP-002：deterministic id——同四元组跨实例全等；输入变化 → id 变。"""
    _complete(stack)
    v1 = stack["vr"].create_verdict(
        hypothesis_id=stack["hyp"].hypothesis_id,
        task_id=stack["task"].task_id, result="supported",
        evidence_refs=(stack["eid"],))
    v2 = VerdictRuntime(db[0], hypothesis_service=stack["hs"],
                        task_runtime=stack["tr"]).create_verdict(
        hypothesis_id=stack["hyp"].hypothesis_id,
        task_id=stack["task"].task_id, result="supported",
        evidence_refs=(stack["eid"],))
    assert v1.verdict_id == v2.verdict_id
    assert v1.verdict_id == verdict_identity(
        hypothesis_id=stack["hyp"].hypothesis_id,
        task_id=stack["task"].task_id, result="supported",
        evidence_refs=(stack["eid"],))
    # inconclusive verdict（独立 hypothesis——本 task 已绑定 supported 语义）
    hyp2 = stack["hs"].create_hypothesis(
        statement="H: 002 别路", domain_ref="industrial", pack_ref="dpr_a",
        policy_ref="pol_b", context_ref="grc_c", origin="human")
    task2 = stack["tr"].create_task(hypothesis_id=hyp2.hypothesis_id,
                                    task_type="expert_review", spec="s",
                                    evidence_requirements=(stack["eid"],))
    stack["tr"].start_task(task2.task_id, actor_id="human:reviewer")
    stack["tr"].complete_task(task2.task_id, actor_id="human:reviewer")
    v3 = stack["vr"].create_verdict(
        hypothesis_id=hyp2.hypothesis_id,
        task_id=task2.task_id, result="inconclusive",
        evidence_refs=(stack["eid"],))
    assert v3.verdict_id != v1.verdict_id


def test_vd_cmp_003_duplicate_idempotent(db, stack):
    """VD-CMP-003：duplicate idempotent——重复 verdict 零重复审计/零重复迁移。"""
    _complete(stack)
    v1 = stack["vr"].create_verdict(
        hypothesis_id=stack["hyp"].hypothesis_id,
        task_id=stack["task"].task_id, result="supported",
        evidence_refs=(stack["eid"],))
    n1 = db[0].execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                       " activity='graph:hypothesis-verdict'").fetchone()["c"]
    v2 = stack["vr"].create_verdict(
        hypothesis_id=stack["hyp"].hypothesis_id,
        task_id=stack["task"].task_id, result="supported",
        evidence_refs=(stack["eid"],))
    n2 = db[0].execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                       " activity='graph:hypothesis-verdict'").fetchone()["c"]
    assert v1.verdict_id == v2.verdict_id and n1 == n2 == 1
    # 幂等重放不触发重复迁移（hypothesis 仍 supported，非二次审计）
    assert stack["hs"].get_hypothesis(
        stack["hyp"].hypothesis_id).status == "supported"


def test_vd_cmp_004_task_completed_validation(db, stack):
    """VD-CMP-004：task completed validation——未完成 task 拒绝
    （E-V08-TASK-NOT-COMPLETED）；不存在 task/hypothesis 拒绝。"""
    with pytest.raises(VerdictError, match="E-V08-TASK-NOT-COMPLETED"):
        stack["vr"].create_verdict(
            hypothesis_id=stack["hyp"].hypothesis_id,
            task_id=stack["task"].task_id, result="supported",
            evidence_refs=(stack["eid"],))
    _complete(stack)
    with pytest.raises(VerdictError, match="E-V08-HYPOTHESIS-NOT-FOUND"):
        stack["vr"].create_verdict(
            hypothesis_id="hyp_ghost", task_id=stack["task"].task_id,
            result="supported", evidence_refs=(stack["eid"],))
    with pytest.raises(VerdictError, match="E-V08-TASK-NOT-FOUND"):
        stack["vr"].create_verdict(
            hypothesis_id=stack["hyp"].hypothesis_id,
            task_id="vt_ghost", result="supported",
            evidence_refs=(stack["eid"],))


def test_vd_cmp_005_invalid_result_fail_close(db, stack):
    """VD-CMP-005：invalid result fail-close——assertion 域结果禁入 + 未知结果
    拒绝 + 不存在 evidence 拒绝（零 fabricate）。"""
    _complete(stack)
    for bad in ("validated", "asserted", "inferred", "pending"):
        with pytest.raises(VerdictError, match="E-V08-VERDICT-INVALID"):
            stack["vr"].create_verdict(
                hypothesis_id=stack["hyp"].hypothesis_id,
                task_id=stack["task"].task_id, result=bad,
                evidence_refs=(stack["eid"],))
    with pytest.raises(VerdictError, match="E-V08-VERDICT-INVALID"):
        stack["vr"].create_verdict(
            hypothesis_id=stack["hyp"].hypothesis_id,
            task_id=stack["task"].task_id, result="supported",
            evidence_refs=("evd_ghost",))
    with pytest.raises(VerdictError, match="E-V08-VERDICT-INVALID"):
        stack["vr"].create_verdict(
            hypothesis_id=stack["hyp"].hypothesis_id,
            task_id=stack["task"].task_id, result="supported",
            evidence_refs=())


def test_vd_cmp_006_hypothesis_transition(db, stack):
    """VD-CMP-006：hypothesis transition——verdict 只能驱动 open→supported/
    refuted；inconclusive 保持 open；supported 后不可再迁移（零直通）。"""
    _complete(stack)
    # supported 驱动迁移
    stack["vr"].create_verdict(
        hypothesis_id=stack["hyp"].hypothesis_id,
        task_id=stack["task"].task_id, result="supported",
        evidence_refs=(stack["eid"],), actor_id="human:reviewer")
    assert stack["hs"].get_hypothesis(
        stack["hyp"].hypothesis_id).status == "supported"
    # supported 后再 verdict（同 task）→ 幂等返回，零直通零二次迁移
    v = stack["vr"].create_verdict(
        hypothesis_id=stack["hyp"].hypothesis_id,
        task_id=stack["task"].task_id, result="supported",
        evidence_refs=(stack["eid"],))
    assert v.verdict_id.startswith("vrd_")
    # inconclusive：open 保持
    hyp2 = stack["hs"].create_hypothesis(
        statement="H: inconclusive 路径", domain_ref="industrial",
        pack_ref="dpr_a", policy_ref="pol_b", context_ref="grc_c",
        origin="human")
    task2 = stack["tr"].create_task(hypothesis_id=hyp2.hypothesis_id,
                                    task_type="expert_review", spec="s2",
                                    evidence_requirements=(stack["eid"],))
    stack["tr"].start_task(task2.task_id, actor_id="human:reviewer")
    stack["tr"].complete_task(task2.task_id, actor_id="human:reviewer")
    stack["vr"].create_verdict(hypothesis_id=hyp2.hypothesis_id,
                               task_id=task2.task_id, result="inconclusive",
                               evidence_refs=(stack["eid"],))
    assert stack["hs"].get_hypothesis(hyp2.hypothesis_id).status == "open"
    # supported → assertion/validated 禁止（transition_status 红线复证）
    from agent_kb.hypothesis import HypothesisError
    for bad in ("asserted", "validated", "inferred"):
        with pytest.raises(HypothesisError, match="E-V08-INVALID-TRANSITION"):
            stack["hs"].transition_status(stack["hyp"].hypothesis_id,
                                          new_status=bad,
                                          actor_id="human:reviewer")


def test_vd_cmp_007_provenance_audit(db, stack):
    """VD-CMP-007：provenance audit——graph:hypothesis-verdict 记录 verdict_id/
    hypothesis_id/task_id/result/evidence_refs/actor。"""
    _complete(stack)
    stack["vr"].create_verdict(
        hypothesis_id=stack["hyp"].hypothesis_id,
        task_id=stack["task"].task_id, result="supported",
        evidence_refs=(stack["eid"],), reason="r1",
        actor_id="human:reviewer")
    rows = [dict(x) for x in db[0].execute(
        "SELECT * FROM akb_provenance WHERE activity='graph:hypothesis-verdict'")]
    assert len(rows) == 1
    m = json.loads(rows[0]["metadata_json"])
    assert m["hypothesis_id"] == stack["hyp"].hypothesis_id
    assert m["task_id"] == stack["task"].task_id
    assert m["result"] == "supported" and m["actor"] == "human:reviewer"
    assert m["evidence_refs"] == [stack["eid"]]


def test_vd_cmp_008_no_assertion_leakage(db, stack):
    """VD-CMP-008：no assertion leakage——verdict 全流程零 akb_assertions/
    kg_nodes/kg_edges 写入 + 零 candidate promotion。"""
    con = db[0]
    n_a = con.execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
    n_n = con.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"]
    n_e = con.execute("SELECT COUNT(*) c FROM kg_edges").fetchone()["c"]
    _complete(stack)
    stack["vr"].create_verdict(
        hypothesis_id=stack["hyp"].hypothesis_id,
        task_id=stack["task"].task_id, result="supported",
        evidence_refs=(stack["eid"],))
    assert con.execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"] == n_a
    assert con.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"] == n_n
    assert con.execute("SELECT COUNT(*) c FROM kg_edges").fetchone()["c"] == n_e


def test_vd_cmp_009_replay_determinism(db, stack):
    """VD-CMP-009：replay determinism——跨实例 verdict 重建一致 + list canonical
    排序 + 多 verdict seq 序不串扰。"""
    _complete(stack)
    v1 = stack["vr"].create_verdict(
        hypothesis_id=stack["hyp"].hypothesis_id,
        task_id=stack["task"].task_id, result="inconclusive",
        evidence_refs=(stack["eid"],))
    # 第二个 verdict（不同 result——verdict_id 不同）
    v2 = stack["vr"].create_verdict(
        hypothesis_id=stack["hyp"].hypothesis_id,
        task_id=stack["task"].task_id, result="supported",
        evidence_refs=(stack["eid"],))
    vr2 = VerdictRuntime(db[0], hypothesis_service=stack["hs"],
                         task_runtime=stack["tr"])
    assert vr2.get_verdict(v1.verdict_id).result == "inconclusive"
    assert vr2.get_verdict(v2.verdict_id).result == "supported"
    lst = vr2.list_verdicts(stack["hyp"].hypothesis_id)
    assert [v.verdict_id for v in lst] == sorted(v.verdict_id for v in lst)
    assert len(lst) == 2
    # 不存在 → None（不 fabricate）
    assert vr2.get_verdict("vrd_nonexistent") is None


def test_vd_cmp_010_frozen_regression(db, stack):
    """VD-CMP-010：frozen regression——V0.5/V0.6/V0.7 frozen 模块零 Verdict 感知
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
        assert "VerdictRuntime" not in inspect.getsource(mod)
    for sym in ("VerdictRuntime", "Verdict"):
        assert not hasattr(legacy, sym)
    # 建图回归：verdict 活动后投影/查询面不变
    from agent_kb.kgraph import (
        GraphPersistenceService, GraphProjectionService, GraphQueryService)
    con = db[0]
    con.execute("INSERT INTO akb_sources (source_id, source_type, name)"
                " VALUES ('vd2', 'document', 'VD2')")
    con.execute("INSERT INTO akb_documents (document_id, source_id, version,"
                " content_hash, ingested_at) VALUES ('dvd2', 'vd2', '1.0',"
                " 'h', strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    EvidenceStore(con).create(document_id="dvd2", content="建图锚。",
                              extraction_method="t")
    GraphPersistenceService(con).persist(GraphProjectionService().process(con))
    q = GraphQueryService(con)
    v1 = q.canonical_view()
    _complete(stack)
    stack["vr"].create_verdict(
        hypothesis_id=stack["hyp"].hypothesis_id,
        task_id=stack["task"].task_id, result="refuted",
        evidence_refs=(stack["eid"],))
    assert q.canonical_view() == v1