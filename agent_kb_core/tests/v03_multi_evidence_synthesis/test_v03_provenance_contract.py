# -*- coding: utf-8 -*-
"""V0.3 Conflict Provenance Contract（AKB-V03-IMPL-003）P-001..P-010。

行为级验证链：输入对象 → 实际 detection → ConflictRecord →
source_evidence_ids / unit_ids / candidate_id 各归其位。
显式构造 candidate_id != unit_id（否则测试无意义）。
"""
from __future__ import annotations

import json

import pytest

from agent_kb.evidence_core.synthesis.conflicts import ConflictDetector
from agent_kb.evidence_core.synthesis.models import (
    AlignmentResult,
    EntityAlignmentCluster,
    RelationAlignmentCluster,
)


def _al_with_entities():
    """构造：E1/u1 与 E2/u2，candidate_id='cand-X'（与 unit_id 完全不同字串）。"""
    al = AlignmentResult()
    al.entity_clusters.append(EntityAlignmentCluster(
        cluster_id="cl_0001", representative="OBC",
        members=[
            {"evidence_id": "EV-1", "unit_id": "UNIT-1", "candidate_id": "cand-1",
             "normalized_form": "OBC", "entity_type": "equipment",
             "ontology_ref": "object_type:equipment", "confidence": 0.9},
            {"evidence_id": "EV-2", "unit_id": "UNIT-2", "candidate_id": "cand-2",
             "normalized_form": "OBC", "entity_type": "document",
             "ontology_ref": "object_type:document_ref", "confidence": 0.9}]))
    al.entity_clusters.append(EntityAlignmentCluster(
        cluster_id="cl_0002", representative="265V",
        members=[
            {"evidence_id": "EV-1", "unit_id": "UNIT-1", "candidate_id": "cand-3",
             "normalized_form": "265V", "entity_type": "parameter", "confidence": 0.9}]))
    al.relation_clusters.append(RelationAlignmentCluster(
        cluster_id="rc_0001", subject_cluster="cl_0001", predicate="has_parameter",
        object_cluster="cl_0002",
        members=[
            {"evidence_id": "EV-1", "unit_id": "UNIT-1", "confidence": 0.9,
             "object_cluster": "cl_0002", "object_value": "265V"},
            {"evidence_id": "EV-2", "unit_id": "UNIT-2", "confidence": 0.85,
             "object_cluster": "cl_0002", "object_value": "280V"}]))
    al.temporal_alignment = {"per_evidence": {"EV-1": "anchored", "EV-2": "anchored"},
                             "overall": "same", "anchors": {}}
    return al


def _units():
    return [{"evidence_id": "EV-1", "unit_id": "UNIT-1", "source_type": "document"},
            {"evidence_id": "EV-2", "unit_id": "UNIT-2", "source_type": "human"}]


AUDIT = "2026-09-03T12:00:00Z"


def _detect(al=None, units=None):
    cs = ConflictDetector().detect(al or _al_with_entities(), units or _units(),
                                   audit_ts=AUDIT)
    by = {}
    for c in cs.conflicts:
        by.setdefault(c.conflict_type, []).append(c)
    return cs, by


def _members_of(al):
    return [m for cl in al.entity_clusters for m in cl.members]


def test_p_001_value_conflict_provenance(db):
    cs, by = _detect()
    vc = by["VALUE_CONFLICT"][0]
    assert set(vc.source_evidence_ids) == {"EV-1", "EV-2"}
    assert set(vc.unit_ids) == {"UNIT-1", "UNIT-2"}
    for side in vc.sides:
        for m in side["members"]:
            assert m["evidence_id"] in ("EV-1", "EV-2")
            assert m["unit_id"] in ("UNIT-1", "UNIT-2")


def test_p_002_ontology_conflict_unit_ids_not_candidate_ids():
    """本轮最关键测试：unit_ids ← unit_id，禁止 candidate_id 冒充。"""
    al = _al_with_entities()
    cs, by = _detect(al)
    oc = by["ONTOLOGY_CONFLICT"][0]
    real_unit_ids = {m["unit_id"] for cl in al.entity_clusters
                     for m in cl.members if m.get("ontology_ref")}
    candidate_ids = {m["candidate_id"] for cl in al.entity_clusters for m in cl.members}
    assert set(oc.unit_ids) == real_unit_ids
    assert set(oc.unit_ids).isdisjoint(candidate_ids)      # P-009 核心
    assert oc.unit_ids == ["UNIT-1", "UNIT-2"]
    assert "cand-1" not in oc.unit_ids and "cand-2" not in oc.unit_ids


