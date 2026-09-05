# -*- coding: utf-8 -*-
"""ER-CMP-001..016（AKB-V05-IMPL-002：governed entity resolution）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.evidence_core.state_machine import validate_transition
from agent_kb.kgraph import (
    EntityGovernanceService,
    EntityIdentityResolver,
    GraphProjectionService,
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
def gov(db):
    return EntityGovernanceService(db)


def test_er_cmp_001_exact_identity_resolution(db):
    """ER-CMP-001：同一规范 identity → deterministic same canonical identity。"""
    r = EntityIdentityResolver()
    members = [
        {"normalized_form": "Pump-01", "entity_type": "equipment",
         "evidence_id": "E1", "candidate_id": "c1", "surface_form": "Pump-01"},
        {"normalized_form": "Pump-01", "entity_type": "equipment",
         "evidence_id": "E2", "candidate_id": "c2", "surface_form": "pump-01"}]
    clusters = r.resolve_clusters(members)
    assert len(clusters) == 1
    assert clusters[0]["canonical_id"] == r.canonical_id("Pump-01", "equipment")
    # 同输入重算同 id
    assert r.canonical_id("Pump-01", "equipment") == r.canonical_id("Pump-01", "equipment")


def test_er_cmp_002_entity_type_conflict(db):
    """ER-CMP-002：同文本不同 type → NOT MERGED（分裂簇）+ merge 拒绝。"""
    r = EntityIdentityResolver()
    clusters = r.resolve_clusters([
        {"normalized_form": "Pump-01", "entity_type": "pump",
         "evidence_id": "E1", "candidate_id": "c1"},
        {"normalized_form": "Pump-01", "entity_type": "valve",
         "evidence_id": "E2", "candidate_id": "c2"}])
    assert len(clusters) == 2                          # 分裂（不合并）
    gov = EntityGovernanceService(db, r)
    cand = gov.generate_merge_candidate(
        source_entity_ids=[clusters[0]["canonical_id"], clusters[1]["canonical_id"]],
        canonical_form="Pump-01", entity_types=["pump", "valve"],
        evidence_refs=["E1"], match_strategy="L3_SIMILARITY")
    with pytest.raises(ValueError, match="E-V05-ENTITY-TYPE-CONFLICT"):
        gov.approve_merge(candidate_id=cand.candidate_id, actor_id="human:reviewer",
                          reason="try")


def test_er_cmp_003_similarity_candidate_only(db):
    """ER-CMP-003（最重要负例）：similarity=1.0 → MergeCandidate created，NO automatic
    merge——无治理动作前无任何 approved 状态。"""
    gov = EntityGovernanceService(db)
    cand = gov.generate_merge_candidate(
        source_entity_ids=["ent_A", "ent_B"], canonical_form="Pump-01",
        entity_types=["equipment"], evidence_refs=["E1", "E2"],
        match_strategy="L3_SIMILARITY", match_score=1.0)
    assert cand.status == "pending"                    # 只是候选
    assert cand.match_strategy == "L3_SIMILARITY"
    assert not any(m["candidate_id"] == cand.candidate_id
                   for m in gov.merges.values())       # 零自动 merge
    assert all(m["canonical_id"] != cand.canonical_candidate_id
               for m in gov.merges.values())


def test_er_cmp_004_human_merge_approval(db, gov):
    """ER-CMP-004：valid candidate + required evidence + human actor → approved。"""
    cand = gov.generate_merge_candidate(
        source_entity_ids=["ent_A", "ent_B"], canonical_form="Pump-01",
        entity_types=["equipment"], evidence_refs=["E1", "E2"],
        match_strategy="L1_EXACT")
    result = gov.approve_merge(candidate_id=cand.candidate_id, actor_id="human:reviewer",
                               reason="治理批准：L1 精确同 identity",
                               required_evidence=["E1", "E2"])
    assert result["accepted"] is True
    assert cand.status == "approved"
    assert result["canonical_id"] == cand.canonical_candidate_id


def test_er_cmp_005_non_human_merge_rejection(db, gov):
    """ER-CMP-005：system/agent/llm actor → E-V05-GOVERNANCE-ACTOR + zero merge。"""
    cand = gov.generate_merge_candidate(
        source_entity_ids=["ent_A", "ent_B"], canonical_form="Pump-01",
        entity_types=["equipment"], evidence_refs=["E1"], match_strategy="L1_EXACT")
    for actor in ("system:validator", "agent:bot", "llm:model"):
        with pytest.raises(ValueError, match="E-V05-GOVERNANCE-ACTOR"):
            gov.approve_merge(candidate_id=cand.candidate_id, actor_id=actor, reason="x")
    assert cand.status == "pending"                    # zero merge
    assert not gov.merges


def test_er_cmp_006_evidence_requirement(db, gov):
    """ER-CMP-006：无/缺 Evidence → E-V05-NO-MERGE-EVIDENCE + zero merge。"""
    cand = gov.generate_merge_candidate(
        source_entity_ids=["ent_A", "ent_B"], canonical_form="Pump-01",
        entity_types=["equipment"], evidence_refs=[], match_strategy="L1_EXACT")
    with pytest.raises(ValueError, match="E-V05-NO-MERGE-EVIDENCE"):
        gov.approve_merge(candidate_id=cand.candidate_id, actor_id="human:reviewer",
                          reason="try")
    cand2 = gov.generate_merge_candidate(
        source_entity_ids=["ent_C", "ent_D"], canonical_form="Valve-02",
        entity_types=["equipment"], evidence_refs=["E9"], match_strategy="L1_EXACT")
    with pytest.raises(ValueError, match="E-V05-NO-MERGE-EVIDENCE"):
        gov.approve_merge(candidate_id=cand2.candidate_id, actor_id="human:reviewer",
                          reason="try", required_evidence=["E9", "E10"])
    assert not gov.merges


def test_er_cmp_007_merge_provenance(db, gov):
    """ER-CMP-007：approved merge → akb_provenance before/after/evidence/actor/reason
    全可恢复。"""
    cand = gov.generate_merge_candidate(
        source_entity_ids=["ent_A", "ent_B"], canonical_form="Pump-01",
        entity_types=["equipment"], evidence_refs=["E1", "E2"], match_strategy="L1_EXACT")
    result = gov.approve_merge(candidate_id=cand.candidate_id, actor_id="human:reviewer",
                               reason="audit reason X")
    rows = [dict(r) for r in db.execute(
        "SELECT * FROM akb_provenance WHERE activity='graph:entity-merge'")]
    assert rows
    m = json.loads(rows[0]["metadata_json"])
    assert m["reason"] == "audit reason X"
    assert m["entity_ids"] == ["ent_A", "ent_B"]
    assert m["before_snapshot"] and m["after_snapshot"]
    assert m["candidate_id"] == cand.candidate_id
    assert m["evidence_refs"] == ["E1", "E2"]
    assert rows[0]["actor_id"] == "human:reviewer"


def test_er_cmp_008_merge_is_logical(db, gov):
    """ER-CMP-008：merge 是逻辑的——source entities 不物理删除，历史可回溯。"""
    cand = gov.generate_merge_candidate(
        source_entity_ids=["ent_A", "ent_B"], canonical_form="Pump-01",
        entity_types=["equipment"], evidence_refs=["E1"], match_strategy="L1_EXACT")
    gov.approve_merge(candidate_id=cand.candidate_id, actor_id="human:reviewer",
                      reason="ok")
    rec = gov.merges[cand.canonical_candidate_id]
    assert rec["source_entity_ids"] == ["ent_A", "ent_B"]   # 源身份保留
    assert rec["before_snapshot"]                           # before 状态可回溯
    assert rec["provenance_ref"]                            # merge provenance 在


def test_er_cmp_009_split(db, gov):
    """ER-CMP-009：merged → human split → source identity trace 恢复 + provenance。"""
    cand = gov.generate_merge_candidate(
        source_entity_ids=["ent_A", "ent_B"], canonical_form="Pump-01",
        entity_types=["equipment"], evidence_refs=["E1"], match_strategy="L1_EXACT")
    approved = gov.approve_merge(candidate_id=cand.candidate_id, actor_id="human:reviewer",
                                 reason="merge first")
    with pytest.raises(ValueError, match="E-V05-GOVERNANCE-ACTOR"):
        gov.split_entity(canonical_id=approved["canonical_id"], actor_id="system:x",
                         reason="auto", partition=[["ent_A"], ["ent_B"]])
    split = gov.split_entity(canonical_id=approved["canonical_id"],
                             actor_id="human:reviewer", reason="误合并拆分",
                             partition=[["ent_A"], ["ent_B"]])
    assert split["accepted"]
    assert split["split"]["partition"] == [["ent_A"], ["ent_B"]]
    assert split["split"]["merge_provenance_ref"] == approved["provenance_ref"]
    assert gov.merges[approved["canonical_id"]]["superseded"] is True


def test_er_cmp_010_alias_governance(db, gov):
    """ER-CMP-010：human alias 成功；非 human 拒绝；跨实体冲突 → E-V05-ALIAS-CONFLICT。"""
    ok = gov.add_alias(entity_id="ent_A", alias="泵一号", actor_id="human:reviewer",
                       reason="现场别名")
    assert ok["accepted"]
    with pytest.raises(ValueError, match="E-V05-GOVERNANCE-ACTOR"):
        gov.add_alias(entity_id="ent_B", alias="泵二号", actor_id="system:bot", reason="x")
    with pytest.raises(ValueError, match="E-V05-ALIAS-CONFLICT"):
        gov.add_alias(entity_id="ent_B", alias="泵一号", actor_id="human:reviewer",
                      reason="conflict")
    # terminology 只读通道拒绝
    with pytest.raises(ValueError, match="E-V05-TERMINOLOGY-READONLY"):
        gov.add_alias(entity_id="ent_A", alias="术语表别名", actor_id="human:reviewer",
                      reason="x", source="terminology")
    # alias provenance 落库
    rows = [dict(r) for r in db.execute(
        "SELECT * FROM akb_provenance WHERE activity='graph:entity-alias'")]
    assert rows and json.loads(rows[0]["metadata_json"])["alias"] == "泵一号"


def test_er_cmp_011_rollback(db, gov):
    """ER-CMP-011：merge → rollback → 逻辑状态恢复 + audit 保留。"""
    cand = gov.generate_merge_candidate(
        source_entity_ids=["ent_A", "ent_B"], canonical_form="Pump-01",
        entity_types=["equipment"], evidence_refs=["E1"], match_strategy="L1_EXACT")
    approved = gov.approve_merge(candidate_id=cand.candidate_id, actor_id="human:reviewer",
                                 reason="merge")
    rb = gov.rollback(canonical_id=approved["canonical_id"], actor_id="human:reviewer",
                      reason="撤销误合并")
    assert rb["accepted"]
    assert rb["source_entity_ids"] == ["ent_A", "ent_B"]    # 源可追溯状态恢复
    # merge 与 rollback 的 provenance 都保留（禁物理删除）
    acts = [r["activity"] for r in db.execute(
        "SELECT activity FROM akb_provenance WHERE activity LIKE 'graph:entity-%'")]
    assert "graph:entity-merge" in acts and "graph:entity-rollback" in acts
    assert gov.merges[approved["canonical_id"]]["rolled_back"] is True
    # 二次 rollback 拒绝（已回滚）
    with pytest.raises(ValueError, match="E-V05-ROLLBACK-NOT-FOUND"):
        gov.rollback(canonical_id=approved["canonical_id"], actor_id="human:reviewer",
                     reason="again")


def test_er_cmp_012_determinism(db):
    """ER-CMP-012：same input → same candidate_id / canonical_id / resolution。"""
    g1 = EntityGovernanceService(db)
    g2 = EntityGovernanceService(db)
    c1 = g1.generate_merge_candidate(
        source_entity_ids=["ent_A", "ent_B"], canonical_form="Pump-01",
        entity_types=["equipment"], evidence_refs=["E1"], match_strategy="L1_EXACT")
    c2 = g2.generate_merge_candidate(
        source_entity_ids=["ent_A", "ent_B"], canonical_form="Pump-01",
        entity_types=["equipment"], evidence_refs=["E1"], match_strategy="L1_EXACT")
    assert c1.candidate_id == c2.candidate_id
    assert c1.canonical_candidate_id == c2.canonical_candidate_id


def test_er_cmp_013_cross_instance_determinism(db):
    """ER-CMP-013：两个独立 resolver 实例 → identical result。"""
    r1 = EntityIdentityResolver(domain_pack_version="dp1")
    r2 = EntityIdentityResolver(domain_pack_version="dp1")
    members = [{"normalized_form": "Pump-01", "entity_type": "equipment",
                "evidence_id": "E1", "candidate_id": "c1"}]
    assert r1.resolve_clusters(members) == r2.resolve_clusters(members)
    assert r1.canonical_id("Pump-01", "equipment") == r2.canonical_id("Pump-01",
                                                                      "equipment")
    # domain-pack aware：不同 dpv → 不同 id（确定性差异）
    r3 = EntityIdentityResolver(domain_pack_version="dp2")
    assert r1.canonical_id("Pump-01", "equipment") != r3.canonical_id("Pump-01",
                                                                      "equipment")


def test_er_cmp_014_idempotency(db, gov):
    """ER-CMP-014：同 merge 重复批准 → 零重复 merge/零重复 provenance action。"""
    cand = gov.generate_merge_candidate(
        source_entity_ids=["ent_A", "ent_B"], canonical_form="Pump-01",
        entity_types=["equipment"], evidence_refs=["E1"], match_strategy="L1_EXACT")
    gov.approve_merge(candidate_id=cand.candidate_id, actor_id="human:reviewer",
                      reason="first")
    n1 = db.execute("SELECT COUNT(*) c FROM akb_provenance"
                    " WHERE activity='graph:entity-merge'").fetchone()["c"]
    with pytest.raises(ValueError, match="E-V05-CANDIDATE-STATUS"):
        gov.approve_merge(candidate_id=cand.candidate_id, actor_id="human:reviewer",
                          reason="second")
    n2 = db.execute("SELECT COUNT(*) c FROM akb_provenance"
                    " WHERE activity='graph:entity-merge'").fetchone()["c"]
    assert n1 == n2 == 1                              # 无重复
    assert len(gov.merges) == 1


def test_er_cmp_015_v04_regression_anchor(db, seeded):
    """ER-CMP-015：V0.4 inferred→candidate→validated 仍工作；inferred→asserted 仍禁。"""
    from agent_kb.evidence_core.assertions import AssertionValidator
    inf = seeded["reasoning"]["assertions"][0]
    assert inf.status == "candidate" and inf.assertion_type == "inferred"
    v = validate_transition(current_status="candidate", new_status="asserted",
                            assertion_type="inferred", actor_id="human:reviewer",
                            evidence_count=1)
    assert any("E-ILLEGAL-TRANSITION" in x for x in v)
    # candidate→validated 治理面保持（validator 通道）
    if inf.evidence_refs:
        r = AssertionValidator(db).validate(assertion_id=inf.assertion_id,
                                            actor_id="system:validator")
        assert r["accepted"]


def test_er_cmp_016_legacy_graph_isolation(db):
    """ER-CMP-016：agent_kb.graph 与 agent_kb.kgraph 完全隔离（import 面 + API 面）。"""
    import agent_kb.graph as legacy
    import agent_kb.kgraph as kgraph
    # API 面互斥：legacy 符号不在 kgraph；kgraph 符号不在 legacy
    for sym in ("DeterministicRelationExtractor", "GraphEdge", "SQLiteGraphStore",
                "GraphPath", "RelationExtractor"):
        assert not hasattr(kgraph, sym), sym
    for sym in ("GraphProjectionService", "EntityIdentityResolver",
                "EntityGovernanceService"):
        assert not hasattr(legacy, sym), sym
    # kgraph 零写 legacy 数据结构（graph_edges 表零变化）
    before = db.execute("SELECT COUNT(*) c FROM graph_edges").fetchone()["c"]
    EntityIdentityResolver().resolve_clusters([
        {"normalized_form": "X", "entity_type": "t", "evidence_id": "E",
         "candidate_id": "c"}])
    after = db.execute("SELECT COUNT(*) c FROM graph_edges").fetchone()["c"]
    assert before == after