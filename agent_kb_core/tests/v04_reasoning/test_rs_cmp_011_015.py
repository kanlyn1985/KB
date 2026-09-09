# -*- coding: utf-8 -*-
"""RS-CMP-011..015（AKB-V04-IMPL-003：inferred candidate governance integration）。

RS-CMP-011 inferred→validated 人工治理流（human actor + reason + 独立证据校验）
RS-CMP-012 validation provenance activity（govern:validate 落库可查）
RS-CMP-013 governance audit trail（时序完整可回放）
RS-CMP-014 failure isolation strengthening（非法迁移拒绝留审计 + 零状态破坏）
RS-CMP-015 治理回归锚（inferred→asserted 永禁；extracted/observed 治理面不变）
"""
from __future__ import annotations

import json

import pytest

from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.evidence_core.state_machine import validate_transition
from agent_kb.reasoning import (
    BuiltinRuleReasoner,
    InferenceGovernanceService,
    ReasoningContext,
    ReasoningEngine,
)


def _seed(db):
    """inferred candidate（经 engine）+ 一条 extracted 对照（带 evidence_refs——
    独立证据校验面）。"""
    store = AssertionStore(db)
    from agent_kb.evidence_core import EvidenceStore
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('gv', 'document', 'GV')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at) VALUES ('dgv', 'gv', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    ev = EvidenceStore(db).create(document_id="dgv", content="治理锚证据文本。",
                                  extraction_method="t")
    parent = store.create_candidate(
        subject_ref="A", predicate_ref="before",
        object={"kind": "literal", "value": "B"}, assertion_type="extracted",
        ontology_scope="test", actor_id="system:seed", confidence=0.9,
        evidence_refs=[ev.evidence_id])
    eng = ReasoningEngine(db, provider=BuiltinRuleReasoner())
    r = eng.reason([parent.assertion_id], actor_id="system:reasoner",
                   context=ReasoningContext("test"))
    # before 单 parent 无 RR-02 闭包（需两跳）——直接用 RR-01 通道造 inferred：
    if not r["assertions"]:
        sat = store.create_candidate(
            subject_ref="Pump-A", predicate_ref="satisfies_rule",
            object={"kind": "literal", "value": "RuleX"}, assertion_type="extracted",
            ontology_scope="test", actor_id="system:seed", confidence=0.9,
            evidence_refs=[ev.evidence_id])
        req = store.create_candidate(
            subject_ref="", predicate_ref="rule_requires",
            object={"kind": "literal", "value": "Inspection"}, assertion_type="extracted",
            ontology_scope="test", actor_id="system:seed", confidence=0.9,
            evidence_refs=[ev.evidence_id])
        r = eng.reason([sat.assertion_id, req.assertion_id],
                       actor_id="system:reasoner", context=ReasoningContext("test"))
    assert r["assertions"], "inferred candidate must exist for governance tests"
    return {"store": store, "parent": parent, "run": r,
            "inferred": r["assertions"][0]}


def test_rs_cmp_011_inferred_validated_human_flow(db):
    """RS-CMP-011：inferred→validated 人工流（human actor；system/llm/agent 拒绝）。"""
    seeded = _seed(db)
    gov = InferenceGovernanceService(db, seeded["store"])
    inf = seeded["inferred"]
    # 非 human actor 拒绝（R-06 无自动晋升）
    with pytest.raises(ValueError, match="E-V04-GOVERNANCE-ACTOR"):
        gov.validate_inferred(assertion_id=inf.assertion_id,
                              actor_id="system:validator", reason="auto")
    # 缺 reason 拒绝
    with pytest.raises(ValueError, match="E-INVALID-REASON"):
        gov.validate_inferred(assertion_id=inf.assertion_id,
                              actor_id="human:reviewer", reason="  ")
    # 合法人工流
    result = gov.validate_inferred(assertion_id=inf.assertion_id,
                                   actor_id="human:reviewer",
                                   reason="治理复核通过：规则链可回放")
    assert result["accepted"] is True
    row = db.execute("SELECT status FROM akb_assertions WHERE assertion_id=?",
                     (inf.assertion_id,)).fetchone()
    assert row["status"] == "validated"          # candidate→validated 达成
    # 非 inferred 类型走此通道拒绝（extracted 用既有治理面）
    with pytest.raises(ValueError, match="E-V04-NOT-INFERRED"):
        gov.validate_inferred(assertion_id=seeded["parent"].assertion_id,
                              actor_id="human:reviewer", reason="x")


def test_rs_cmp_012_validation_provenance_activity(db):
    """RS-CMP-012：validation provenance activity（govern:validate + 既有 validate 双记）。"""
    seeded = _seed(db)
    gov = InferenceGovernanceService(db, seeded["store"])
    inf = seeded["inferred"]
    gov.validate_inferred(assertion_id=inf.assertion_id, actor_id="human:reviewer",
                          reason="复核通过")
    acts = [r["activity"] for r in db.execute(
        "SELECT activity FROM akb_provenance WHERE inputs_json LIKE ?",
        (f"%{inf.assertion_id}%",))]
    assert "govern:validate" in acts              # V0.4 治理审计活动
    # 既有 transition 记录（candidate→validated）也保留（V0.1 面）
    assert any(a.startswith("transition:") for a in acts)


def test_rs_cmp_013_governance_audit_trail(db):
    """RS-CMP-013：治理审计轨迹——validate/transition-rejected/transition 时序可回放。"""
    seeded = _seed(db)
    gov = InferenceGovernanceService(db, seeded["store"])
    inf = seeded["inferred"]
    gov.validate_inferred(assertion_id=inf.assertion_id, actor_id="human:reviewer",
                          reason="R1")
    gov.transition(assertion_id=inf.assertion_id, new_status="disputed",
                   actor_id="human:reviewer", reason="R2")
    # 非法迁移被拒 + 留审计
    with pytest.raises(ValueError):
        gov.transition(assertion_id=inf.assertion_id, new_status="asserted",
                       actor_id="human:reviewer", reason="R3")
    trail = gov.audit_trail(inf.assertion_id)
    actions = [t["action"] for t in trail]
    assert "validate" in actions and "transition" in actions
    assert "transition-rejected" in actions       # 拒绝也留痕
    # 时序有序 + reason 全记录
    assert [t["occurred_at"] for t in trail] == sorted(
        t["occurred_at"] for t in trail)
    reasons = {t["reason"] for t in trail}
    assert {"R1", "R2", "R3"} <= reasons
    # transition-rejected 记录含 violations
    rejected = next(t for t in trail if t["action"] == "transition-rejected")
    assert rejected["to_status"] == "asserted"


def test_rs_cmp_014_failure_isolation_strengthened(db):
    """RS-CMP-014：非法迁移零状态破坏 + inferred 治理后既有链保持 + 触发器兜底。"""
    seeded = _seed(db)
    gov = InferenceGovernanceService(db, seeded["store"])
    inf = seeded["inferred"]
    gov.validate_inferred(assertion_id=inf.assertion_id, actor_id="human:reviewer",
                          reason="ok")
    before = db.execute("SELECT status FROM akb_assertions WHERE assertion_id=?",
                        (inf.assertion_id,)).fetchone()["status"]
    # asserted 直写触发器拦截（status 保持）
    with pytest.raises(Exception):
        db.execute("UPDATE akb_assertions SET status='asserted' WHERE assertion_id=?",
                   (inf.assertion_id,))
    after = db.execute("SELECT status FROM akb_assertions WHERE assertion_id=?",
                       (inf.assertion_id,)).fetchone()["status"]
    assert before == after == "validated"         # 零状态破坏
    # validated→asserted（即使人工）仍被 inferred 硬门拒绝
    with pytest.raises(ValueError, match="E-ILLEGAL-TRANSITION"):
        gov.transition(assertion_id=inf.assertion_id, new_status="asserted",
                       actor_id="human:reviewer", reason="attempt")
    # dispute/deprecate 通道可用（治理面完整）
    gov.transition(assertion_id=inf.assertion_id, new_status="disputed",
                   actor_id="human:reviewer", reason="d")
    row = db.execute("SELECT status FROM akb_assertions WHERE assertion_id=?",
                     (inf.assertion_id,)).fetchone()
    assert row["status"] == "disputed"


def test_rs_cmp_015_governance_regression_anchors(db):
    """RS-CMP-015：extracted/observed 治理面不变（既有 validate/transition 行为零破坏）+
    inferred 链上 parent rejected 不自动失效（INV-005）。"""
    seeded = _seed(db)
    gov = InferenceGovernanceService(db, seeded["store"])
    parent = seeded["parent"]
    # extracted 的 validated 走既有通道（system:validator 可用——非 inferred 不受 human 限定）
    from agent_kb.evidence_core.assertions import AssertionValidator
    r = AssertionValidator(db).validate(assertion_id=parent.assertion_id,
                                        actor_id="system:validator")
    assert r["accepted"] is True
    row = db.execute("SELECT status FROM akb_assertions WHERE assertion_id=?",
                     (parent.assertion_id,)).fetchone()
    assert row["status"] == "validated"
    # parent disputed（validated→disputed 合法路径）→ inferred 子女不自动失效（INV-005）
    inf = seeded["inferred"]
    inf_id = inf.assertion_id
    seeded["store"].transition(assertion_id=parent.assertion_id, new_status="disputed",
                               actor_id="human:tester", reason="governance dispute")
    row2 = db.execute("SELECT status FROM akb_assertions WHERE assertion_id=?",
                      (inf_id,)).fetchone()
    assert row2["status"] in ("candidate", "validated")   # 未自动失效
    from agent_kb.reasoning import InferenceTraceService
    tr = InferenceTraceService(db).trace(inf_id)
    assert tr["assertion"] is not None            # 链仍可回溯