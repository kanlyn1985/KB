# -*- coding: utf-8 -*-
"""RP-CMP-001..010（AKB-V07-IMPL-002：RulePackage Runtime acceptance）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.domains.runtime import DomainPackRuntime
from agent_kb.domains.schema import (
    DomainPack,
    ObjectTypeSpec,
    RelationTypeSpec,
)
from agent_kb.rules import (
    PatternRuleProvider,
    RulePackage,
    RulePackageError,
    RulePackageRuntime,
    RuleSpec,
)
from agent_kb.reasoning import (
    BuiltinRuleReasoner,
    ReasoningContext as V04Context,
    ReasoningEngine,
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
def domain_runtime(db):
    return DomainPackRuntime(db)


def _pack(domain_id="industrial", version="1.0.0") -> DomainPack:
    return DomainPack(
        domain_id=domain_id, name="Pack", version=version,
        object_types={"Equipment": ObjectTypeSpec(name="Equipment"),
                      "Step": ObjectTypeSpec(name="Step")},
        relation_types={"before": RelationTypeSpec(
            name="before", source_types=["Step"], target_types=["Step"])},
        terminology={})


def _rule_package(package_id="flow-rules", version="1.0.0",
                  bindings=("industrial@1.0.0",), rule_version="1.0") -> RulePackage:
    return RulePackage(
        package_id=package_id, version=version,
        rules=(RuleSpec(
            rule_id="R-before-chain", rule_version=rule_version,
            rule_type="transitive",
            input_pattern={"predicates": ["before", "before"]},
            output_pattern={"predicate": "before", "subject_from": "first"},
            constraints={"max_expansion": 64}),
            RuleSpec(
            rule_id="R-param-equiv", rule_version=rule_version,
            rule_type="corroboration",
            input_pattern={"predicates": ["has_parameter"]},
            output_pattern={"predicate": "has_parameter"}),
        ),
        domain_bindings=bindings)


def test_rp_cmp_001_rule_package_load(db, domain_runtime):
    """RP-CMP-001：rule package load——注册 → RegisteredPackage（ref/provider）。"""
    domain_runtime.load_runtime_pack(_pack())
    rt = RulePackageRuntime(db)
    reg = rt.register(_rule_package(), domain_runtime=domain_runtime)
    assert reg.package_ref.startswith("rlp_")
    assert isinstance(reg.provider, PatternRuleProvider)
    assert reg.provider.reasoner_id() == "rulepkg:flow-rules"
    assert reg.provider.rule_version() == "1.0.0"


def test_rp_cmp_002_schema_validation(db, domain_runtime):
    """RP-CMP-002：schema validation——空 id/version/规则/谓词/未知类型全拒绝。"""
    domain_runtime.load_runtime_pack(_pack())
    rt = RulePackageRuntime(db)
    with pytest.raises(RulePackageError, match="E-V07-RULE-INVALID"):
        rt.register(_rule_package(package_id=" "), domain_runtime=domain_runtime)
    with pytest.raises(RulePackageError, match="E-V07-RULE-INVALID"):
        rt.register(_rule_package(version=" "), domain_runtime=domain_runtime)
    empty = RulePackage(package_id="p2", version="1.0", rules=(),
                        domain_bindings=("industrial@1.0.0",))
    with pytest.raises(RulePackageError, match="E-V07-RULE-INVALID"):
        rt.register(empty, domain_runtime=domain_runtime)
    nopred = RulePackage(
        package_id="p3", version="1.0",
        rules=(RuleSpec(rule_id="r1", rule_version="1.0", rule_type="transitive",
                        input_pattern={}, output_pattern={}),),
        domain_bindings=("industrial@1.0.0",))
    with pytest.raises(RulePackageError, match="E-V07-RULE-INVALID"):
        rt.register(nopred, domain_runtime=domain_runtime)


def test_rp_cmp_003_deterministic_rule_package_id(db, domain_runtime):
    """RP-CMP-003：deterministic rule_package_id——跨实例/重复注册全等。"""
    domain_runtime.load_runtime_pack(_pack())
    rt1 = RulePackageRuntime(db)
    reg1 = rt1.register(_rule_package(), domain_runtime=domain_runtime)
    reg2 = rt1.register(_rule_package(), domain_runtime=domain_runtime)  # 幂等
    assert reg1.package_ref == reg2.package_ref
    con2 = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con2.row_factory = pytest.importorskip("sqlite3").Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con2).migrate()
    dr2 = DomainPackRuntime(con2)
    dr2.load_runtime_pack(_pack())
    reg3 = RulePackageRuntime(con2).register(_rule_package(), domain_runtime=dr2)
    assert reg3.package_ref == reg1.package_ref
    con2.close()


def test_rp_cmp_004_version_conflict_handling(db, domain_runtime):
    """RP-CMP-004：version conflict——同包多版本共存 + 最新语义 + 幂等零重复审计。"""
    domain_runtime.load_runtime_pack(_pack())
    rt = RulePackageRuntime(db)
    rt.register(_rule_package(version="1.0.0"), domain_runtime=domain_runtime)
    rt.register(_rule_package(version="2.0.0"), domain_runtime=domain_runtime)
    assert rt.get_package("flow-rules").package.version == "2.0.0"
    assert rt.get_package("flow-rules", version="1.0.0").package.version == "1.0.0"
    # 重复注册零重复审计
    rt.register(_rule_package(version="2.0.0"), domain_runtime=domain_runtime)
    n = db.execute("SELECT COUNT(*) c FROM akb_provenance"
                   " WHERE activity='graph:rule-load'").fetchone()["c"]
    assert n == 2


def test_rp_cmp_005_invalid_rule_reject(db, domain_runtime):
    """RP-CMP-005：invalid rule reject——空 rule_id/version/未知 rule_type 拒绝。"""
    domain_runtime.load_runtime_pack(_pack())
    rt = RulePackageRuntime(db)
    bad1 = RulePackage(package_id="b1", version="1.0",
                       rules=(RuleSpec(rule_id=" ", rule_version="1.0",
                                       rule_type="transitive",
                                       input_pattern={"predicates": ["before"]},
                                       output_pattern={}),),
                       domain_bindings=("industrial@1.0.0",))
    with pytest.raises(RulePackageError, match="E-V07-RULE-INVALID"):
        rt.register(bad1, domain_runtime=domain_runtime)
    bad2 = RulePackage(package_id="b2", version="1.0",
                       rules=(RuleSpec(rule_id="r", rule_version="1.0",
                                       rule_type="teleport",
                                       input_pattern={"predicates": ["before"]},
                                       output_pattern={}),),
                       domain_bindings=("industrial@1.0.0",))
    with pytest.raises(RulePackageError, match="E-V07-RULE-INVALID"):
        rt.register(bad2, domain_runtime=domain_runtime)


def test_rp_cmp_006_domainpack_binding_validation(db, domain_runtime):
    """RP-CMP-006：DomainPack binding validation——未加载域绑定 fail-close；
    合法绑定通过；坏格式拒绝。"""
    rt = RulePackageRuntime(db)
    with pytest.raises(RulePackageError, match="E-V07-DOMAIN-NOT-LOADED"):
        rt.register(_rule_package(), domain_runtime=domain_runtime)  # 未加载
    domain_runtime.load_runtime_pack(_pack())
    reg = rt.register(_rule_package(), domain_runtime=domain_runtime)
    assert reg.package_ref.startswith("rlp_")
    with pytest.raises(RulePackageError, match="E-V07-RULE-INVALID"):
        rt.register(_rule_package(bindings=("badformat",)),
                    domain_runtime=domain_runtime)


def test_rp_cmp_007_provenance_rule_load_audit(db, domain_runtime):
    """RP-CMP-007：provenance rule-load audit——graph:rule-load 落
    akb_provenance（package_ref/rules/bindings）。"""
    domain_runtime.load_runtime_pack(_pack())
    RulePackageRuntime(db).register(_rule_package(), domain_runtime=domain_runtime)
    rows = [dict(x) for x in db.execute(
        "SELECT * FROM akb_provenance WHERE activity='graph:rule-load'")]
    assert len(rows) == 1
    m = json.loads(rows[0]["metadata_json"])
    assert m["package_ids"] == ["flow-rules"] and m["version"] == "1.0.0"
    assert m["package_ref"].startswith("rlp_")
    assert "R-before-chain" in m["rules"]
    assert m["domain_bindings"] == ["industrial@1.0.0"]


def test_rp_cmp_008_reasoning_integration(db, domain_runtime):
    """RP-CMP-008：reasoning integration——RulePackage provider 注入 V0.4 引擎
    （经 V0.6 orchestrator）产候选；候选恒 candidate；governance 边界不变。"""
    from agent_kb.evidence_core import EvidenceStore
    from agent_kb.evidence_core.assertions import AssertionStore
    from agent_kb.kgraph import (
        GraphContextBuilder,
        GraphPersistenceService,
        GraphProjectionService,
        GraphQueryService,
    )
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('rp', 'document', 'RP')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version,"
               " content_hash, ingested_at) VALUES ('drp', 'rp', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    eid = EvidenceStore(db).create(document_id="drp",
                                   content="流程 T1 先于流程 T2 执行。",
                                   extraction_method="t").evidence_id
    st = AssertionStore(db)
    ab = st.create_candidate(subject_ref="T1", predicate_ref="before",
                             object={"kind": "literal", "value": "T2"},
                             assertion_type="extracted", ontology_scope="test",
                             actor_id="system:seed", confidence=0.9,
                             evidence_refs=[eid])
    bc = st.create_candidate(subject_ref="T2", predicate_ref="before",
                             object={"kind": "literal", "value": "T3"},
                             assertion_type="extracted", ontology_scope="test",
                             actor_id="system:seed", confidence=0.9,
                             evidence_refs=[eid])
    GraphPersistenceService(db).persist(GraphProjectionService().process(db))
    # 注册规则包 + provider 注入 V0.4 引擎（单一引擎原则——只换 provider）
    domain_runtime.load_runtime_pack(_pack())
    reg = RulePackageRuntime(db).register(_rule_package(),
                                          domain_runtime=domain_runtime)
    engine = ReasoningEngine(db, provider=reg.provider)   # 注入，非新建语义
    ctx = GraphContextBuilder().build(
        db, root_entity=next(n.node_id for n in
                             GraphQueryService(db).query_nodes(
                                 node_type="entity", limit=1000)
                             if n.payload.get("canonical_form") in ("T1", "T2")))
    from agent_kb.kgraph import GraphReasoningOrchestrator
    orch = GraphReasoningOrchestrator(db, engine=engine)
    r = orch.run(ctx)
    assert r["candidates"], "package rules must yield candidates"
    for a in r["candidates"]:
        row = db.execute("SELECT assertion_type, status FROM akb_assertions"
                         " WHERE assertion_id=?", (a.assertion_id,)).fetchone()
        assert row["assertion_type"] == "inferred" and row["status"] == "candidate"
        assert a.derivation["reasoner_id"] == "rulepkg:flow-rules"
        assert a.derivation["rule_ref"].startswith("R-before-chain@")
    # 候选不被 orchestrator/pack 晋升
    n = db.execute("SELECT COUNT(*) c FROM akb_assertions WHERE assertion_type="
                   "'inferred' AND status='asserted'").fetchone()["c"]
    assert n == 0


def test_rp_cmp_009_rule_ordering_determinism(db, domain_runtime):
    """RP-CMP-009：rule ordering determinism——provider infer 输出顺序确定
    （谓词池 assertion_id 排序 + 规则序）；双调用全等。"""
    domain_runtime.load_runtime_pack(_pack())
    reg = RulePackageRuntime(db).register(_rule_package(),
                                          domain_runtime=domain_runtime)
    prov = reg.provider

    class FakeA:
        def __init__(self, aid, pred, subj, obj_val):
            self.assertion_id = aid
            self.predicate_ref = pred
            self.subject_ref = subj
            self.object = {"kind": "literal", "value": obj_val}
            self.confidence = 0.9

    parents = [FakeA("ast_b", "before", "T2", "T3"),
               FakeA("ast_a", "before", "T1", "T2"),
               FakeA("ast_c", "has_parameter", "OBC", "265V")]
    p1 = prov.infer(parents, V04Context("test"))
    p2 = prov.infer(parents, V04Context("test"))
    assert [(x.proposal_id, tuple(x.parent_assertions)) for x in p1] == \
        [(x.proposal_id, tuple(x.parent_assertions)) for x in p2]
    # 乱序输入 → 同输出（池内排序保证）
    parents_rev = list(reversed(parents))
    p3 = prov.infer(parents_rev, V04Context("test"))
    assert [(x.proposal_id, tuple(x.parent_assertions)) for x in p1] == \
        [(x.proposal_id, tuple(x.parent_assertions)) for x in p3]


def test_rp_cmp_010_frozen_regression(db):
    """RP-CMP-010：frozen regression——V0.4 engine/V0.6 orchestrator/legacy 零触碰
    （源码审计 + API 面互斥）。"""
    import inspect
    import agent_kb.graph as legacy
    import agent_kb.kgraph.orchestrator as orch_mod
    import agent_kb.reasoning.engine as engine_mod
    # rules runtime 零出现在 frozen 模块（单向依赖）
    assert "rules" not in inspect.getsource(engine_mod)
    src_orch = inspect.getsource(orch_mod)
    assert "RulePackageRuntime" not in src_orch      # orchestrator 未感知 rules runtime
    for sym in ("RulePackageRuntime", "PatternRuleProvider"):
        assert not hasattr(legacy, sym)