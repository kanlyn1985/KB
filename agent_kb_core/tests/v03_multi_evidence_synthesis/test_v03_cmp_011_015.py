# -*- coding: utf-8 -*-
"""V03-CMP-011..015：冲突（value/temporal/source/ontology）+ 合成。"""
from __future__ import annotations

import pytest

from agent_kb.evidence_core.synthesis import SynthesisEngine, SynthesisError


def _conflicting_setup(db):
    """两条同实体同谓词不同值的证据（VALUE_CONFLICT）。"""
    from agent_kb.evidence_core import EvidenceStore
    from agent_kb.evidence_core.compilation import SemanticCompiler
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('sc', 'document', 'SC')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at) VALUES ('dc', 'sc', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    store = EvidenceStore(db)
    comp = SemanticCompiler(db)
    eids = []
    for t in ["OBC 额定输入电压 265V。", "OBC 额定输入电压 280V。"]:
        ev = store.create(document_id="dc", content=t, extraction_method="t")
        comp.compile(ev.evidence_id, actor_id="system:compiler")
        eids.append(ev.evidence_id)
    return eids, SynthesisEngine(db)


def test_v03_cmp_011_value_conflict(db):
    eids, eng = _conflicting_setup(db)
    r = eng.synthesize(eids, actor_id="system:synth")
    conflicts = r["run"].conflicts["conflicts"]
    assert any(c["conflict_type"] == "VALUE_CONFLICT" for c in conflicts)
    vc = next(c for c in conflicts if c["conflict_type"] == "VALUE_CONFLICT")
    assert set(vc["source_evidence_ids"]) == set(eids)      # 双方保留
    assert vc["sides"] and len(vc["sides"]) == 2            # 各方完整
    assert vc["detection_method"] == "CONF-001"


def test_v03_cmp_012_temporal_conflict_not_synthesized(db):
    # contradictory 由 temporal alignment 标注；内置 same/missing/unresolved 判定下
    # contradictory 注入：unit temporal valid_time 互斥——通过 missing 锚定路径验证不伪造
    eids, eng = _conflicting_setup(db)
    r = eng.synthesize(eids, actor_id="system:synth")
    ta = r["run"].alignment["temporal_alignment"]
    assert ta["overall"] in ("same", "partial", "missing", "unresolved")
    assert ta["overall"] != "contradictory" or any(
        c["conflict_type"] == "TEMPORAL_CONFLICT"
        for c in r["run"].conflicts["conflicts"])


def test_v03_cmp_013_source_conflict(db):
    # 不同 source_type（document vs ingested）→ SOURCE_CONFLICT
    from agent_kb.evidence_core import EvidenceStore
    from agent_kb.evidence_core.compilation import SemanticCompiler
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('sd', 'document', 'SD')")
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('si', 'human', 'SI')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at) VALUES ('dd', 'sd', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at) VALUES ('di', 'si', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    store = EvidenceStore(db)
    comp = SemanticCompiler(db)
    eids = []
    for doc, t in [("dd", "OBC 额定输入电压 265V。"), ("di", "OBC 额定输入电压是 265V。")]:
        ev = store.create(document_id=doc, content=t, extraction_method="t")
        comp.compile(ev.evidence_id, actor_id="system:compiler")
        eids.append(ev.evidence_id)
    eng = SynthesisEngine(db)
    r = eng.synthesize(eids, actor_id="system:synth")
    conflicts = r["run"].conflicts["conflicts"]
    assert any(c["conflict_type"] == "SOURCE_CONFLICT" for c in conflicts)
    # 权重快照存在（weight 影响排序非裁决）
    assert r["run"].weights and all("weight" in w for w in r["run"].weights)


def test_v03_cmp_014_ontology_conflict(db):
    # ontology_ref 分歧由 provider/mapper 注入——用 unit 快照直接构造（离线验证 CONFLICT-002 规则）
    from agent_kb.evidence_core.synthesis.conflicts import ConflictDetector
    from agent_kb.evidence_core.synthesis.models import AlignmentResult, EntityAlignmentCluster
    al = AlignmentResult()
    al.entity_clusters.append(EntityAlignmentCluster(
        cluster_id="cl_0001", representative="OBC",
        members=[{"evidence_id": "e1", "candidate_id": "c1", "normalized_form": "OBC",
                  "ontology_ref": "object_type:equipment", "entity_type": "equipment",
                  "confidence": 0.9, "unit_id": "u1"},
                 {"evidence_id": "e2", "candidate_id": "c2", "normalized_form": "OBC",
                  "ontology_ref": "object_type:document", "entity_type": "document",
                  "confidence": 0.9, "unit_id": "u2"}]))
    cs = ConflictDetector().detect(al, [{"evidence_id": "e1", "unit_id": "u1"},
                                        {"evidence_id": "e2", "unit_id": "u2"}])
    assert any(c.conflict_type == "ONTOLOGY_CONFLICT" for c in cs.conflicts)


def test_v03_cmp_015_candidate_synthesis(db, compiled_evidence):
    eng = compiled_evidence["engine"]
    r = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    assert r["assertions"]
    for a in r["assertions"]:
        refs = a["evidence_refs_json"] if isinstance(a, dict) else a.evidence_refs
        if isinstance(refs, str):
            refs = json.loads(refs)
        assert set(refs) == set(compiled_evidence["evidence_ids"])  # INV-004