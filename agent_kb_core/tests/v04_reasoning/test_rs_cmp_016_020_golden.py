# -*- coding: utf-8 -*-
"""RS-CMP-016..020（AKB-V04-IMPL-004：V0.4 Reasoning Golden P/N/D 分层验证）。

数据集：agent_kb_core/tests/golden/v04_reasoning/{positive,negative,disputed}/
RS-CMP-016 positive 分层（10 案例）
RS-CMP-017 negative 分层（8 案例）
RS-CMP-018 disputed 分层（5 案例）
RS-CMP-019 Golden 完备性（manifest 配额/字段/数量 + 分层文件对齐）
RS-CMP-020 全量回归锚（V0.1/V0.2/V0.3 语义零破坏 + inferred→asserted 永禁）
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_kb.evidence_core.assertions import AssertionStore, AssertionValidator
from agent_kb.evidence_core import EvidenceStore
from agent_kb.evidence_core.state_machine import validate_transition
from agent_kb.reasoning import (
    BuiltinRuleReasoner,
    InferenceGovernanceService,
    ReasoningContext,
    ReasoningEngine,
    ReasoningRunRepository,
)
from agent_kb.reasoning.models import canonical_json

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "v04_reasoning"
MANIFEST = json.loads((GOLDEN / "cases.json").read_text(encoding="utf-8"))


def _mk_evidence(db):
    db.execute("INSERT OR IGNORE INTO akb_sources (source_id, source_type, name)"
               " VALUES ('gd', 'document', 'GD')")
    db.execute("INSERT OR IGNORE INTO akb_documents (document_id, source_id, version,"
               " content_hash, ingested_at) VALUES ('dgd', 'gd', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    return EvidenceStore(db).create(document_id="dgd", content="Golden 锚证据。",
                                    extraction_method="t").evidence_id


def _seed(db, case):
    """按 case.seed_assertions 建 parent 断言；返回 (made, eid, engine, gov, store)。"""
    store = AssertionStore(db)
    eid = _mk_evidence(db)
    made = {}
    for s in case["seed_assertions"]:
        if "key" not in s:
            continue
        made[s["key"]] = store.create_candidate(
            subject_ref=s["subject_ref"], predicate_ref=s["predicate_ref"],
            object={"kind": "literal", "value": s["value"]}, assertion_type="extracted",
            ontology_scope="test", actor_id="system:seed",
            confidence=s.get("confidence", 0.9), evidence_refs=[eid])
    eng = ReasoningEngine(db, provider=BuiltinRuleReasoner())
    gov = InferenceGovernanceService(db, store)
    return made, eid, eng, gov, store


def _parent_ids(made, case):
    return [made[s["key"]].assertion_id for s in case["seed_assertions"]
            if "key" in s and s["key"] in made]


def _run(db, case, eng):
    ctx = ReasoningContext("test", max_depth=case["expectation"].get(
        "_max_depth", 8)) if "max_depth" in case["expectation"] else ReasoningContext("test")
    if "max_depth" in case["expectation"]:
        ctx = ReasoningContext("test", max_depth=case["expectation"]["max_depth"])
    return eng.reason(_parent_ids(_seed_cache["made"], case),
                      actor_id="system:reasoner", context=ctx)


_seed_cache = {}


def _execute(db, case):
    """执行单个 golden case（seed → reason → 附加动作），返回 context dict。"""
    made, eid, eng, gov, store = _seed(db, case)
    _seed_cache["made"] = made
    exp = case["expectation"]
    ctx = ReasoningContext("test")
    if "max_depth" in exp:
        ctx = ReasoningContext("test", max_depth=exp["max_depth"])
    r = eng.reason(_parent_ids(made, case), actor_id="system:reasoner", context=ctx)
    out = {"r": r, "made": made, "gov": gov, "store": store, "eid": eid, "db": db}
    # 附加治理动作（disputed/负例面）
    if r["assertions"] and exp.get("promote_asserted"):
        inf = r["assertions"][0]
        with pytest.raises(ValueError, match=exp["error_contains"]):
            gov.transition(assertion_id=inf.assertion_id, new_status="asserted",
                           actor_id="human:reviewer", reason="attempt")
    if r["assertions"] and exp.get("govern_non_human"):
        inf = r["assertions"][0]
        with pytest.raises(ValueError, match=exp["error"]):
            gov.validate_inferred(assertion_id=inf.assertion_id,
                                  actor_id="system:validator", reason="auto")
    if r["assertions"] and exp.get("govern_no_reason"):
        inf = r["assertions"][0]
        with pytest.raises(ValueError, match=exp["error"]):
            gov.validate_inferred(assertion_id=inf.assertion_id,
                                  actor_id="human:reviewer", reason="")
    if r["assertions"] and exp.get("audit_actions"):
        inf = r["assertions"][0]
        gov.validate_inferred(assertion_id=inf.assertion_id, actor_id="human:reviewer",
                              reason="golden")
        if "transition" in exp["audit_actions"]:
            gov.transition(assertion_id=inf.assertion_id, new_status="disputed",
                           actor_id="human:reviewer", reason="golden-dispute")
        if "transition-rejected" in exp["audit_actions"]:
            with pytest.raises(ValueError):
                gov.transition(assertion_id=inf.assertion_id, new_status="asserted",
                               actor_id="human:reviewer", reason="golden-illegal")
    if r["assertions"] and exp.get("parent_dispute"):
        inf_id = r["assertions"][0].assertion_id
        parent = next(iter(made.values()))
        AssertionValidator(db).validate(assertion_id=parent.assertion_id,
                                        actor_id="system:validator")
        store.transition(assertion_id=parent.assertion_id, new_status="disputed",
                         actor_id="human:tester", reason="golden")
    if r["assertions"] and exp.get("dispute_after_validate"):
        inf = r["assertions"][0]
        gov.validate_inferred(assertion_id=inf.assertion_id, actor_id="human:reviewer",
                              reason="golden")
        gov.transition(assertion_id=inf.assertion_id, new_status="disputed",
                       actor_id="human:reviewer", reason="golden")
    return out


def _assert_expectation(db, case, out):
    exp = case["expectation"]
    r = out["r"]
    if "error" in exp and not exp.get("promote_asserted") \
            and not exp.get("govern_non_human") and not exp.get("govern_no_reason"):
        # govern 类错误已在 _execute 的 pytest.raises 行为级验证（ValueError 路径）；
        # engine-level error 检查仅用于 parent-not-found 等 reason() 返回面
        assert any(exp["error"] in e for e in r["errors"]), case["case_id"]
    if exp.get("run_status") == "failed":
        from agent_kb.reasoning import ReasoningRunRepository
        snap = ReasoningRunRepository(db).get(r["run_id"])
        assert snap["status"] == "failed", case["case_id"]
    n = len(r["assertions"])
    if "candidates" in exp:
        assert n == exp["candidates"], case["case_id"]
    if "candidates_min" in exp:
        assert n >= exp["candidates_min"], case["case_id"]
    if "candidates_max" in exp:
        assert n <= exp["candidates_max"], case["case_id"]
    if "warnings_min" in exp:
        assert len(r["warnings"]) >= exp["warnings_min"], case["case_id"]
    if "rule_refs" in exp:
        got = {a.derivation["rule_ref"].split("@")[0] for a in r["assertions"]}
        assert set(exp["rule_refs"]) <= got, case["case_id"]
    if "expect_triple" in exp:
        s, p, v = exp["expect_triple"]
        assert any(a.subject_ref == s and a.predicate_ref == p
                   and a.object.get("value") == v for a in r["assertions"]), case["case_id"]
    if "expect_subject" in exp:
        assert any(a.subject_ref == exp["expect_subject"]
                   for a in r["assertions"]), case["case_id"]
    if "confidence_between" in exp:
        lo, hi = exp["confidence_between"]
        assert all(a.confidence is not None and lo <= a.confidence <= hi
                   for a in r["assertions"]), case["case_id"]
    if "derivation_keys" in exp:
        for a in r["assertions"]:
            for k in exp["derivation_keys"]:
                assert a.derivation.get(k), (case["case_id"], k)
    if exp.get("provenance_run"):
        a = r["assertions"][0]
        assert a.derivation.get("reasoning_run_id") == r["run_id"]
        rows = list(db.execute("SELECT 1 FROM akb_provenance WHERE activity='infer'"))
        assert rows, case["case_id"]
    if exp.get("disputed_value"):
        assert any(a.object.get("value") == exp["disputed_value"]
                   for a in r["assertions"]), case["case_id"]
    if "audit_actions" in exp:
        inf_id = r["assertions"][0].assertion_id
        trail = out["gov"].audit_trail(inf_id)
        assert set(exp["audit_actions"]) <= {t["action"] for t in trail}, case["case_id"]
    if exp.get("child_not_invalidated"):
        inf_id = r["assertions"][0].assertion_id
        row = db.execute("SELECT status FROM akb_assertions WHERE assertion_id=?",
                         (inf_id,)).fetchone()
        assert row["status"] in ("candidate", "validated"), case["case_id"]
    if exp.get("trace_keeps_parents"):
        from agent_kb.reasoning import InferenceTraceService
        tr = InferenceTraceService(db).trace(r["assertions"][0].assertion_id)
        assert tr["parents"], case["case_id"]
    # 通用不变量：inferred 恒 candidate + asserted 迁移硬门
    for a in r["assertions"]:
        assert a.status == "candidate" and a.assertion_type == "inferred"
        v = validate_transition(current_status="candidate", new_status="asserted",
                                assertion_type="inferred", actor_id="human:reviewer",
                                evidence_count=1)
        assert any("E-ILLEGAL-TRANSITION" in x for x in v)


def test_rs_cmp_016_golden_positive():
    """RS-CMP-016：positive 分层——全部案例行为级执行并通过 expectation。"""
    cases = [c for c in MANIFEST["cases"] if c["category"] == "positive"]
    assert len(cases) == MANIFEST["counts"]["positive"] == 10
    con = pytest.importorskip("sqlite3")
    for case in cases:
        db = con.connect(":memory:", isolation_level=None)
        db.row_factory = con.Row
        from agent_kb.storage.migrations import SchemaMigrator
        SchemaMigrator(db).migrate()
        try:
            out = _execute(db, case)
            _assert_expectation(db, case, out)
        finally:
            db.close()


def test_rs_cmp_017_golden_negative():
    """RS-CMP-017：negative 分层——拒绝/隔离/边界全部行为级验证。"""
    cases = [c for c in MANIFEST["cases"] if c["category"] == "negative"]
    assert len(cases) == MANIFEST["counts"]["negative"] == 8
    con = pytest.importorskip("sqlite3")
    for case in cases:
        db = con.connect(":memory:", isolation_level=None)
        db.row_factory = con.Row
        from agent_kb.storage.migrations import SchemaMigrator
        SchemaMigrator(db).migrate()
        try:
            if case["case_id"] == "RG-011":
                # ghost parent：直接引用不存在 id
                eng = ReasoningEngine(db, provider=BuiltinRuleReasoner())
                r = eng.reason(["ghost-assertion-id"], actor_id="system:reasoner",
                               context=ReasoningContext("test"))
                assert not r["ok"] and any("E-V04-PARENT-NOT-FOUND" in e
                                           for e in r["errors"])
                continue
            if case["case_id"] == "RG-012":
                # provider crash 场景
                _mk_evidence(db)
                store = AssertionStore(db)
                p = store.create_candidate(
                    subject_ref="A", predicate_ref="before",
                    object={"kind": "literal", "value": "B"}, assertion_type="extracted",
                    ontology_scope="test", actor_id="system:seed", confidence=0.9)
                class Crash:
                    def reasoner_id(self):
                        return "crash"
                    def rule_version(self):
                        return "v0"
                    def infer(self, parents, ctx):
                        raise RuntimeError("crash")
                eng = ReasoningEngine(db, provider=Crash())
                with pytest.raises(RuntimeError):
                    eng.reason([p.assertion_id], actor_id="system:reasoner",
                               context=ReasoningContext("test"))
                snap = ReasoningRunRepository(db).get(
                    list(db.execute("SELECT run_id FROM akb_reasoning_runs"
                                    " WHERE status='failed'"))[0]["run_id"])
                assert snap["status"] == "failed"
                continue
            if case["case_id"] == "RG-013":
                # malformed provider（缺 rule_ref/snapshot 提案）
                made = _seed(db, case)[0]
                pids = _parent_ids(made, case)
                from agent_kb.reasoning.models import InferredProposal
                class BadProvider:
                    def reasoner_id(self):
                        return "bad"
                    def rule_version(self):
                        return "v0"
                    def infer(self, parents, ctx):
                        return [InferredProposal(
                            proposal_id="inf_0001", subject_ref="A",
                            predicate_ref="before",
                            object={"kind": "literal", "value": "C"},
                            rule_ref="", parent_assertions=pids,
                            reasoner_id="bad", rule_input_snapshot="")]
                eng = ReasoningEngine(db, provider=BadProvider())
                r = eng.reason(pids, actor_id="system:reasoner",
                               context=ReasoningContext("test"))
                assert not r["assertions"] and r["warnings"]
                continue
            out = _execute(db, case)
            _assert_expectation(db, case, out)
        finally:
            db.close()


def test_rs_cmp_018_golden_disputed():
    """RS-CMP-018：disputed 分层——矛盾显式化 + 治理通道行为级验证。"""
    cases = [c for c in MANIFEST["cases"] if c["category"] == "disputed"]
    assert len(cases) == MANIFEST["counts"]["disputed"] == 5
    con = pytest.importorskip("sqlite3")
    for case in cases:
        db = con.connect(":memory:", isolation_level=None)
        db.row_factory = con.Row
        from agent_kb.storage.migrations import SchemaMigrator
        SchemaMigrator(db).migrate()
        try:
            out = _execute(db, case)
            _assert_expectation(db, case, out)
        finally:
            db.close()


def test_rs_cmp_019_golden_completeness():
    """RS-CMP-019：Golden 完备性——manifest 配额/数量/必填字段 + 分层文件对齐。"""
    assert MANIFEST["total"] == 23
    assert MANIFEST["counts"] == {"positive": 10, "negative": 8, "disputed": 5}
    required = {"case_id", "category", "description", "seed_assertions", "expectation"}
    seen = set()
    for c in MANIFEST["cases"]:
        assert required <= set(c), c.get("case_id")
        assert c["case_id"] not in seen
        seen.add(c["case_id"])
    for cat in ("positive", "negative", "disputed"):
        files = {p.stem for p in (GOLDEN / cat).glob("*.json")}
        manifest_ids = {c["case_id"] for c in MANIFEST["cases"] if c["category"] == cat}
        assert files == manifest_ids, cat


def test_rs_cmp_020_regression_anchors():
    """RS-CMP-020：V0.1/V0.2/V0.3 语义零破坏 + V0.4 治理硬门（跨 golden 抽样锚）。"""
    con = pytest.importorskip("sqlite3")
    db = con.connect(":memory:", isolation_level=None)
    db.row_factory = con.Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(db).migrate()
    try:
        # V0.2 compile 幂等锚
        eid = _mk_evidence(db)
        from agent_kb.evidence_core.compilation import SemanticCompiler
        comp = SemanticCompiler(db)
        # V0.2 compile 需要真实 evidence 内容——直接取 created evidence
        from agent_kb.evidence_core import EvidenceStore
        row = db.execute("SELECT evidence_id FROM akb_evidence LIMIT 1").fetchone()
        c1 = comp.compile(row["evidence_id"], actor_id="system:compiler")
        c2 = comp.compile(row["evidence_id"], actor_id="system:compiler")
        # V0.2 幂等锚：二次 compile 命中既有 run（或语义产物全等）
        assert c2.idempotent_hit or [a.assertion_id for a in c1.assertions] == \
            [a.assertion_id for a in c2.assertions]
        # V0.3 synthesis 锚：两条同主题参数文本（R-01 relation 面）
        ev0 = EvidenceStore(db).create(document_id="dgd",
                                       content="OBC 额定输入电压 265V。",
                                       extraction_method="t")
        comp.compile(ev0.evidence_id, actor_id="system:compiler")
        ev2 = EvidenceStore(db).create(document_id="dgd",
                                       content="OBC 额定输入电压是 265V。",
                                       extraction_method="t")
        comp.compile(ev2.evidence_id, actor_id="system:compiler")
        from agent_kb.evidence_core.synthesis import SynthesisEngine
        sr = SynthesisEngine(db).synthesize(
            [ev0.evidence_id, ev2.evidence_id], actor_id="system:synth")
        assert sr["assertions"]
        # V0.4 治理硬门锚：inferred→asserted 拒绝（跨层不变）
        eng = ReasoningEngine(db, provider=BuiltinRuleReasoner())
        m2, _eid2, _eng2, _gov2, _store2 = _seed(db, MANIFEST["cases"][1])
        rr = eng.reason([m2["ab"].assertion_id, m2["bc"].assertion_id],
                        actor_id="system:reasoner", context=ReasoningContext("test"))
        assert rr["assertions"]
        v = validate_transition(current_status="candidate", new_status="asserted",
                                assertion_type="inferred", actor_id="human:reviewer",
                                evidence_count=1)
        assert any("E-ILLEGAL-TRANSITION" in x for x in v)
    finally:
        db.close()