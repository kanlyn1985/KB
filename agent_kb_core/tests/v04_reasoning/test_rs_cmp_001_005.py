# -*- coding: utf-8 -*-
"""RS-CMP-001..005（V0.4 Reasoner Core 第一阶段验收）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.reasoning import BuiltinRuleReasoner, ReasoningEngine
from agent_kb.reasoning.models import canonical_json


def _ids(r):
    return [a.assertion_id for a in r["assertions"]]


def test_rs_cmp_001_inferred_creation_with_full_derivation(db, seeded, engine, ctx):
    """RS-CMP-001：inferred 创建含完整 derivation（六键）。"""
    made = seeded["made"]
    r = engine.reason([made["ab"].assertion_id, made["bc"].assertion_id],
                      actor_id="system:reasoner", context=ctx)
    assert r["ok"] and r["assertions"]
    a = next(a for a in r["assertions"] if a.predicate_ref == "before"
             and a.subject_ref == "A")
    d = a.derivation
    for key in ("rule_ref", "parent_assertions", "reasoner_id",
                "rule_input_snapshot", "confidence_basis", "depth"):
        assert d[key], f"derivation key {key} missing"
    assert a.assertion_type == "inferred"
    assert a.status == "candidate"                      # R-01 恒 candidate
    assert set(a.evidence_refs) == set(made["ab"].evidence_refs) | set(
        made["bc"].evidence_refs)                       # R-05 parent 并集
    # rule_input_snapshot 可回放（DC-04）
    snapshot = json.loads(d["rule_input_snapshot"])
    assert snapshot and all("assertion_id" in s for s in snapshot)
    # provenance(activity=infer) 落库
    rows = list(db.execute("SELECT activity FROM akb_provenance WHERE activity='infer'"))
    assert rows


def test_rs_cmp_002_missing_derivation_rejected(db, seeded, ctx):
    """RS-CMP-002：缺 derivation/rule_ref 的提案被拒绝（继承 INV-002）。"""
    made = seeded["made"]
    parents = [seeded["store"]._row_to_assertion(db.execute(
        "SELECT * FROM akb_assertions WHERE assertion_id=?",
        (made["ab"].assertion_id,)).fetchone())] \
        if hasattr(seeded["store"], "_row_to_assertion") else None
    from agent_kb.reasoning.engine import ReasoningEngine as RE
    eng = RE(db, provider=BuiltinRuleReasoner())
    from agent_kb.reasoning.models import InferredProposal
    bad = InferredProposal(
        proposal_id="inf_0001", subject_ref="A", predicate_ref="before",
        object={"kind": "literal", "value": "C"},
        rule_ref="",                                # 缺 rule_ref
        parent_assertions=[made["ab"].assertion_id],
        reasoner_id="builtin-rule-reasoner",
        rule_input_snapshot=canonical_json([{"assertion_id": made["ab"].assertion_id}]))
    assert bad.validate(), "malformed proposal must yield violations"
    # 引擎路径：malformed 提案级隔离（warning + 零候选）
    class BadProvider:
        def reasoner_id(self):
            return "bad"
        def rule_version(self):
            return "v0"
        def infer(self, parent_assertions, context):
            bad2 = InferredProposal(
                proposal_id="inf_0001", subject_ref="A", predicate_ref="before",
                object={"kind": "literal", "value": "C"},
                rule_ref="", parent_assertions=[made["ab"].assertion_id],
                reasoner_id="bad", rule_input_snapshot="")
            return [bad2]
    eng2 = ReasoningEngine(db, provider=BadProvider())
    r = eng2.reason([made["ab"].assertion_id], actor_id="system:reasoner", context=ctx)
    assert r["ok"] and not r["assertions"] and r["warnings"]


def test_rs_cmp_003_parent_boundary_and_cycle_detection(db, seeded, engine, ctx):
    """RS-CMP-003：parent 存在性 + 环检测 + 深度限制。"""
    made = seeded["made"]
    # 不存在 parent → E-V04-PARENT-NOT-FOUND
    r0 = engine.reason(["ghost-assertion"], actor_id="system:reasoner", context=ctx)
    assert not r0["ok"] and any("E-V04-PARENT-NOT-FOUND" in e for e in r0["errors"])
    # 深度限制（max_depth=0 → 任何提案超限）
    from agent_kb.reasoning import ReasoningContext
    r1 = engine.reason([made["ab"].assertion_id, made["bc"].assertion_id],
                       actor_id="system:reasoner",
                       context=ReasoningContext(ontology_scope="test", max_depth=0))
    assert not r1["assertions"] and any(
        "E-V04-DEPTH-EXCEEDED" in w for w in r1["warnings"])
    # 正常深度（默认 8）
    r2 = engine.reason([made["ab"].assertion_id, made["bc"].assertion_id],
                       actor_id="system:reasoner", context=ctx)
    assert r2["assertions"]


def test_rs_cmp_004_no_inferred_asserted_promotion(db, seeded):
    """RS-CMP-004：inferred→asserted 永久禁止（State Machine 继承）。"""
    made = seeded["made"]
    engine = ReasoningEngine(db, provider=BuiltinRuleReasoner())
    ctx = seeded.get("ctx")
    from agent_kb.reasoning import ReasoningContext
    r = engine.reason([made["ab"].assertion_id, made["bc"].assertion_id],
                      actor_id="system:reasoner",
                      context=ReasoningContext(ontology_scope="test"))
    assert r["assertions"]
    a = r["assertions"][0]
    # 全部产物 status=candidate
    assert all(x.status == "candidate" and x.assertion_type == "inferred"
               for x in r["assertions"])
    # 直写 asserted 被触发器拦截（V0.1 兜底）
    with pytest.raises(Exception):
        db.execute("UPDATE akb_assertions SET status='asserted' WHERE assertion_id=?",
                   (a.assertion_id,))
    # 状态机 API 层拒绝（keyword-only 签名）
    from agent_kb.evidence_core.state_machine import validate_transition
    v = validate_transition(current_status="candidate", new_status="asserted",
                            assertion_type="inferred", actor_id="human:tester",
                            evidence_count=1)
    assert v and any("E-ILLEGAL-TRANSITION" in x for x in v)
    # 合法迁移 candidate→validated 仍可用（治理面不变）
    v2 = validate_transition(current_status="candidate", new_status="validated",
                             assertion_type="inferred", actor_id="human:tester",
                             evidence_count=1)
    assert not v2


def test_rs_cmp_005_provider_neutrality_and_determinism(db, seeded, engine, ctx):
    """RS-CMP-005：provider 协议 + 确定性（同输入双跑提案级全等 + fingerprint 稳定）。"""
    made = seeded["made"]
    from agent_kb.reasoning.provider import ReasonerProvider
    assert isinstance(BuiltinRuleReasoner(), ReasonerProvider)   # Protocol 结构
    pids = [made["ab"].assertion_id, made["bc"].assertion_id]
    r1 = engine.reason(pids, actor_id="system:reasoner", context=ctx)
    r2 = engine.reason(pids, actor_id="system:reasoner", context=ctx)
    assert r1["fingerprint"] == r2["fingerprint"]
    # 逆序 parent 输入 → 同 fingerprint（canonical sorted）
    r3 = engine.reason(list(reversed(pids)), actor_id="system:reasoner", context=ctx)
    assert r3["fingerprint"] == r1["fingerprint"]
    # 提案级确定性：derivation/三元/置信全等（除 assertion_id 事件性字段）
    def sem(r):
        return [(a.subject_ref, a.predicate_ref, canonical_json(a.object),
                 a.derivation["rule_ref"], a.confidence,
                 tuple(sorted(a.evidence_refs))) for a in r["assertions"]]
    assert sem(r1) == sem(r2)


def test_rs_cmp_005b_rules_behaviour(db, seeded, engine, ctx):
    """RR-01..04 行为面（deduction/传递/佐证/矛盾旗标）。"""
    made = seeded["made"]
    r = engine.reason([made[k].assertion_id for k in
                       ("sat", "req", "ab", "bc", "same1", "same2", "diff1", "diff2")],
                      actor_id="system:reasoner", context=ctx)
    got = {(a.subject_ref, a.predicate_ref, a.object.get("value"))
           for a in r["assertions"]}
    assert ("Pump-A", "requires", "Inspection") in got            # RR-01
    assert ("A", "before", "C") in got                            # RR-02
    corrob = [a for a in r["assertions"] if a.derivation["rule_ref"].startswith("RR-03")]
    assert corrob and corrob[0].subject_ref == "OBC"              # RR-03
    dispute = [a for a in r["assertions"] if a.derivation["rule_ref"].startswith("RR-04")]
    assert dispute and dispute[0].object["value"] == "__DISPUTED__"  # RR-04（不裁决）
    # 跨实体互斥不误产（OBC/MOT 分组独立）
    assert not any(a.subject_ref == "OBC" and a.object.get("value") == "__DISPUTED__"
                   for a in r["assertions"])