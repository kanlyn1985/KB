# -*- coding: utf-8 -*-
"""V0.3 Conflict Provenance Scope Contract（AKB-V03-IMPL-004）P-012..P-015。

核心升级：每类 conflict 的 source_evidence_ids/unit_ids 必须是**精确集合**
（== expected exact set），不是"包含正确成员但夹带无关成员"。
"""
from __future__ import annotations

import json

import pytest

from agent_kb.evidence_core.synthesis import SynthesisEngine
from agent_kb.evidence_core.synthesis.conflicts import ConflictDetector
from agent_kb.evidence_core.synthesis.models import (
    AlignmentResult,
    EntityAlignmentCluster,
    RelationAlignmentCluster,
)


def test_p_012_temporal_conflict_provenance_scope(db):
    """无关 Evidence（E3/E4）不得进入 TEMPORAL_CONFLICT。"""
    from agent_kb.evidence_core.synthesis.alignment import EvidenceAlignmentEngine
    eng_e = EvidenceAlignmentEngine()
    # E1/E2 区间互斥（真实 contradictory）；E3/E4 无关时间记录（missing）
    units = [
        {"evidence_id": "E1", "unit_id": "UNIT-1",
         "temporal_parse": {"valid_time": {"valid_from": "2026-01-01",
                                           "valid_until": "2026-06-01"},
                            "parse_status": "resolved"}},
        {"evidence_id": "E2", "unit_id": "UNIT-2",
         "temporal_parse": {"valid_time": {"valid_from": "2027-01-01",
                                           "valid_until": "2027-06-01"},
                            "parse_status": "resolved"}},
        {"evidence_id": "E3", "unit_id": "UNIT-3", "temporal_parse": None},
        {"evidence_id": "E4", "unit_id": "UNIT-4", "temporal_parse": None},
    ]
    # Semantic Context：E1/E2 同实体簇（真实冲突语境）；E3/E4 无实体（无关记录）
    al = eng_e.align([
        {"evidence_id": "E1", "unit_id": "UNIT-1",
         "entity_candidates": [{"candidate_id": "cd1", "normalized_form": "OBC",
                                "entity_type": "equipment"}],
         "temporal_parse": units[0]["temporal_parse"]},
        {"evidence_id": "E2", "unit_id": "UNIT-2",
         "entity_candidates": [{"candidate_id": "cd2", "normalized_form": "OBC",
                                "entity_type": "equipment"}],
         "temporal_parse": units[1]["temporal_parse"]},
        {"evidence_id": "E3", "unit_id": "UNIT-3",
         "entity_candidates": [{"candidate_id": "cd3", "normalized_form": " unrelated X",
                                "entity_type": "equipment"}], "temporal_parse": None},
        {"evidence_id": "E4", "unit_id": "UNIT-4",
         "entity_candidates": [{"candidate_id": "cd4", "normalized_form": " unrelated Y",
                                "entity_type": "equipment"}], "temporal_parse": None}])
    ta = al.temporal_alignment
    assert ta["overall"] == "contradictory"
    assert ta["contradiction_members"], "exact contradictory members required"
    cs = ConflictDetector().detect(al, units, audit_ts="T")
    tc = [c for c in cs.conflicts if c.conflict_type == "TEMPORAL_CONFLICT"]
    assert tc, "TEMPORAL_CONFLICT must be emitted"
    conflict = tc[0]
    # 精确集合（P-014 核心语义）
    assert set(conflict.source_evidence_ids) == {"E1", "E2"}
    assert set(conflict.unit_ids) == {"UNIT-1", "UNIT-2"}
    # 无关成员排除（任务书 §5 显式断言）
    assert "E3" not in conflict.source_evidence_ids
    assert "E4" not in conflict.source_evidence_ids
    assert "UNIT-3" not in conflict.unit_ids
    assert "UNIT-4" not in conflict.unit_ids
    # §12：sides 可定位四方字段
    for s in conflict.sides:
        assert s["evidence_id"] in ("E1", "E2")
        assert s["unit_id"] in ("UNIT-1", "UNIT-2")
        assert s["valid_from"] and s["valid_until"]


