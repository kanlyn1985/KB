# -*- coding: utf-8 -*-
"""RS-CMP-006..010（AKB-V04-IMPL-002：persistence/trace/回归）。

RS-CMP-006 determinism（run 快照级全等）
RS-CMP-007 idempotency（fingerprint 锚：零新候选/零新 run）
RS-CMP-008 provenance 链（infer 双链：run 表 + 断言级 + 反查）
RS-CMP-009 failure isolation（run failed / 提案隔离 / migration 幂等）
RS-CMP-010 V0.1/V0.2/V0.3 回归锚（既有语义零破坏：compile/synthesis 可用）
"""
from __future__ import annotations

import json

import pytest

from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.reasoning import (
    BuiltinRuleReasoner,
    ReasoningContext,
    ReasoningEngine,
    ReasoningRunRepository,
)
from agent_kb.reasoning.repository import InferenceTraceService


def _ids(r):
    return sorted(a.assertion_id for a in r["assertions"])


def _seed(db):
    store = AssertionStore(db)
    made = {}
    def mk(key, subj, pred, value, conf=0.9):
        made[key] = store.create_candidate(
            subject_ref=subj, predicate_ref=pred,
            object={"kind": "literal", "value": value}, assertion_type="extracted",
            ontology_scope="test", actor_id="system:seed", confidence=conf)
        return made[key]
    mk("ab", "A", "before", "B")
    mk("bc", "B", "before", "C")
    mk("same1", "OBC", "has_parameter", "265V", 0.9)
    mk("same2", "OBC", "has_parameter", "265V", 0.8)
    return made


def test_rs_cmp_006_determinism_run_snapshots(db):
    """RS-CMP-006：同输入双跑（不同 db）→ run 快照语义级全等（parent/reasoner/rules/
    proposals 结构）。"""
    snaps = []
    for _ in range(2):
        con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
        con.row_factory = pytest.importorskip("sqlite3").Row
        from agent_kb.storage.migrations import SchemaMigrator
        SchemaMigrator(con).migrate()
        made = _seed(con)
        eng = ReasoningEngine(con, provider=BuiltinRuleReasoner())
        r = eng.reason([made["ab"].assertion_id, made["bc"].assertion_id],
                       actor_id="system:reasoner", context=ReasoningContext("test"))
        snap = ReasoningRunRepository(con).get(r["run_id"])
        # 结构级全等（跨库 assertion_id 事件性字段不同——语义字段必须全等）
        snaps.append({
            "reasoner_id": snap["reasoner_id"],
            "rule_version": snap["rule_version"],
            "configuration_hash": snap["configuration_hash"],
            "status": snap["status"],
            "parent_count": len(json.loads(snap["parent_ids_json"])),
            "proposals": [(p["rule_ref"], p["subject_ref"], p["predicate_ref"])
                          for p in json.loads(snap["proposals_json"])],
        })
        con.close()
    assert snaps[0] == snaps[1]                     # 结构级全等（确定性）
    # 断言级语义全等
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con).migrate()
    made = _seed(con)
    eng = ReasoningEngine(con, provider=BuiltinRuleReasoner())
    r1 = eng.reason([made["ab"].assertion_id, made["bc"].assertion_id],
                    actor_id="system:reasoner", context=ReasoningContext("test"))
    r2 = eng.reason(list(reversed([made["ab"].assertion_id, made["bc"].assertion_id])),
                    actor_id="system:reasoner", context=ReasoningContext("test"))
    def sem(r):
        return [(a.subject_ref, a.predicate_ref, canonical_json(a.object),
                 a.derivation["rule_ref"], a.confidence) for a in r["assertions"]]
    from agent_kb.reasoning.models import canonical_json
    assert sem(r1) == sem(r2)                       # 逆序 parent → 语义等
    assert r1["fingerprint"] == r2["fingerprint"]


def test_rs_cmp_007_idempotency_fingerprint_anchor(db):
    """RS-CMP-007：同输入重放 → 锚命中（零新候选/零新 run/结果完整）。"""
    made = _seed(db)
    eng = ReasoningEngine(db, provider=BuiltinRuleReasoner())
    pids = [made["ab"].assertion_id, made["bc"].assertion_id]
    r1 = eng.reason(pids, actor_id="system:reasoner", context=ReasoningContext("test"))
    n1 = db.execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
    runs1 = db.execute("SELECT COUNT(*) c FROM akb_reasoning_runs").fetchone()["c"]
    r2 = eng.reason(pids, actor_id="system:reasoner", context=ReasoningContext("test"))
    assert r2.get("idempotent_hit") and r2["run_id"] == r1["run_id"]
    assert len(r2["assertions"]) == len(r1["assertions"])
    n2 = db.execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
    runs2 = db.execute("SELECT COUNT(*) c FROM akb_reasoning_runs").fetchone()["c"]
    assert n1 == n2 and runs1 == runs2              # 零新增
    # 逆序输入同锚
    r3 = eng.reason(list(reversed(pids)), actor_id="system:reasoner",
                    context=ReasoningContext("test"))
    assert r3.get("idempotent_hit") and r3["fingerprint"] == r1["fingerprint"]


