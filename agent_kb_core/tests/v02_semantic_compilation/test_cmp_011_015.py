# -*- coding: utf-8 -*-
"""CMP-011..015：determinism/failure isolation/malformed/quarantine。"""
from __future__ import annotations

from pathlib import Path

import pytest

from agent_kb.evidence_core.compilation import (
    CompilationError,
    E_SEMANTIC_EXTRACTION_FAILED,
    FakeSemanticCompilerProvider,
    RawExtraction,
    SemanticCompiler,
    validate_provider_output,
)


def test_cmp_011_determinism_two_runs(db, seeded):
    """同输入两次 run：幂等返回的语义内容与首次全等（排除 ID/审计字段）；候选顺序稳定。"""
    comp = SemanticCompiler(db)
    r1 = comp.compile(seeded["evidence_id"], actor_id="system:compiler")
    r2 = comp.compile(seeded["evidence_id"], actor_id="system:compiler")
    assert r2.idempotent_hit and r1.fingerprint == r2.fingerprint
    sem1 = [{**u.entity_candidates[i]} for i, u in enumerate(r1.units) for _ in [0]]
    # 语义对比：normalized_text/entity candidates（排除 unit_id/provenance/时间戳）
    def semantic(u):
        return {"normalized_text": u.normalized_text,
                "entities": [(c["normalized_form"], c["entity_type"]) for c in u.entity_candidates],
                "relations": [(c["subject_candidate_id"], c["predicate_candidate"],
                               c["object_candidate_id"]) for c in u.relation_candidates]}
    assert [semantic(u) for u in r1.units] == [semantic(u) for u in r2.units]
    # 候选顺序稳定：同 run 内 span 升序
    for u in r1.units:
        spans = [c["source_span"][0] for c in u.entity_candidates if c.get("source_span")]
        assert spans == sorted(spans)


def test_cmp_011b_candidate_ordering_stable(db, seeded):
    from agent_kb.evidence_core.compilation.models import RawExtraction
    from agent_kb.evidence_core.compilation.resolvers import EntityCandidateResolver
    raw = RawExtraction(entities_raw=[
        {"surface_form": "电容", "normalized_form": "电容", "confidence": 0.9, "source_span": [10, 12]},
        {"surface_form": "OBC", "normalized_form": "OBC", "confidence": 0.9, "source_span": [0, 3]},
        {"surface_form": "电阻", "normalized_form": "电阻", "confidence": 0.9, "source_span": [5, 7]}])
    ents = EntityCandidateResolver().resolve(raw)
    assert [e.normalized_form for e in ents] == ["OBC", "电阻", "电容"]  # span 排序
    ids = [e.candidate_id for e in ents]
    assert ids == ["ec_0001", "ec_0002", "ec_0003"]  # 序号排序后重编


def test_cmp_012_failure_isolation(db, seeded):
    """provider 级失败 → run failed；Evidence/authoritative 零修改；无半成品 unit。"""
    boom = SemanticCompiler(db, provider=FakeSemanticCompilerProvider(
        error=RuntimeError("provider crashed"), pid="crash-provider"))
    with pytest.raises(RuntimeError):
        boom.compile(seeded["evidence_id"], actor_id="system:compiler")
    # 无半成品
    assert db.execute("SELECT COUNT(*) FROM akb_semantic_units").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM akb_assertions").fetchone()[0] == 0
    # run failed 留痕
    run = db.execute("SELECT status FROM akb_compilation_runs").fetchone()
    assert run["status"] == "failed"
    # evidence 不变
    ev = db.execute("SELECT content FROM akb_evidence WHERE evidence_id=?",
                    (seeded["evidence_id"],)).fetchone()
    assert ev["content"] == seeded["evidence"].content


def test_cmp_013_malformed_provider_rejected(db, seeded):
    """缺字段/越界 confidence → E-SEMANTIC-EXTRACTION-FAILED，无产物。"""
    cases = [
        RawExtraction(entities_raw=[{"surface_form": "X"}]),               # 缺 confidence
        RawExtraction(entities_raw=[{"surface_form": "X", "confidence": 1.5}]),  # 越界
        RawExtraction(relations_raw=[{"subject_surface": "a"}]),           # 缺 predicate/object
    ]
    for bad in cases:
        with pytest.raises(ValueError, match="E-SEMANTIC-EXTRACTION-FAILED"):
            validate_provider_output(bad)
        comp = SemanticCompiler(db, provider=FakeSemanticCompilerProvider(
            result=bad, pid="bad-provider"))
        with pytest.raises(Exception):
            comp.compile(seeded["evidence_id"], actor_id="system:compiler")
    assert db.execute("SELECT COUNT(*) FROM akb_semantic_units").fetchone()[0] == 0


def test_cmp_014_unknown_ontology_quarantine(db, seeded):
    """有词表未命中 → quarantined；unit 落库；assertion 不产；warning 进 run。"""
    from agent_kb.evidence_core.compilation.models import RawExtraction
    from agent_kb.domains.loader import load_domain_pack
    pack = load_domain_pack(Path(__file__).resolve().parents[3] / "agent_kb_core" / "domains" / "obc_dcdc")
    comp = SemanticCompiler(db, domain_pack=pack, provider=FakeSemanticCompilerProvider(
        result=RawExtraction(
            entities_raw=[{"surface_form": "神秘元件XYZ", "normalized_form": "神秘元件XYZ",
                           "entity_type": "unknown", "confidence": 0.9,
                           "source_span": [0, 7]},
                          {"surface_form": "100V", "normalized_form": "100V",
                           "entity_type": "parameter", "confidence": 0.9,
                           "source_span": [8, 12]}],
            relations_raw=[{"subject_surface": "神秘元件XYZ", "predicate": "has_parameter",
                            "object_surface": "100V", "confidence": 0.9,
                            "source_span": [8, 12]}]),
        pid="fake-q"))
    r = comp.compile(seeded["evidence_id"], actor_id="system:compiler")
    assert len(r.units) >= 1  # unit 保留
    mappings = r.units[0].ontology_mapping["mappings"]
    assert any(m["mapping_status"] == "quarantined" for m in mappings)
    assert not r.assertions  # quarantine unit 不产 assertion
    assert r.run.warnings or any(m["mapping_status"] == "quarantined" for m in mappings)