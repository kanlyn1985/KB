# -*- coding: utf-8 -*-
"""V10-REGISTRY-CMP-001..012（AKB-V10-IMPL-003：Registry Snapshot Runtime）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.causal import (
    CausalProjectionRuntime,
    ScalePersistenceRuntime,
)
from agent_kb.domains.runtime import DomainPackRuntime
from agent_kb.domains.schema import DomainPack, ObjectTypeSpec
from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.policy import ReasoningPolicy, ReasoningPolicyRuntime
from agent_kb.rules import RulePackage, RulePackageRuntime, RuleSpec
from agent_kb.storage.migrations import SchemaMigrator
from agent_kb.storage.registry_snapshot import (
    RegistrySnapshotError,
    RegistrySnapshotRuntime,
    registry_snapshot_identity,
)
from agent_kb.storage.query import ScaleQueryRuntime


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(
        ":memory:", isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    SchemaMigrator(con).migrate()
    con.execute("INSERT INTO akb_sources (source_id, source_type, name)"
                " VALUES ('r10', 'document', 'R10')")
    con.execute("INSERT INTO akb_documents (document_id, source_id, version,"
                " content_hash, ingested_at) VALUES ('dr10', 'r10', '1.0',"
                " 'h', strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    ev = EvidenceStore(con).create(document_id="dr10", content="快照锚证据。",
                                   extraction_method="t")
    yield con, ev.evidence_id
    con.close()


import sqlite3


def _pack(source):
    return DomainPack(domain_id=source, name=f"P-{source}", version="1.0.0",
                      object_types={"Step": ObjectTypeSpec(name="Step")},
                      relation_types={}, terminology={})


def _seed_domain_registry(con):
    rt = DomainPackRuntime(con)
    for d in ("industrial", "finance"):
        rt.load_runtime_pack(_pack(d))
    return rt.registry


def _seed_rule_registry(con, eid):
    rt = RulePackageRuntime(con)
    for pid in ("flow", "hvac"):
        pkg = RulePackage(package_id=pid, version="1.0",
                          rules=(RuleSpec(rule_id="R1", rule_version="1",
                                          rule_type="transitive",
                                          input_pattern={"predicates":
                                                         ["before"]},
                                          output_pattern={"predicate":
                                                          "before"}),),
                          domain_bindings=("industrial@1.0.0",))
        rt.register(pkg)
    return rt.registry


def _seed_policy_registry(con):
    rt = ReasoningPolicyRuntime(con)
    for pol_id in ("core", "audit"):
        pol = ReasoningPolicy(policy_id=pol_id, version="1",
                              enabled_rules=("flow@1.0",),
                              per_domain_budgets={"industrial":
                                                  {"max_candidates": 8}},
                              load_order=("flow@1.0",))
        rt.activate(pol)
    return rt.registry


def test_v10_registry_cmp_001_snapshot_create(db):
    """V10-REGISTRY-CMP-001：snapshot create——domain registry 全字段。"""
    con, _ = db
    reg = _seed_domain_registry(con)
    s = RegistrySnapshotRuntime(con).create_snapshot(reg,
                                                     registry_type="domain_pack")
    assert s.snapshot_id.startswith("rgs_")
    assert s.registry_type == "domain_pack"
    assert s.schema_version == 1
    assert len(s.entries) == 2
    assert {e["entry_key"] for e in s.entries} == {
        "finance@1.0.0", "industrial@1.0.0"}
    assert len(s.fingerprint) == 16


def test_v10_registry_cmp_002_deterministic_snapshot_id(db):
    """V10-REGISTRY-CMP-002：deterministic snapshot_id——同状态跨实例全等。"""
    con, _ = db
    s1 = RegistrySnapshotRuntime(con).create_snapshot(
        _seed_domain_registry(con), registry_type="domain_pack")
    s2 = RegistrySnapshotRuntime(con).create_snapshot(
        _seed_domain_registry(con), registry_type="domain_pack")
    assert s1.snapshot_id == s2.snapshot_id
    assert s1.fingerprint == s2.fingerprint
    # 单元级复算
    kw = dict(registry_type="domain_pack", schema_version=1,
              entries=({"entry_key": "a@1", "content_ref": "r1",
                        "detail": ""},))
    assert registry_snapshot_identity(**kw) == registry_snapshot_identity(**kw)


def test_v10_registry_cmp_003_fingerprint_change_detection(db):
    """V10-REGISTRY-CMP-003：fingerprint change detection——注册新 pack →
    snapshot_id/fingerprint 变。"""
    con, _ = db
    rt = DomainPackRuntime(con)
    s1 = RegistrySnapshotRuntime(con).create_snapshot(
        dict(rt.registry), registry_type="domain_pack")
    rt.load_runtime_pack(_pack("industrial"))
    s2 = RegistrySnapshotRuntime(con).create_snapshot(
        dict(rt.registry), registry_type="domain_pack")
    assert s2.snapshot_id != s1.snapshot_id
    assert s2.fingerprint != s1.fingerprint


def test_v10_registry_cmp_004_canonical_ordering(db):
    """V10-REGISTRY-CMP-004：canonical ordering——entries 按 entry_key ASC
    （跨插入顺序）。"""
    con, _ = db
    rt = DomainPackRuntime(con)
    for d in ("zeta", "alpha", "mid"):
        rt.load_runtime_pack(_pack(d))
    s = RegistrySnapshotRuntime(con).create_snapshot(
        dict(rt.registry), registry_type="domain_pack")
    keys = [e["entry_key"] for e in s.entries]
    assert keys == sorted(keys)
    assert keys[0].startswith("alpha")


def test_v10_registry_cmp_005_immutable_object(db):
    """V10-REGISTRY-CMP-005：immutable object——frozen dataclass 赋值拒绝 +
    重复 create 零重复审计。"""
    con, _ = db
    s = RegistrySnapshotRuntime(con).create_snapshot(
        _seed_domain_registry(con), registry_type="domain_pack")
    with pytest.raises(Exception):
        s.fingerprint = "x"  # type: ignore[misc]
    n1 = con.execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                     " activity='graph:registry-snapshot-create'"
                     ).fetchone()["c"]
    RegistrySnapshotRuntime(con).create_snapshot(_seed_domain_registry(con),
                                                 registry_type="domain_pack")
    n2 = con.execute("SELECT COUNT(*) c FROM akb_provenance WHERE"
                     " activity='graph:registry-snapshot-create'"
                     ).fetchone()["c"]
    assert n1 == n2


def test_v10_registry_cmp_006_restore_snapshot(db):
    """V10-REGISTRY-CMP-006：restore snapshot——校验通过 + deterministic 载荷。"""
    con, _ = db
    s = RegistrySnapshotRuntime(con).create_snapshot(
        _seed_domain_registry(con), registry_type="domain_pack")
    r1 = RegistrySnapshotRuntime.restore_snapshot(s)
    r2 = RegistrySnapshotRuntime.restore_snapshot(s)
    assert r1 == r2
    assert r1["fingerprint"] == s.fingerprint
    assert [e["entry_key"] for e in r1["entries"]] == \
        sorted(e["entry_key"] for e in s.entries)


def test_v10_registry_cmp_007_invalid_fingerprint_fail_close(db):
    """V10-REGISTRY-CMP-007：invalid fingerprint fail-close——篡改 payload 拒绝。"""
    from dataclasses import replace
    con, _ = db
    s = RegistrySnapshotRuntime(con).create_snapshot(
        _seed_domain_registry(con), registry_type="domain_pack")
    tampered = replace(s, entries=s.entries + ({"entry_key": "evil@1",
                                                "content_ref": "x",
                                                "detail": ""},))
    with pytest.raises(RegistrySnapshotError,
                       match="E-V10-REGISTRY-INVALID"):
        RegistrySnapshotRuntime.restore_snapshot(tampered)


def test_v10_registry_cmp_008_invalid_schema_fail_close(db):
    """V10-REGISTRY-CMP-008：invalid schema fail-close——未知 schema_version/
    未知 registry_type/坏 id 全拒。"""
    con, _ = db
    s = RegistrySnapshotRuntime(con).create_snapshot(
        _seed_domain_registry(con), registry_type="domain_pack")
    from dataclasses import replace
    with pytest.raises(RegistrySnapshotError,
                       match="E-V10-REGISTRY-INVALID"):
        RegistrySnapshotRuntime.restore_snapshot(replace(s, schema_version=99))
    rt = RegistrySnapshotRuntime(con)
    with pytest.raises(RegistrySnapshotError,
                       match="E-V10-REGISTRY-INVALID"):
        rt.create_snapshot({}, registry_type="teleport")
    with pytest.raises(RegistrySnapshotError,
                       match="E-V10-REGISTRY-INVALID"):
        rt.get_snapshot("bad-id")


def test_v10_registry_cmp_009_provenance_audit(db):
    """V10-REGISTRY-CMP-009：provenance audit——graph:registry-snapshot-create
    落 akb_provenance（snapshot_id/registry_type/entries/fingerprint）。"""
    con, _ = db
    s = RegistrySnapshotRuntime(con).create_snapshot(
        _seed_domain_registry(con), registry_type="domain_pack")
    rows = [dict(x) for x in con.execute(
        "SELECT * FROM akb_provenance WHERE activity ="
        " 'graph:registry-snapshot-create'")]
    assert len(rows) == 1
    m = json.loads(rows[0]["metadata_json"])
    assert m["snapshot_id"] == s.snapshot_id
    assert m["registry_type"] == "domain_pack"
    assert m["fingerprint"] == s.fingerprint
    assert m["entry_count"] == 2


def test_v10_registry_cmp_010_duplicate_fail_close(db):
    """V10-REGISTRY-CMP-010：duplicate entry fail-close——同 key 双条目拒绝
    （选择 fail-close 而非静默去重——语义冲突显式暴露）。"""
    con, _ = db
    reg = {("industrial", "1.0.0"): None}
    # 构造同 key 场景（不同大小写归一后同 key——用 tuple 与 str 混合模拟）
    reg_mixed = {"industrial@1.0.0": None, ("industrial", "1.0.0"): None}
    with pytest.raises(RegistrySnapshotError,
                       match="duplicate entry_key"):
        RegistrySnapshotRuntime(con).create_snapshot(
            reg_mixed, registry_type="domain_pack")


def test_v10_registry_cmp_011_no_frozen_mutation(db):
    """V10-REGISTRY-CMP-011：no frozen mutation——快照全流程 akb_assertions/
    kg_nodes/kg_edges unchanged + registry 行为零变化。"""
    con, _ = db
    reg = _seed_domain_registry(con)
    reg_before = {k: v.pack_ref for k, v in reg.items()}
    snap = {t: [tuple(r) for r in con.execute(f"SELECT * FROM {t} ORDER BY 1")]
            for t in ("akb_assertions", "kg_nodes", "kg_edges")}
    s = RegistrySnapshotRuntime(con).create_snapshot(
        reg, registry_type="domain_pack")
    RegistrySnapshotRuntime.restore_snapshot(s)
    assert {k: v.pack_ref for k, v in reg.items()} == reg_before
    for t in ("akb_assertions", "kg_nodes", "kg_edges"):
        assert [tuple(r) for r in con.execute(
            f"SELECT * FROM {t} ORDER BY 1")] == snap[t], t


def test_v10_registry_cmp_012_full_regression(db):
    """V10-REGISTRY-CMP-012：full regression——四类 registry 快照全兼容（domain/
    rule/policy/causal）+ query/persist 层零干扰 + 建图回归。"""
    con, eid = db
    rt = RegistrySnapshotRuntime(con)
    # domain / rule / policy
    s1 = rt.create_snapshot(_seed_domain_registry(con),
                            registry_type="domain_pack")
    s2 = rt.create_snapshot(_seed_rule_registry(con, eid),
                            registry_type="rule_package")
    s3 = rt.create_snapshot(_seed_policy_registry(con),
                            registry_type="policy")
    # causal projection registry（fingerprint 锚）
    st = AssertionStore(con)
    st.create_candidate(subject_ref="Heat", predicate_ref="causes",
                        object={"kind": "literal", "value": "Aging"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    proj = CausalProjectionRuntime(con).project()
    s4 = rt.create_snapshot({("causal", "1"): proj},
                            registry_type="causal")
    for s, keys in ((s1, 2), (s2, 2), (s3, 2), (s4, 1)):
        assert len(s.entries) == keys
    # 四类 snapshot_id 互异
    assert len({s1.snapshot_id, s2.snapshot_id, s3.snapshot_id,
                s4.snapshot_id}) == 4
    # query/persist 层零干扰
    ScalePersistenceRuntime(con).persist_causal_edges(proj)
    assert ScaleQueryRuntime(con).list_causal_edges()["count"] == 1
    # 建图回归
    from agent_kb.kgraph import (
        GraphPersistenceService, GraphProjectionService, GraphQueryService)
    GraphPersistenceService(con).persist(GraphProjectionService().process(con))
    qv = GraphQueryService(con)
    v1 = qv.canonical_view()
    rt.create_snapshot(_seed_domain_registry(con),
                       registry_type="domain_pack")
    assert qv.canonical_view() == v1