def test_p_003_identity_conflict_unit_ids_not_candidate_ids():
    al = _al_with_entities()
    cs, by = _detect(al)
    ic = by["IDENTITY_CONFLICT"][0]
    candidate_ids = {m["candidate_id"] for cl in al.entity_clusters for m in cl.members}
    assert set(ic.unit_ids) == {"UNIT-1", "UNIT-2"}
    assert set(ic.unit_ids).isdisjoint(candidate_ids)
    assert ic.detection_method == "CONF-005"


def test_p_004_state_conflict_provenance():
    """STATE_CONFLICT：sides 自带 unit_id/evidence_id → 直接建 ConflictRecord。"""
    al = _al_with_entities()
    al.state_contradictions = [{
        "cluster_id": "st_0001", "state_predicate": "has_parameter",
        "source_evidence_ids": ["EV-1", "EV-2"],
        "members": [{"evidence_id": "EV-1", "unit_id": "UNIT-1",
                     "valid_from": "2026-01-01", "valid_until": "2026-06-01",
                     "object_value": "265V"},
                    {"evidence_id": "EV-2", "unit_id": "UNIT-2",
                     "valid_from": "2027-01-01", "valid_until": "2027-06-01",
                     "object_value": "265V"}],
        "sides": [{"evidence_id": "EV-1", "unit_id": "UNIT-1",
                   "valid_from": "2026-01-01", "valid_until": "2026-06-01",
                   "object_value": "265V"},
                  {"evidence_id": "EV-2", "unit_id": "UNIT-2",
                   "valid_from": "2027-01-01", "valid_until": "2027-06-01",
                   "object_value": "265V"}]}]
    cs, by = _detect(al)
    sc = by["STATE_CONFLICT"][0]
    assert set(sc.source_evidence_ids) == {"EV-1", "EV-2"}
    assert set(sc.unit_ids) == {"UNIT-1", "UNIT-2"}
    for s in sc.sides:
        assert s["evidence_id"] in ("EV-1", "EV-2") and s["unit_id"] in ("UNIT-1", "UNIT-2")
    assert sc.detection_method == "CONF-006-STATE"


def test_p_005_source_conflict_provenance():
    cs, by = _detect()
    sc = by["SOURCE_CONFLICT"][0]
    assert set(sc.source_evidence_ids) == {"EV-1", "EV-2"}
    assert set(sc.unit_ids) == {"UNIT-1", "UNIT-2"}
    sides_types = {s["source_type"] for s in sc.sides}
    assert sides_types == {"document", "human"}


def test_p_006_temporal_conflict_provenance():
    """新契约：contradiction_members 驱动精确 scope（V03-IMPL-004）。"""
    al = _al_with_entities()
    al.temporal_alignment = dict(al.temporal_alignment,
        overall="contradictory",
        contradiction_members=[
            {"evidence_id": "EV-1", "unit_id": "UNIT-1",
             "valid_from": "2026-01-01", "valid_until": "2026-06-01"},
            {"evidence_id": "EV-2", "unit_id": "UNIT-2",
             "valid_from": "2027-01-01", "valid_until": "2027-06-01"}])
    cs, by = _detect(al)
    tc = by["TEMPORAL_CONFLICT"][0]
    assert set(tc.source_evidence_ids) == {"EV-1", "EV-2"}
    assert set(tc.unit_ids) == {"UNIT-1", "UNIT-2"}
    # §12：sides 可定位 evidence_id/unit_id/valid_from/valid_until
    for s in tc.sides:
        assert s["evidence_id"] in ("EV-1", "EV-2")
        assert s["unit_id"] in ("UNIT-1", "UNIT-2")
        assert s["valid_from"] and s["valid_until"]


def test_p_007_relation_conflict_provenance():
    al = _al_with_entities()
    # 注入谓词互斥对（同 subj/obj 簇 has_parameter + constrained_by）
    al.relation_clusters.append(RelationAlignmentCluster(
        cluster_id="rc_0002", subject_cluster="cl_0001", predicate="constrained_by",
        object_cluster="cl_0002",
        members=[{"evidence_id": "EV-1", "unit_id": "UNIT-1", "confidence": 0.8,
                  "object_cluster": "cl_0002", "object_value": "265V"}]))
    cs, by = _detect(al)
    rc = by["RELATION_CONFLICT"][0]
    assert rc.detection_method == "CONF-007-RELATION"
    assert set(rc.source_evidence_ids) == {"EV-1", "EV-2"}
    assert set(rc.unit_ids) == {"UNIT-1", "UNIT-2"}


