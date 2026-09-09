# -*- coding: utf-8 -*-
"""CMP-001..005：编译链基础（unit 产出/断言候选/幂等/版本/Evidence immutable）。"""
from __future__ import annotations

import pytest

from agent_kb.evidence_core.compilation import (
    CompilationError,
    E_CANDIDATE_BUILD_FAILED,
    SemanticCompiler,
    compilation_fingerprint,
)


def test_cmp_001_evidence_to_unit(db, seeded, compiler):
    r = compiler.compile(seeded["evidence_id"], actor_id="system:compiler")
    assert len(r.units) >= 1
    u = r.units[0]
    assert u.normalized_text and u.extraction_method == "compiler:builtin-rules"
    assert u.entity_candidates and u.relation_candidates
    row = db.execute("SELECT * FROM akb_semantic_units WHERE unit_id=?",
                     (u.unit_id,)).fetchone()
    assert row is not None and row["compiler_run_ref"] == r.run.run_id


def test_cmp_002_unit_to_candidate_assertion(db, seeded, compiler):
    r = compiler.compile(seeded["evidence_id"], actor_id="system:compiler")
    assert r.assertions, "expected candidate assertions from compiled unit"
    for a in r.assertions:
        assert a.status == "candidate"
        assert a.evidence_refs == [seeded["evidence_id"]]
        assert a.subject_ref.startswith("entity:")
        assert a.provenance_ref


def test_cmp_003_idempotent_recompile(seeded, compiler):
    r1 = compiler.compile(seeded["evidence_id"], actor_id="system:compiler")
    r2 = compiler.compile(seeded["evidence_id"], actor_id="system:compiler")
    assert r2.idempotent_hit is True
    assert len(r2.units) == len(r1.units)  # 不产生重复 unit
    assert len(r2.assertions) == len(r1.assertions)


def test_cmp_004_version_distinguishes_fingerprint(seeded, db):
    c1 = SemanticCompiler(db, compiler_version="v02-compiler-1.0")
    r1 = c1.compile(seeded["evidence_id"], actor_id="system:compiler")
    c2 = SemanticCompiler(db, compiler_version="v02-compiler-2.0")
    r2 = c2.compile(seeded["evidence_id"], actor_id="system:compiler")
    assert not r2.idempotent_hit
    assert r2.fingerprint != r1.fingerprint
    assert len(r2.units) >= 1  # 新版本新 unit（旧产物不动）


def test_cmp_005_evidence_immutable(db, seeded, compiler):
    before = db.execute("SELECT * FROM akb_evidence WHERE evidence_id=?",
                        (seeded["evidence_id"],)).fetchone()
    compiler.compile(seeded["evidence_id"], actor_id="system:compiler")
    after = db.execute("SELECT * FROM akb_evidence WHERE evidence_id=?",
                       (seeded["evidence_id"],)).fetchone()
    assert dict(before) == dict(after)
    # append-only 兜底仍生效
    import sqlite3
    with pytest.raises(sqlite3.Error, match="append-only"):
        db.execute("UPDATE akb_evidence SET content='tampered' WHERE evidence_id=?",
                   (seeded["evidence_id"],))


def test_cmp_005b_invalid_evidence_rejected(db):
    c = SemanticCompiler(db)
    with pytest.raises(CompilationError) as ei:
        c.compile("ev_ghost", actor_id="system:compiler")
    assert ei.value.code == "E-COMPILER-INVALID-EVIDENCE"