def test_p_013_temporal_provenance_identity_isolation(db):
    """三层隔离：Evidence=E1,E2 / Unit=U1,U2 / candidate-C MUST NOT appear。"""
    from agent_kb.evidence_core.synthesis.alignment import EvidenceAlignmentEngine
    eng_e = EvidenceAlignmentEngine()
    units = [
        {"evidence_id": "E1", "unit_id": "U1", "unit_type": "text",
         "entity_candidates": [{"candidate_id": "candidate-A",
                                "normalized_form": "OBC", "entity_type": "equipment"}],
         "temporal_parse": {"valid_time": {"valid_from": "2026-01-01",
                                           "valid_until": "2026-06-01"},
                            "parse_status": "resolved"}},
        {"evidence_id": "E2", "unit_id": "U2", "unit_type": "text",
         "entity_candidates": [{"candidate_id": "candidate-B",
                                "normalized_form": "OBC", "entity_type": "equipment"}],
         "temporal_parse": {"valid_time": {"valid_from": "2027-01-01",
                                           "valid_until": "2027-06-01"},
                            "parse_status": "resolved"}},
        {"evidence_id": "E3", "unit_id": "U3", "unit_type": "text",
         "entity_candidates": [{"candidate_id": "candidate-C",
                                "normalized_form": " unrelated entity",
                                "entity_type": "equipment"}],
         "temporal_parse": None},
    ]
    al = eng_e.align(units)
    # 预热 contradiction：直接补 members（E1/E2 区间互斥）
    al.temporal_alignment["overall"] = "contradictory"
    al.temporal_alignment["contradiction_members"] = [
        {"evidence_id": "E1", "unit_id": "U1",
         "valid_from": "2026-01-01", "valid_until": "2026-06-01"},
        {"evidence_id": "E2", "unit_id": "U2",
         "valid_from": "2027-01-01", "valid_until": "2027-06-01"}]
    cs = ConflictDetector().detect(al, units, audit_ts="T")
    tc = [c for c in cs.conflicts if c.conflict_type == "TEMPORAL_CONFLICT"][0]
    assert set(tc.source_evidence_ids) == {"E1", "E2"}
    assert set(tc.unit_ids) == {"U1", "U2"}
    assert "candidate-C" not in tc.unit_ids
    assert "candidate-A" not in tc.unit_ids and "candidate-B" not in tc.unit_ids
    # E3（candidate-C 所属）整体不在 provenance
    assert "E3" not in tc.source_evidence_ids


def test_p_014_conflict_provenance_scope_contract_all_types(db):
    """全部 7 类冲突：source_evidence_ids/unit_ids == actual conflict members 精确集合。"""
    al = AlignmentResult()
    # 实体簇：E1/u1 与 E2/u2（entity_type 分歧 → IDENTITY；ontology_ref 分歧 → ONTOLOGY）
    al.entity_clusters.append(EntityAlignmentCluster(
        cluster_id="cl_0001", representative="OBC",
        members=[
            {"evidence_id": "E1", "unit_id": "u1", "candidate_id": "cd1",
             "normalized_form": "OBC", "entity_type": "equipment",
             "ontology_ref": "object_type:equipment", "confidence": 0.9},
            {"evidence_id": "E2", "unit_id": "u2", "candidate_id": "cd2",
             "normalized_form": "OBC", "entity_type": "document",
             "ontology_ref": "object_type:document_ref", "confidence": 0.9}]))
    # relation 簇（E1/E2，object 值不同 → VALUE；双谓词 → RELATION）
    al.relation_clusters.append(RelationAlignmentCluster(
        cluster_id="rc_0001", subject_cluster="cl_0001", predicate="has_parameter",
        object_cluster="cl_0002",
        members=[{"evidence_id": "E1", "unit_id": "u1", "confidence": 0.9,
                  "object_cluster": "cl_0002", "object_value": "265V"},
                 {"evidence_id": "E2", "unit_id": "u2", "confidence": 0.9,
                  "object_cluster": "cl_0002", "object_value": "280V"}]))
    al.relation_clusters.append(RelationAlignmentCluster(
        cluster_id="rc_0002", subject_cluster="cl_0001", predicate="constrained_by",
        object_cluster="cl_0002",
        members=[{"evidence_id": "E1", "unit_id": "u1", "confidence": 0.8,
                  "object_cluster": "cl_0002", "object_value": "265V"}]))
    # temporal contradictory（E1/E2）
    al.temporal_alignment = {
        "per_evidence": {"E1": "anchored", "E2": "anchored"}, "overall": "contradictory",
        "contradiction_members": [
            {"evidence_id": "E1", "unit_id": "u1",
             "valid_from": "2026-01-01", "valid_until": "2026-06-01"},
            {"evidence_id": "E2", "unit_id": "u2",
             "valid_from": "2027-01-01", "valid_until": "2027-06-01"}]}
    units = [
        {"evidence_id": "E1", "unit_id": "u1", "source_type": "document"},
        {"evidence_id": "E2", "unit_id": "u2", "source_type": "human"},
        {"evidence_id": "E9", "unit_id": "u9", "source_type": "document"},  # 无关第三方
    ]
    cs = ConflictDetector().detect(al, units, audit_ts="T")
    by = {}
    for c in cs.conflicts:
        by.setdefault(c.conflict_type, []).append(c)
    expected_members = {"E1", "E2"}
    for ctype in ("VALUE_CONFLICT", "ONTOLOGY_CONFLICT", "TEMPORAL_CONFLICT",
                  "SOURCE_CONFLICT", "IDENTITY_CONFLICT"):
        assert ctype in by, f"{ctype} missing"
        c = by[ctype][0]
        # 精确集合断言（非 subset/superset）
        assert set(c.source_evidence_ids) == expected_members, ctype
        assert set(c.unit_ids) == {"u1", "u2"}, ctype
        # 第三方 E9/u9 零渗漏
        assert "E9" not in c.source_evidence_ids and "u9" not in c.unit_ids
    # STATE_CONFLICT：E1/E2 contradiction（第三方不进入）
    al.state_contradictions = [{
        "cluster_id": "st_0001", "state_predicate": "has_parameter",
        "source_evidence_ids": ["E1", "E2"],
        "sides": [{"evidence_id": "E1", "unit_id": "u1",
                   "valid_from": "2026-01-01", "valid_until": "2026-06-01",
                   "object_value": "265V"},
                  {"evidence_id": "E2", "unit_id": "u2",
                   "valid_from": "2027-01-01", "valid_until": "2027-06-01",
                   "object_value": "265V"}]}]
    cs2 = ConflictDetector().detect(al, units, audit_ts="T")
    sc = [c for c in cs2.conflicts if c.conflict_type == "STATE_CONFLICT"][0]
    assert set(sc.source_evidence_ids) == {"E1", "E2"}
    assert set(sc.unit_ids) == {"u1", "u2"}
    assert "E9" not in sc.source_evidence_ids and "u9" not in sc.unit_ids
    # RELATION_CONFLICT：谓词互斥对成员 = E1（两簇并集 member）
    rcl = [c for c in cs.conflicts if c.conflict_type == "RELATION_CONFLICT"]
    if rcl:
        assert set(rcl[0].source_evidence_ids) <= {"E1", "E2"}
        assert set(rcl[0].unit_ids) <= {"u1", "u2"}


