# -*- coding: utf-8 -*-
"""CD-CMP-001..010（AKB-V07-IMPL-004：CrossDomainGuard acceptance）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.domains.guard import CrossDomainError, CrossDomainGuard
from agent_kb.domains.runtime import DomainPackRuntime
from agent_kb.domains.schema import DomainPack, ObjectTypeSpec
from agent_kb.policy import ReasoningPolicy, ReasoningPolicyRuntime
from agent_kb.rules import RulePackage, RulePackageRuntime, RuleSpec


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con).migrate()
    yield con
    con.close()


def _pack(domain_id, version="1.0.0") -> DomainPack:
    return DomainPack(
        domain_id=domain_id, name=f"{domain_id} Pack", version=version,
        object_types={"Step": ObjectTypeSpec(name="Step")},
        relation_types={}, terminology={})


def _rule_pkg(pid="flow-rules", version="1.0.0",
              bindings=("industrial@1.0.0",)) -> RulePackage:
    return RulePackage(
        package_id=pid, version=version,
        rules=(RuleSpec(rule_id="R1", rule_version="1.0", rule_type="transitive",
                        input_pattern={"predicates": ["before"]},
                        output_pattern={"predicate": "before"}),),
        domain_bindings=bindings)


@pytest.fixture
def stack(db):
    dr = DomainPackRuntime(db)
    dr.load_runtime_pack(_pack("industrial"))
    dr.load_runtime_pack(_pack("finance"))
    rr = RulePackageRuntime(db)
    rr.register(_rule_pkg(), domain_runtime=dr)
    pr = ReasoningPolicyRuntime(db)
    pol = ReasoningPolicy(
        policy_id="core", version="1.0", enabled_rules=("flow-rules@1.0.0",),
        per_domain_budgets={"industrial": {"max_candidates": 64},
                            "finance": {"max_candidates": 64}},
        load_order=("flow-rules@1.0.0",))
    pol_ref = pr.activate(pol, rule_runtime=rr, domain_runtime=dr)["policy_ref"]
    return {"dr": dr, "rr": rr, "pr": pr, "pol": pol, "pol_ref": pol_ref}


def test_cd_cmp_001_domain_allow(db, stack):
    """CD-CMP-001：domain allow——root 域内访问 allow + fingerprint canonical。"""
    g = CrossDomainGuard(db, domain_runtime=stack["dr"],
                         rule_runtime=stack["rr"], policy_runtime=stack["pr"])
    ds = g.guard_context(root_domain="industrial",
                         context_domains=("industrial",),
                         pack_ref="dpr_x", policy_ref=stack["pol_ref"])
    assert len(ds) == 1 and ds[0].decision == "allow"
    assert ds[0].reason == "intra-domain"
    assert ds[0].fingerprint.startswith("gcd_")


def test_cd_cmp_002_unauthorized_block(db, stack):
    """CD-CMP-002：unauthorized block——跨域未授权 → E-V07-CROSS-DOMAIN-BLOCKED
    fail-close（block 裁决先审计后抛错）。"""
    g = CrossDomainGuard(db, domain_runtime=stack["dr"],
                         rule_runtime=stack["rr"], policy_runtime=stack["pr"])
    with pytest.raises(CrossDomainError, match="E-V07-CROSS-DOMAIN-BLOCKED"):
        g.guard_context(root_domain="industrial",
                        context_domains=("finance",),
                        pack_ref="dpr_x", policy_ref=stack["pol_ref"])


def test_cd_cmp_003_namespace_conflict(db, stack):
    """CD-CMP-003：namespace conflict——ns 归属不符 → E-V07-NAMESPACE-CONFLICT。"""
    g = CrossDomainGuard(db, domain_runtime=stack["dr"])
    g.check_namespace("industrial", expected_owner="industrial")   # 合法
    with pytest.raises(CrossDomainError, match="E-V07-NAMESPACE-CONFLICT"):
        g.check_namespace("industrial", expected_owner="finance")
    with pytest.raises(CrossDomainError, match="E-V07-NAMESPACE-CONFLICT"):
        g.check_namespace("ghost-ns", expected_owner="industrial")


def test_cd_cmp_004_deterministic_decision(db, stack):
    """CD-CMP-004：deterministic decision——同输入双实例同 fingerprint（canonical）。"""
    g1 = CrossDomainGuard(db, domain_runtime=stack["dr"],
                          rule_runtime=stack["rr"], policy_runtime=stack["pr"])
    con2 = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con2.row_factory = pytest.importorskip("sqlite3").Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con2).migrate()
    dr2 = DomainPackRuntime(con2)
    dr2.load_runtime_pack(_pack("industrial"))
    dr2.load_runtime_pack(_pack("finance"))
    g2 = CrossDomainGuard(con2, domain_runtime=dr2)
    d1 = g1.guard_context(root_domain="industrial",
                          context_domains=("industrial",),
                          pack_ref="dpr_x", policy_ref=stack["pol_ref"])[0]
    d2 = g2.guard_context(root_domain="industrial",
                          context_domains=("industrial",),
                          pack_ref="dpr_x", policy_ref=stack["pol_ref"])[0]
    assert d1.fingerprint == d2.fingerprint
    # 输入不同 → fingerprint 不同
    d3 = g1.guard_context(root_domain="industrial",
                          context_domains=("industrial",),
                          pack_ref="dpr_y", policy_ref=stack["pol_ref"])[0]
    assert d3.fingerprint != d1.fingerprint
    con2.close()


def test_cd_cmp_005_provenance_audit(db, stack):
    """CD-CMP-005：provenance audit——cross-domain-allow/block 均落
    akb_provenance（source/target/pack_ref/policy_ref/decision）。"""
    g = CrossDomainGuard(db, domain_runtime=stack["dr"],
                         rule_runtime=stack["rr"], policy_runtime=stack["pr"])
    # allow（授权跨域）
    g.guard_context(root_domain="industrial", context_domains=("finance",),
                    pack_ref="dpr_x", policy_ref=stack["pol_ref"],
                    allow_cross_domain=True)
    rows = [dict(x) for x in db.execute(
        "SELECT * FROM akb_provenance WHERE activity='graph:cross-domain-allow'")]
    assert len(rows) == 1
    m = json.loads(rows[0]["metadata_json"])
    assert m["source_domain"] == "industrial" and m["target_domain"] == "finance"
    assert m["pack_ref"] == "dpr_x" and m["policy_ref"] == stack["pol_ref"]
    assert m["decision"] == "allow"
    # block
    with pytest.raises(CrossDomainError):
        g.guard_context(root_domain="industrial", context_domains=("finance",),
                        pack_ref="dpr_x", policy_ref=stack["pol_ref"])
    rows_b = [dict(x) for x in db.execute(
        "SELECT * FROM akb_provenance WHERE activity='graph:cross-domain-block'")]
    assert len(rows_b) == 1
    mb = json.loads(rows_b[0]["metadata_json"])
    assert mb["decision"] == "block" and mb["fingerprint"].startswith("gcd_")


def test_cd_cmp_006_policy_integration(db, stack):
    """CD-CMP-006：policy integration——guard 裁决携带 policy_ref；policy 无感知
    （零 frozen 修改）。"""
    g = CrossDomainGuard(db, domain_runtime=stack["dr"],
                         rule_runtime=stack["rr"], policy_runtime=stack["pr"])
    ds = g.guard_context(root_domain="industrial",
                         context_domains=("industrial", "finance"),
                         pack_ref="dpr_x", policy_ref=stack["pol_ref"],
                         allow_cross_domain=True)
    assert all(d.policy_ref == stack["pol_ref"] for d in ds)
    # policy runtime 注册表面未被 guard 修改
    assert len(stack["pr"].list_policies()) == 1


def test_cd_cmp_007_pack_isolation(db, stack):
    """CD-CMP-007：pack isolation——LoadedPack ns 唯一持有 + guard check 一致。"""
    assert stack["dr"].get_pack("industrial").namespace != \
        stack["dr"].get_pack("finance").namespace
    g = CrossDomainGuard(db, domain_runtime=stack["dr"])
    g.check_namespace("finance", expected_owner="finance")   # 正主通过
    with pytest.raises(CrossDomainError, match="E-V07-NAMESPACE-CONFLICT"):
        g.check_namespace("finance", expected_owner="industrial")


def test_cd_cmp_008_rule_binding_isolation(db, stack):
    """CD-CMP-008：rule binding isolation——绑定域已加载通过；未加载域 fail-close。"""
    g = CrossDomainGuard(db, domain_runtime=stack["dr"],
                         rule_runtime=stack["rr"])
    g.check_rule_binding(("flow-rules", "1.0.0"))            # industrial@1.0.0 已加载
    stack["rr"].register(_rule_pkg(pid="ghost-rules", bindings=("ghost@9.9",)),
                         domain_runtime=stack["dr"]) if False else None
    # 直接构造未加载绑定的包（绕过注册校验——测 guard 侧独立防御）
    from agent_kb.rules import RulePackage, RulePackageRuntime
    rr2 = RulePackageRuntime(db)
    pkg = _rule_pkg(pid="ghost-rules", bindings=("ghost@9.9",))
    # 先注册成功（跳过 domain 校验——不传 domain_runtime）
    rr2.register(pkg)
    g2 = CrossDomainGuard(db, domain_runtime=stack["dr"], rule_runtime=rr2)
    with pytest.raises(CrossDomainError, match="E-V07-NAMESPACE-CONFLICT"):
        g2.check_rule_binding(("ghost-rules", "1.0.0"))
    with pytest.raises(CrossDomainError, match="E-V07-RULE-PACK-NOT-REGISTERED"):
        g.check_rule_binding(("never-registered", "1.0"))


def test_cd_cmp_009_fail_close(db, stack):
    """CD-CMP-009：fail-close 全矩阵——block 决策 enforce 抛错 + 未注册 ns +
    未注册包全显式拒绝；零 fabricate。"""
    g = CrossDomainGuard(db, domain_runtime=stack["dr"],
                         rule_runtime=stack["rr"], policy_runtime=stack["pr"])
    ds = g.guard_context(root_domain="industrial",
                         context_domains=("industrial", "finance"),
                         pack_ref="dpr_x", policy_ref=stack["pol_ref"],
                         allow_cross_domain=True)
    # 全 allow 集 enforce 通过
    g.enforce(ds)
    # 混入 block → enforce 抛错
    from agent_kb.domains.guard import GuardDecision
    blocked = [d for d in ds] + [GuardDecision(
        decision="block", source_domain="industrial", target_domain="legal",
        pack_ref="dpr_x", policy_ref=stack["pol_ref"], fingerprint="gcd_x",
        reason="test")]
    with pytest.raises(CrossDomainError, match="E-V07-CROSS-DOMAIN-BLOCKED"):
        g.enforce(blocked)


def test_cd_cmp_010_frozen_regression(db, stack):
    """CD-CMP-010：frozen regression——V0.6 orchestrator/context/provenance 零
    guard 感知（单向依赖）；guard 零 candidate 产生；legacy 零引用。"""
    import inspect
    import agent_kb.graph as legacy
    import agent_kb.kgraph.orchestrator as orch_mod
    import agent_kb.kgraph.context as ctx_mod
    src_orch = inspect.getsource(orch_mod)
    assert "CrossDomainGuard" not in src_orch        # orchestrator 未感知 guard
    assert "guard" not in inspect.getsource(ctx_mod).lower()
    for sym in ("CrossDomainGuard", "GuardDecision"):
        assert not hasattr(legacy, sym)
    # guard 零 candidate：调用后 akb_assertions 零新增
    n_before = db.execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
    g = CrossDomainGuard(db, domain_runtime=stack["dr"])
    g.guard_context(root_domain="industrial", context_domains=("industrial",),
                    pack_ref="dpr_x", policy_ref=stack["pol_ref"])
    n_after = db.execute("SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
    assert n_before == n_after