def test_rs_cmp_008_provenance_dual_chain(db):
    """RS-CMP-008：双链持久化——run 表（parent/proposals/锚）+ 断言级 derivation.
    reasoning_run_id 反查 + provenance activity=infer。"""
    made = _seed(db)
    eng = ReasoningEngine(db, provider=BuiltinRuleReasoner())
    r = eng.reason([made["ab"].assertion_id, made["bc"].assertion_id],
                   actor_id="system:reasoner", context=ReasoningContext("test"))
    # run 表：canonical parent 序 + 状态 + proposals 快照
    snap = ReasoningRunRepository(db).get(r["run_id"])
    assert json.loads(snap["parent_ids_json"]) == sorted(
        [made["ab"].assertion_id, made["bc"].assertion_id])
    assert snap["status"] == "completed" and snap["fingerprint"] == r["fingerprint"]
    proposals = json.loads(snap["proposals_json"])
    assert proposals and all("rule_ref" in p for p in proposals)
    # 断言级：derivation.reasoning_run_id 可反查 run
    a = r["assertions"][0]
    assert a.derivation["reasoning_run_id"] == r["run_id"]
    # provenance activity=infer
    rows = list(db.execute(
        "SELECT inputs_json, metadata_json FROM akb_provenance WHERE activity='infer'"))
    assert rows and r["run_id"] is not None
    # trace：断言 → run → parents 完整
    tr = InferenceTraceService(db).trace(a.assertion_id)
    assert tr["assertion"]["assertion_id"] == a.assertion_id
    assert tr["parents"] and all(p["assertion"] for p in tr["parents"])
    assert {p["assertion"]["assertion_id"] for p in tr["parents"]} == {
        made["ab"].assertion_id, made["bc"].assertion_id}


def test_rs_cmp_009_failure_isolation_and_migration_idempotent(db):
    """RS-CMP-009：失败隔离（run failed 零候选）+ migration 14 幂等重复执行。"""
    made = _seed(db)
    before = db.execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
    # provider 崩溃 → run failed、零候选、既有产物零破坏
    class CrashProvider:
        def reasoner_id(self):
            return "crash"
        def rule_version(self):
            return "v0"
        def infer(self, parent_assertions, context):
            raise RuntimeError("provider crash")
    eng = ReasoningEngine(db, provider=CrashProvider())
    with pytest.raises(RuntimeError):
        eng.reason([made["ab"].assertion_id], actor_id="system:reasoner",
                   context=ReasoningContext("test"))
    after = db.execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
    assert before == after
    failed = list(db.execute("SELECT * FROM akb_reasoning_runs WHERE status='failed'"))
    assert failed and failed[0]["reasoner_id"] == "crash"
    # migration 14 幂等：重复 SchemaMigrator.migrate() 不炸不重复
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(db).migrate()
    SchemaMigrator(db).migrate()
    runs = db.execute("SELECT COUNT(*) c FROM akb_reasoning_runs").fetchone()["c"]
    assert runs == 1                                 # 表数据未受重复迁移影响


def test_rs_cmp_010_regression_anchors(db):
    """RS-CMP-010：V0.1/V0.2/V0.3 回归锚——既有语义零破坏（compile 幂等/synthesis
    可用/治理边界不变），inferred 永不自动 asserted。"""
    # V0.2 compile 锚
    from agent_kb.evidence_core import EvidenceStore
    from agent_kb.evidence_core.compilation import SemanticCompiler
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('rc', 'document', 'RC')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at) VALUES ('drc', 'rc', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    store = EvidenceStore(db)
    comp = SemanticCompiler(db)
    ev = store.create(document_id="drc", content="OBC 额定输入电压 265V。",
                      extraction_method="t")
    c1 = comp.compile(ev.evidence_id, actor_id="system:compiler")
    c2 = comp.compile(ev.evidence_id, actor_id="system:compiler")
    assert c2.idempotent_hit                          # V0.2 幂等不变
    # V0.3 synthesis 锚（第二 evidence 同主题）
    ev2 = store.create(document_id="drc", content="OBC 额定输入电压是 265V。",
                       extraction_method="t")
    comp.compile(ev2.evidence_id, actor_id="system:compiler")
    from agent_kb.evidence_core.synthesis import SynthesisEngine
    sr = SynthesisEngine(db).synthesize([ev.evidence_id, ev2.evidence_id],
                                        actor_id="system:synth")
    assert sr["assertions"]                           # synthesis 可用
    # V0.4 inferred 产物治理边界：恒 candidate，asserted 直写被触发器拦截
    eng = ReasoningEngine(db, provider=BuiltinRuleReasoner())
    rr = eng.reason([sr["assertions"][0].assertion_id], actor_id="system:reasoner",
                    context=ReasoningContext("test"))
    for a in rr["assertions"]:
        assert a.status == "candidate" and a.assertion_type == "inferred"
        from agent_kb.evidence_core.state_machine import validate_transition
        v = validate_transition(current_status="candidate", new_status="asserted",
                                assertion_type="inferred", actor_id="human:tester",
                                evidence_count=1)
        assert any("E-ILLEGAL-TRANSITION" in x for x in v)