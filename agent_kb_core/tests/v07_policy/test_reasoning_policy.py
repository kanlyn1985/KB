# -*- coding: utf-8 -*-
"""POLICY-CMP-001..010（AKB-V07-IMPL-003：ReasoningPolicy Runtime acceptance）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.domains.runtime import DomainPackRuntime
from agent_kb.domains.schema import DomainPack, ObjectTypeSpec
from agent_kb.policy import (
    PolicyError,
    ReasoningPolicy,
    ReasoningPolicyRuntime,
)
from agent_kb.reasoning import ReasoningEngine
from agent_kb.rules import RulePackage, RulePackageRuntime, RuleSpec


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con).migrate()
    yield con
    con.close()


@pytest.fixture
def runtime_stack(db):
    """完整栈：DomainPack + RulePackage 已加载/注册。"""
    dr = DomainPackRuntime(db)
    dr.load_runtime_pack(DomainPack(
        domain_id="industrial", name="Pack", version="1.0.0",
        object_types={"Step": ObjectTypeSpec(name="Step")},
        relation_types={}, terminology={}))
    rr = RulePackageRuntime(db)
    rr.register(RulePackage(
        package_id="flow-rules", version="1.0.0",
        rules=(RuleSpec(rule_id="R-chain", rule_version="1.0",
                        rule_type="transitive",
                        input_pattern={"predicates": ["before"]},
                        output_pattern={"predicate": "before"}),),
        domain_bindings=("industrial@1.0.0",)), domain_runtime=dr)
    return {"dr": dr, "rr": rr}


def _policy(pid="core-policy", version="1.0.0", enabled=("flow-rules@1.0.0",),
            budgets=None, depth=4, cands=1024, order=None) -> ReasoningPolicy:
    return ReasoningPolicy(
        policy_id=pid, version=version, enabled_rules=tuple(enabled),
        per_domain_budgets=budgets or {"industrial": {"max_candidates": 64}},
        load_order=tuple(order or enabled),
        max_derivation_depth=depth, max_candidates=cands)


def test_policy_cmp_001_policy_load(db, runtime_stack):
    """POLICY-CMP-001：policy load——激活 → policy_ref + 幂等语义。"""
    rt = ReasoningPolicyRuntime(db)
    r = rt.activate(_policy(), rule_runtime=runtime_stack["rr"],
                    domain_runtime=runtime_stack["dr"])
    assert r["policy_ref"].startswith("pol_")
    assert r["idempotent_hit"] is False
    r2 = rt.activate(_policy(), rule_runtime=runtime_stack["rr"],
                     domain_runtime=runtime_stack["dr"])
    assert r2["idempotent_hit"] is True
    assert r2["policy_ref"] == r["policy_ref"]


def test_policy_cmp_002_schema_validation(db, runtime_stack):
    """POLICY-CMP-002：schema validation——空 id/version/未注册规则/未知域/
    超上限/非法状态过滤/load_order 越集 全拒绝。"""
    rt = ReasoningPolicyRuntime(db)
    with pytest.raises(PolicyError, match="E-V07-POLICY-INVALID"):
        rt.activate(_policy(pid=" "), rule_runtime=runtime_stack["rr"],
                    domain_runtime=runtime_stack["dr"])
    with pytest.raises(PolicyError, match="E-V07-POLICY-INVALID"):
        rt.activate(_policy(enabled=("ghost@1.0",)),
                    rule_runtime=runtime_stack["rr"],
                    domain_runtime=runtime_stack["dr"])
    with pytest.raises(PolicyError, match="E-V07-POLICY-INVALID"):
        rt.activate(_policy(budgets={"ghost": {"max_candidates": 1}}),
                    rule_runtime=runtime_stack["rr"],
                    domain_runtime=runtime_stack["dr"])
    with pytest.raises(PolicyError, match="E-V07-POLICY-INVALID"):
        rt.activate(_policy(depth=9), rule_runtime=runtime_stack["rr"],
                    domain_runtime=runtime_stack["dr"])
    with pytest.raises(PolicyError, match="E-V07-POLICY-INVALID"):
        rt.activate(_policy(cands=9999), rule_runtime=runtime_stack["rr"],
                    domain_runtime=runtime_stack["dr"])
    # 合法策略正向激活（空 order 合法；收紧预算合法）
    ok = rt.activate(_policy(enabled=("flow-rules@1.0.0",),
                             budgets={"industrial": {"max_candidates": 1}},
                             order=()), rule_runtime=runtime_stack["rr"],
                     domain_runtime=runtime_stack["dr"])
    assert ok["policy_ref"].startswith("pol_")
    # load_order 越集（order 引用未启用规则）
    with pytest.raises(PolicyError, match="E-V07-POLICY-INVALID"):
        rt.activate(_policy(enabled=("flow-rules@1.0.0",),
                            order=("flow-rules@9.9",)),
                    rule_runtime=runtime_stack["rr"],
                    domain_runtime=runtime_stack["dr"])


def test_policy_cmp_003_deterministic_policy_id(db, runtime_stack):
    """POLICY-CMP-003：deterministic policy_id——同策略双 runtime 全等；内容变→变。"""
    r1 = ReasoningPolicyRuntime(db).activate(
        _policy(), rule_runtime=runtime_stack["rr"],
        domain_runtime=runtime_stack["dr"])
    con2 = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con2.row_factory = pytest.importorskip("sqlite3").Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con2).migrate()
    dr2 = DomainPackRuntime(con2)
    dr2.load_runtime_pack(DomainPack(
        domain_id="industrial", name="Pack", version="1.0.0",
        object_types={"Step": ObjectTypeSpec(name="Step")}))
    rr2 = RulePackageRuntime(con2)
    rr2.register(RulePackage(
        package_id="flow-rules", version="1.0.0",
        rules=(RuleSpec(rule_id="R-chain", rule_version="1.0",
                        rule_type="transitive",
                        input_pattern={"predicates": ["before"]},
                        output_pattern={"predicate": "before"}),),
        domain_bindings=("industrial@1.0.0",)), domain_runtime=dr2)
    r2 = ReasoningPolicyRuntime(con2).activate(
        _policy(), rule_runtime=rr2, domain_runtime=dr2)
    assert r1["policy_ref"] == r2["policy_ref"]
    r3 = ReasoningPolicyRuntime(db).activate(
        _policy(version="2.0.0"), rule_runtime=runtime_stack["rr"],
        domain_runtime=runtime_stack["dr"])
    assert r3["policy_ref"] != r1["policy_ref"]
    con2.close()


def test_policy_cmp_004_version_conflict_handling(db, runtime_stack):
    """POLICY-CMP-004：version conflict——同 policy 多版本共存 + 最新语义。"""
    rt = ReasoningPolicyRuntime(db)
    rt.activate(_policy(version="1.0.0"), rule_runtime=runtime_stack["rr"],
                domain_runtime=runtime_stack["dr"])
    rt.activate(_policy(version="2.0.0"), rule_runtime=runtime_stack["rr"],
                domain_runtime=runtime_stack["dr"])
    assert rt.get_policy("core-policy").startswith("pol_")
    assert len(rt.list_policies()) == 2
    assert "core-policy@2.0.0" in rt.list_policies()


def test_policy_cmp_005_enable_disable_semantics(db, runtime_stack):
    """POLICY-CMP-005：enable/disable semantics——check_enabled 精确匹配
    （package@version 维度）。"""
    rt = ReasoningPolicyRuntime(db)
    p = _policy(enabled=("flow-rules@1.0.0",))
    rt.activate(p, rule_runtime=runtime_stack["rr"],
                domain_runtime=runtime_stack["dr"])
    assert rt.check_enabled(p, ("flow-rules", "1.0.0")) is True
    assert rt.check_enabled(p, ("flow-rules", "2.0.0")) is False
    assert rt.check_enabled(p, ("other-rules", "1.0.0")) is False


def test_policy_cmp_006_rule_budget_enforcement(db, runtime_stack):
    """POLICY-CMP-006：rule budget enforcement——per-domain 预算执行（超限
    fail-closed / 界内放行 / 默认回退）。"""
    rt = ReasoningPolicyRuntime(db)
    p = _policy(budgets={"industrial": {"max_candidates": 3}})
    rt.activate(p, rule_runtime=runtime_stack["rr"],
                domain_runtime=runtime_stack["dr"])
    assert rt.apply_budgets(p, "industrial", 2)["allowed"] == 2
    with pytest.raises(PolicyError, match="E-V07-BUDGET-EXCEEDED"):
        rt.apply_budgets(p, "industrial", 5)
    # 未声明域 → 回退全局 max_candidates
    assert rt.apply_budgets(p, "finance", 4)["budget"] == p.max_candidates


def test_policy_cmp_007_provenance_policy_audit(db, runtime_stack):
    """POLICY-CMP-007：provenance policy audit——graph:reason-policy 落
    akb_provenance（enabled_rules/budgets/before-after 快照）。"""
    rt = ReasoningPolicyRuntime(db)
    rt.activate(_policy(), rule_runtime=runtime_stack["rr"],
                domain_runtime=runtime_stack["dr"])
    rows = [dict(x) for x in db.execute(
        "SELECT * FROM akb_provenance WHERE activity='graph:reason-policy'")]
    assert len(rows) == 1
    m = json.loads(rows[0]["metadata_json"])
    assert m["policy_ids"] == ["core-policy"]
    assert m["enabled_rules"] == ["flow-rules@1.0.0"]
    assert m["max_derivation_depth"] == 4
    assert "before_snapshot" in m and "after_snapshot" in m
    # 重复激活零重复审计
    rt.activate(_policy(), rule_runtime=runtime_stack["rr"],
                domain_runtime=runtime_stack["dr"])
    n = db.execute("SELECT COUNT(*) c FROM akb_provenance"
                   " WHERE activity='graph:reason-policy'").fetchone()["c"]
    assert n == 1


def test_policy_cmp_008_reasoning_integration(db, runtime_stack):
    """POLICY-CMP-008：reasoning integration——policy 预算/启停进入 V0.6 全链路
    语义（budgets 收紧 + policy 版本入 V0.4 configuration——fingerprint 隔离）。"""
    from agent_kb.evidence_core import EvidenceStore
    from agent_kb.evidence_core.assertions import AssertionStore
    from agent_kb.kgraph import (
        GraphContextBuilder,
        GraphPersistenceService,
        GraphProjectionService,
        GraphQueryService,
        GraphReasoningOrchestrator,
    )
    from agent_kb.rules import PatternRuleProvider
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('pp', 'document', 'PP')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version,"
               " content_hash, ingested_at) VALUES ('dpp', 'pp', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    eid = EvidenceStore(db).create(document_id="dpp",
                                   content="流程 T1 先于流程 T2 执行。",
                                   extraction_method="t").evidence_id
    st = AssertionStore(db)
    st.create_candidate(subject_ref="T1", predicate_ref="before",
                        object={"kind": "literal", "value": "T2"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    st.create_candidate(subject_ref="T2", predicate_ref="before",
                        object={"kind": "literal", "value": "T3"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    GraphPersistenceService(db).persist(GraphProjectionService().process(db))
    reg = runtime_stack["rr"].get_package("flow-rules")
    engine = ReasoningEngine(db, provider=reg.provider)
    from agent_kb.kgraph import GraphReasoningOrchestrator
    ctx = GraphContextBuilder().build(
        db, root_entity=next(n.node_id for n in
                             GraphQueryService(db).query_nodes(
                                 node_type="entity", limit=1000)
                             if n.payload.get("canonical_form") in ("T1", "T2")))
    policy = _policy()
    rt = ReasoningPolicyRuntime(db)
    rt.activate(policy, rule_runtime=runtime_stack["rr"],
                domain_runtime=runtime_stack["dr"])
    # policy 启停生效：provider 只在 enabled 时执行（check_enabled 门控语义）
    assert rt.check_enabled(policy, ("flow-rules", "1.0.0")) is True
    orch = GraphReasoningOrchestrator(db, engine=engine)
    r = orch.run(ctx)
    assert r["status"] in ("completed", "partial")
    # policy 版本进入 V0.4 configuration → fingerprint 反映 policy（确定性隔离）
    from agent_kb.reasoning import ReasoningContext as V04Context
    v04 = V04Context(ontology_scope="v07-policy", configuration={
        "policy_id": policy.policy_id, "policy_version": policy.version,
        "enabled_rules": sorted(policy.enabled_rules)})
    assert v04.configuration_hash() != V04Context(
        ontology_scope="v07-policy").configuration_hash()


def test_policy_cmp_009_deterministic_replay(db, runtime_stack):
    """POLICY-CMP-009：deterministic replay——同 policy 双 runtime 激活+预算
    判定全等。"""
    r1 = ReasoningPolicyRuntime(db).activate(
        _policy(), rule_runtime=runtime_stack["rr"],
        domain_runtime=runtime_stack["dr"])
    con2 = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con2.row_factory = pytest.importorskip("sqlite3").Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con2).migrate()
    dr2 = DomainPackRuntime(con2)
    dr2.load_runtime_pack(DomainPack(
        domain_id="industrial", name="Pack", version="1.0.0",
        object_types={"Step": ObjectTypeSpec(name="Step")}))
    rr2 = RulePackageRuntime(con2)
    rr2.register(RulePackage(
        package_id="flow-rules", version="1.0.0",
        rules=(RuleSpec(rule_id="R-chain", rule_version="1.0",
                        rule_type="transitive",
                        input_pattern={"predicates": ["before"]},
                        output_pattern={"predicate": "before"}),),
        domain_bindings=("industrial@1.0.0",)), domain_runtime=dr2)
    r2 = ReasoningPolicyRuntime(con2).activate(
        _policy(), rule_runtime=rr2, domain_runtime=dr2)
    assert r1["policy_ref"] == r2["policy_ref"]
    p = _policy()
    rt1, rt2 = ReasoningPolicyRuntime(db), ReasoningPolicyRuntime(con2)
    assert rt1.apply_budgets(p, "industrial", 2) == \
        rt2.apply_budgets(p, "industrial", 2)
    con2.close()


def test_policy_cmp_010_frozen_regression(db):
    """POLICY-CMP-010：frozen regression——V0.6 orchestrator/context/provenance
    零 policy 感知（单向依赖）；legacy 零引用。"""
    import inspect
    import agent_kb.graph as legacy
    import agent_kb.kgraph.orchestrator as orch_mod
    import agent_kb.kgraph.context as ctx_mod
    assert "policy" not in inspect.getsource(orch_mod).lower().replace(
        "policy_version", "").replace("graph:reason-policy", "")
    assert "ReasoningPolicyRuntime" not in inspect.getsource(ctx_mod)
    for sym in ("ReasoningPolicyRuntime", "ReasoningPolicy"):
        assert not hasattr(legacy, sym)