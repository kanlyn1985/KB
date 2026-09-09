# -*- coding: utf-8 -*-
"""CMP-006..010：治理边界（candidate-only/inferred/neutrality/provenance）。"""
from __future__ import annotations

import pytest

from agent_kb.evidence_core.compilation import (
    CompilationError,
    E_CANDIDATE_BUILD_FAILED,
    E_COMPILATION_PROVENANCE_MISSING,
    FakeSemanticCompilerProvider,
    RawExtraction,
    SemanticCompiler,
)
from agent_kb.evidence_core.state_machine import LEGAL_TRANSITIONS


def test_cmp_006_candidate_only(db, seeded, compiler):
    """V0.2 产物全部 candidate；不存在 validated/asserted；无治理跃迁。"""
    r = compiler.compile(seeded["evidence_id"], actor_id="system:compiler")
    assert r.assertions
    rows = db.execute(
        "SELECT status FROM akb_assertions WHERE subject_ref LIKE 'entity:%'").fetchall()
    assert all(row["status"] == "candidate" for row in rows)
    # 治理跃迁必须走 V0.1 transition（compiler 从不调用）
    a = r.assertions[0]
    r2 = compiler.compile(seeded["evidence_id"], actor_id="system:compiler")
    assert r2.idempotent_hit  # 重编译不触发任何状态变化
    assert db.execute("SELECT status FROM akb_assertions WHERE assertion_id=?",
                      (a.assertion_id,)).fetchone()["status"] == "candidate"


def test_cmp_007_inferred_requires_derivation(db, seeded):
    """inferred 无 derivation → E-CANDIDATE-BUILD-FAILED（INV-002）。"""
    from agent_kb.evidence_core.compilation.models import RawExtraction
    # 构造一个 assertion_type=inferred 的候选路径：用 provider 输出模拟 reasoner 标记
    bad = SemanticCompiler(db, provider=FakeSemanticCompilerProvider(
        result=RawExtraction(
            entities_raw=[{"surface_form": "OBC", "normalized_form": "OBC",
                           "entity_type": "equipment", "confidence": 0.9,
                           "source_span": [0, 3]},
                          {"surface_form": "85V", "normalized_form": "85V",
                           "entity_type": "parameter", "confidence": 0.9,
                           "source_span": [4, 7]}],
            relations_raw=[{"subject_surface": "OBC", "predicate": "has_parameter",
                            "object_surface": "85V", "confidence": 0.9,
                            "source_span": [4, 7]}]),
        pid="reasoner-fake"))
    # 模拟 inferred：直接用 builder 层校验（unit.extraction_method=reasoner: 前缀路径）
    from agent_kb.evidence_core.compilation.compiler import CandidateAssertionBuilder
    from agent_kb.evidence_core.assertions import AssertionStore
    builder = CandidateAssertionBuilder(AssertionStore(db))
    unit = type("U", (), {})()
    unit.unit_id = "su_x"
    unit.evidence_id = seeded["evidence_id"]
    unit.entity_candidates = [
        {"candidate_id": "ec_0001", "normalized_form": "OBC"},
        {"candidate_id": "ec_0002", "normalized_form": "85V"}]
    unit.relation_candidates = [
        {"subject_candidate_id": "ec_0001", "predicate_candidate": "has_parameter",
         "object_candidate_id": "ec_0002", "confidence": 0.9}]
    unit.extraction_method = "reasoner:fake"
    unit.ontology_mapping = None
    with pytest.raises(CompilationError, match="E-CANDIDATE-BUILD-FAILED"):
        builder.build(unit, actor_id="system:reasoner",
                      ontology_scope="o", quarantined=False)


def test_cmp_008_mapping_candidate_default(db, seeded, compiler):
    """mapping 默认 candidate（generic 无词表场景 ref=None 但不 quarantine）。"""
    r = compiler.compile(seeded["evidence_id"], actor_id="system:compiler")
    mappings = r.units[0].ontology_mapping["mappings"]
    assert all(m["mapping_status"] == "candidate" for m in mappings)


def test_cmp_009_provenance_eight_questions(db, seeded, compiler):
    r = compiler.compile(seeded["evidence_id"], actor_id="human:reviewer")
    a = r.assertions[0]
    tr = compiler.trace_assertion_compilation(a.assertion_id)
    run = tr["run"]
    assert run is not None
    assert tr["evidence"]["evidence_id"] == seeded["evidence_id"]
    assert run["compiler_version"] == "v02-compiler-1.0"
    assert run["provider_id"] == "builtin-rules"
    assert run["actor_id"] == "human:reviewer"
    assert run["policy_version"] == "policy:v0.2"
    assert run["ontology_version"] is None  # generic pack


def test_cmp_010_provider_neutrality_swap(db, seeded):
    """换 provider（builtin→fake）不改 Canonical 结构/表/assertion 语义。"""
    from agent_kb.evidence_core.compilation.models import RawExtraction
    fake = SemanticCompiler(db, provider=FakeSemanticCompilerProvider(
        result=RawExtraction(
            entities_raw=[{"surface_form": "OBC", "normalized_form": "OBC",
                           "entity_type": "equipment", "confidence": 0.9,
                           "source_span": [0, 3]},
                          {"surface_form": "100V", "normalized_form": "100V",
                           "entity_type": "parameter", "confidence": 0.9,
                           "source_span": [4, 8]}],
            relations_raw=[{"subject_surface": "OBC", "predicate": "has_parameter",
                            "object_surface": "100V", "confidence": 0.9,
                            "source_span": [4, 8]}]),
        pid="fake-provider"))
    r = fake.compile(seeded["evidence_id"], actor_id="system:compiler")
    assert r.assertions
    assert all(a.status == "candidate" for a in r.assertions)
    # 断言结构同款（subject_ref/predicate_ref/provenance 三件套），无 provider 字段泄漏
    a = r.assertions[0]
    canon = a.canonical()
    assert "provider" not in canon and "provider_id" not in canon
    # run 行 provider 记录在 run 表（审计），不在 assertion canonical
    run = fake.describe_run(r.run.run_id)
    assert run["provider_id"] == "fake-provider"