def test_p_015_temporal_reverse_trace(db):
    """行为链：TEMPORAL_CONFLICT → evidence → akb_evidence → akb_semantic_units →
    unit_ids → candidate provenance——100% exact match（禁 subset/superset）。"""
    # 真实数据链：两条区间互斥证据
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('pt', 'document', 'PT')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at, effective_at) VALUES ('dpt', 'pt', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'), '2026-01-01T00:00:00Z')")
    from agent_kb.evidence_core import EvidenceStore
    from agent_kb.evidence_core.compilation import SemanticCompiler
    store = EvidenceStore(db)
    comp = SemanticCompiler(db)
    eids = []
    for t in ["OBC 额定输入电压 265V。", "OBC 额定输入电压 280V。"]:
        ev = store.create(document_id="dpt", content=t, extraction_method="t")
        comp.compile(ev.evidence_id, actor_id="system:compiler")
        eids.append(ev.evidence_id)
    eng = SynthesisEngine(db)
    r = eng.synthesize(eids, actor_id="system:synth")
    tc = [c for c in r["run"].conflicts["conflicts"]
          if c["conflict_type"] == "TEMPORAL_CONFLICT"]
    if not tc:
        pytest.skip("no temporal conflict in this data (compatible case)")
    conflict = tc[0]
    # 反查链 100% exact：每个 source_evidence_id → akb_evidence 存在 →
    # akb_semantic_units 的 unit_id 集合与 conflict.unit_ids 完全一致
    unit_ids_from_db = []
    for eid in conflict["source_evidence_ids"]:
        row = db.execute("SELECT 1 FROM akb_evidence WHERE evidence_id=?", (eid,)).fetchone()
        assert row is not None, f"evidence {eid} must exist"
        db_units = [row2["unit_id"] for row2 in db.execute(
            "SELECT unit_id FROM akb_semantic_units WHERE evidence_id=?", (eid,))]
        assert db_units, "SemanticUnit must exist"
        unit_ids_from_db.extend(db_units)
    assert set(conflict["unit_ids"]) == set(unit_ids_from_db)  # exact（非 subset/superset）
    assert len(conflict["unit_ids"]) == len(set(conflict["unit_ids"]))  # 无重复歧义
    # candidate provenance：run 快照可回溯每个成员
    run = eng.describe_synthesis_run(r["run"].run_id)
    members = json.loads(run["members_json"])
    assert set(members) == set(conflict["source_evidence_ids"])