def test_p_008_audit_timestamp_contract():
    cs, by = _detect()
    for ctype, records in by.items():
        for c in records:
            assert c.audit_timestamp == AUDIT


def test_p_009_no_candidate_as_unit_across_all_types():
    """全部冲突类型：unit_ids 与 candidate_ids 不相交。"""
    al = _al_with_entities()
    al.relation_clusters.append(RelationAlignmentCluster(
        cluster_id="rc_0002", subject_cluster="cl_0001", predicate="constrained_by",
        object_cluster="cl_0002",
        members=[{"evidence_id": "EV-1", "unit_id": "UNIT-1", "confidence": 0.8,
                  "object_cluster": "cl_0002", "object_value": "265V"}]))
    cs, by = _detect(al)
    candidate_ids = {m["candidate_id"] for cl in al.entity_clusters for m in cl.members}
    assert candidate_ids == {"cand-1", "cand-2", "cand-3"}  # 显式异名前提成立
    for ctype, records in by.items():
        for c in records:
            assert set(c.unit_ids).isdisjoint(candidate_ids), f"{ctype} leaked candidate as unit"


def test_p_010_cross_unit_duplicate_candidate_ids():
    """两个 SemanticUnit 用相同 candidate_id='cand-X' → unit_ids 仍正确区分。"""
    al = AlignmentResult()
    al.entity_clusters.append(EntityAlignmentCluster(
        cluster_id="cl_0001", representative="OBC",
        members=[
            {"evidence_id": "EV-A", "unit_id": "UNIT-A", "candidate_id": "cand-X",
             "normalized_form": "OBC", "entity_type": "equipment",
             "ontology_ref": "object_type:equipment", "confidence": 0.9},
            {"evidence_id": "EV-B", "unit_id": "UNIT-B", "candidate_id": "cand-X",
             "normalized_form": "OBC", "entity_type": "document",
             "ontology_ref": "object_type:document_ref", "confidence": 0.9}]))
    units = [{"evidence_id": "EV-A", "unit_id": "UNIT-A", "source_type": "document"},
             {"evidence_id": "EV-B", "unit_id": "UNIT-B", "source_type": "human"}]
    cs, by = _detect(al, units)
    oc = by["ONTOLOGY_CONFLICT"][0]
    assert set(oc.unit_ids) == {"UNIT-A", "UNIT-B"}          # 正确区分 A/B
    assert oc.unit_ids.count("cand-X") == 0
    ic = by["IDENTITY_CONFLICT"][0]
    assert set(ic.unit_ids) == {"UNIT-A", "UNIT-B"}


def test_p_011_reverse_locate_chain(db):
    """行为级反查链：Conflict → Evidence → SemanticUnit → Candidate。"""
    from agent_kb.evidence_core.synthesis import SynthesisEngine
    db = db
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('pc', 'document', 'PC')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at) VALUES ('dpc', 'pc', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    from agent_kb.evidence_core.compilation import SemanticCompiler
    store = EvidenceStore(db)
    comp = SemanticCompiler(db)
    eids = []
    for t in ["OBC 额定输入电压 265V。", "OBC 额定输入电压 280V。"]:
        ev = store.create(document_id="dpc", content=t, extraction_method="t")
        comp.compile(ev.evidence_id, actor_id="system:compiler")
        eids.append(ev.evidence_id)
    eng = SynthesisEngine(db)
    r = eng.synthesize(eids, actor_id="system:synth")
    vc = [c for c in r["run"].conflicts["conflicts"]
          if c["conflict_type"] == "VALUE_CONFLICT"][0]
    # 反向定位：source_evidence_ids → SemanticUnit → candidate
    for eid in vc["source_evidence_ids"]:
        unit_rows = list(db.execute(
            "SELECT unit_id FROM akb_semantic_units WHERE evidence_id=?", (eid,)))
        assert unit_rows, f"evidence {eid} must resolve to SemanticUnit"
        assert any(u in vc["unit_ids"] for u in
                   [row["unit_id"] for row in unit_rows])
    # sides 成员可回溯到具体 entity candidate（normalized_form）
    for side in vc["sides"]:
        for m in side["members"]:
            assert m["evidence_id"] in eids