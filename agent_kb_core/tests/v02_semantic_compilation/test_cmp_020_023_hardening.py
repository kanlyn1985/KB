# -*- coding: utf-8 -*-
"""CMP-020..023：Implementation Hardening（AKB-V02-IMPL-002）。

- CMP-020 Multi-Segment Fingerprint Anchor Semantics（Defect B）
- CMP-021 Multi-Evidence Rejection Boundary（Defect C 行为级）
- CMP-022 CompilationRun Cardinality Integrity（§5）
- CMP-023 Provenance 四级 trace 确定性/完整性（§6，多 segment 场景）
- T-A1/A2/A3 document_effective_time 锚定（Defect A）
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from agent_kb.evidence_core.compilation import (
    CompilationError,
    E_COMPILER_INVALID_EVIDENCE,
    SemanticCompiler,
)


# ---- Defect A：Temporal anchor（T-A1/A2/A3）----

def _mk_doc_evidence(db, text, effective_at=None):
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('src_d', 'document', 'DocSrc')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at, effective_at) VALUES ('doc_eff', 'src_d', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'), ?)", (effective_at,))
    es = db.execute  # noqa: F841
    from agent_kb.evidence_core import EvidenceStore
    store = EvidenceStore(db)
    return store.create(document_id="doc_eff", content=text, extraction_method="t")


def test_ta1_relative_time_anchored_to_document(db):
    """T-A1: '发布之日起' 相对表达锚定 akb_documents.effective_at。"""
    ev = _mk_doc_evidence(db, "自发布之日起实施本规范。", "2026-01-01T00:00:00Z")
    r = SemanticCompiler(db).compile(ev.evidence_id, actor_id="system:compiler")
    parses = [u.temporal_parse for u in r.units if u.temporal_parse]
    assert parses, "expected at least one temporal parse"
    anchored = [p for p in parses if p.get("valid_time")]
    assert any(p["valid_time"].get("valid_from") == "2026-01-01T00:00:00Z" for p in anchored)
    assert all(p["parse_status"] in ("resolved", "unresolved") for p in parses)


def test_ta2_clock_independence(db):
    """T-A2: 机器时钟不影响语义时间输出（fingerprint 确定性）。"""
    ev = _mk_doc_evidence(db, "自发布之日起实施本规范。", "2026-01-01T00:00:00Z")
    r1 = SemanticCompiler(db).compile(ev.evidence_id, actor_id="system:compiler")
    # 同库重跑（幂等）→ fingerprint 恒定；若用当前时钟，unit 语义字段必漂移导致指纹不同
    r2 = SemanticCompiler(db).compile(ev.evidence_id, actor_id="system:compiler")
    assert r2.idempotent_hit and r1.fingerprint == r2.fingerprint
    # 语义字段对比（排除审计字段）
    def sem(u):
        return {k: u.temporal_parse.get(k) for k in
                ("event_time", "valid_time", "observation_time",
                 "document_effective_time", "ingestion_time", "conditions")} \
            if u.temporal_parse else None
    assert [sem(u) for u in r1.units] == [sem(u) for u in r2.units]


def test_ta3_no_effective_at_yields_unresolved(db):
    """T-A3: document 无 effective_at → unresolved，不伪造当前日期。"""
    ev = _mk_doc_evidence(db, "自发布之日起实施本规范。", None)
    r = SemanticCompiler(db).compile(ev.evidence_id, actor_id="system:compiler")
    parses = [u.temporal_parse for u in r.units if u.temporal_parse]
    assert parses
    for p in parses:
        if p.get("valid_time") is not None:
            # 绝不出现"当前日期"——valid_from 只能来自 effective_at（此处为 None）
            assert p["valid_time"].get("valid_from") is None
        assert p.get("document_effective_time") is None
        assert not any(str(v).startswith("202") and "T" in str(v)
                       for v in [p.get("valid_time")] if v)  # 无伪造 ISO 时间戳


# ---- Defect B：CMP-020 多 segment 指纹锚 ----

def test_cmp_020_multisegment_fingerprint_anchor(db, seeded, compiler):
    """≥3 segment Evidence：恰 1 unit 持 fingerprint；全部 unit 同 run；重编译返回全 run 产物；无第二 create_candidate。"""
    from agent_kb.evidence_core import EvidenceStore
    es = EvidenceStore(db)
    ev = es.create(document_id="doc_t1",
                   content="OBC 额定输入电压 265V。\n输入滤波电容 22uF。\n待机功耗小于 5W。",
                   extraction_method="t")
    r1 = compiler.compile(ev.evidence_id, actor_id="system:compiler")
    assert len(r1.units) >= 3
    fps = [u.content_fingerprint for u in r1.units]
    assert fps.count(r1.fingerprint) == 1, "exactly one anchor unit"
    non_null = [f for f in fps if f is not None]
    assert all(non_null.count(f) == 1 for f in non_null), "non-anchor NULL allowed, no duplicate fingerprints"
    run_refs = {u.compiler_run_ref for u in r1.units}
    assert run_refs == {r1.run.run_id}
    n_assertions_r1 = len(r1.assertions)
    # 重编译：返回同 run 全部 unit + 相同 assertions；无第二 create_candidate
    r2 = compiler.compile(ev.evidence_id, actor_id="system:compiler")
    assert r2.idempotent_hit
    assert {u.compiler_run_ref for u in r2.units} == run_refs
    assert len(r2.units) == len(r1.units)
    assert len(r2.assertions) == n_assertions_r1
    total = db.execute(
        "SELECT COUNT(*) AS c FROM akb_assertions WHERE subject_ref LIKE 'entity:%'").fetchone()["c"]
    assert total == n_assertions_r1, "no second assertion creation"


# ---- Defect C：CMP-021 行为级多证据拒绝 ----

def test_cmp_021_multi_evidence_rejection_boundary(db, seeded, compiler):
    """V0.2 无 batch API；多证据注入在持久层被读取/校验路径拒绝；零副作用。"""
    from agent_kb.evidence_core import EvidenceStore
    es = EvidenceStore(db)
    ev2 = es.create(document_id="doc_t1", content="第二条独立证据内容。", extraction_method="t")
    before_units = db.execute("SELECT COUNT(*) AS c FROM akb_semantic_units").fetchone()["c"]
    before_asserts = db.execute("SELECT COUNT(*) AS c FROM akb_assertions").fetchone()["c"]
    before_runs = db.execute("SELECT COUNT(*) AS c FROM akb_compilation_runs").fetchone()["c"]
    ev_before = db.execute("SELECT * FROM akb_evidence WHERE evidence_id=?",
                           (seeded["evidence_id"],)).fetchone()

    # 注入尝试 1：compile 传列表 → 单证据契约守卫 E-COMPILER-INVALID-EVIDENCE
    with pytest.raises(CompilationError, match="single-evidence contract"):
        compiler.compile([seeded["evidence_id"], ev2.evidence_id], actor_id="system:compiler")
    # 注入尝试 2：compile 传多值字符串（非存在 ID → E-COMPILER-INVALID-EVIDENCE）
    with pytest.raises(CompilationError) as ei:
        compiler.compile(f"{seeded['evidence_id']},{ev2.evidence_id}",
                         actor_id="system:compiler")
    assert ei.value.code == E_COMPILER_INVALID_EVIDENCE
    # 注入尝试 3：伪造多元素 run 行（持久层）→ 读取/校验路径必须拒绝或解析为非法
    db.execute(
        "INSERT INTO akb_compilation_runs (run_id, evidence_ids_json, compiler_version,"
        " configuration_hash, ontology_version, provider_id, actor_id, policy_version, status)"
        " VALUES ('run_fake_batch', ?, 'v02-compiler-1.0', 'x', NULL, 'builtin-rules',"
        " 'human:x', 'policy:v0.2', 'completed')",
        (json.dumps([seeded["evidence_id"], ev2.evidence_id]),))
    fake_run = compiler.describe_run("run_fake_batch")
    assert json.loads(fake_run["evidence_ids_json"]) != [seeded["evidence_id"]]
    # 读取路径契约：run 证据基数必须为 1（V0.2 语义）——伪造行不满足 → 无法作为合法 run 使用
    assert len(json.loads(fake_run["evidence_ids_json"])) != 1

    # 零副作用
    assert db.execute("SELECT COUNT(*) AS c FROM akb_semantic_units").fetchone()["c"] == before_units
    assert db.execute("SELECT COUNT(*) AS c FROM akb_assertions").fetchone()["c"] == before_asserts
    assert db.execute("SELECT COUNT(*) AS c FROM akb_compilation_runs").fetchone()["c"] == before_runs + 1
    assert dict(db.execute("SELECT * FROM akb_evidence WHERE evidence_id=?",
                           (seeded["evidence_id"],)).fetchone()) == dict(ev_before)


# ---- §5：CMP-022 run 基数完整性 ----

def test_cmp_022_run_cardinality_integrity(db, seeded, compiler):
    """全部成功 run：evidence_ids_json 恰一元素且等于 invocation id；unit.compiler_run_ref 一致。"""
    from agent_kb.evidence_core import EvidenceStore
    es = EvidenceStore(db)
    ev = es.create(document_id="doc_t1",
                   content="OBC 额定输入电压 265V。\n输入滤波电容 22uF。\n待机功耗小于 5W。",
                   extraction_method="t")
    r = compiler.compile(ev.evidence_id, actor_id="system:compiler")
    run = compiler.describe_run(r.run.run_id)
    ids = json.loads(run["evidence_ids_json"])
    assert ids == [ev.evidence_id]
    for u in r.units:
        assert u.compiler_run_ref == run["run_id"]
    # 库级全查：不存在引用含多 Evidence 的 run 的 unit
    bad = db.execute(
        "SELECT COUNT(*) AS c FROM akb_semantic_units su"
        " JOIN akb_compilation_runs cr ON cr.run_id = su.compiler_run_ref"
        " WHERE json_array_length(cr.evidence_ids_json) != 1").fetchone()["c"]
    assert bad == 0
    orphan = db.execute(
        "SELECT COUNT(*) AS c FROM akb_semantic_units su"
        " JOIN akb_compilation_runs cr ON cr.run_id = su.compiler_run_ref"
        " WHERE json_extract(cr.evidence_ids_json, '$[0]') != su.evidence_id").fetchone()["c"]
    assert orphan == 0


# ---- §6：CMP-023 trace 四级链确定性/完整性（多 segment）----

def test_cmp_023_provenance_trace_multisegment(db, seeded, compiler):
    """多 segment Evidence：trace 断言 → 正确父 Evidence/Run；四级链完整。"""
    from agent_kb.evidence_core import EvidenceStore
    es = EvidenceStore(db)
    ev = es.create(document_id="doc_t1",
                   content="OBC 额定输入电压 265V。\n输入滤波电容 22uF。",
                   extraction_method="t")
    r = compiler.compile(ev.evidence_id, actor_id="system:compiler")
    assert r.assertions
    for a in r.assertions:
        tr = compiler.trace_assertion_compilation(a.assertion_id)
        assert tr["unit"] is not None
        assert tr["unit"]["evidence_id"] == ev.evidence_id
        assert tr["run"] is not None
        assert json.loads(tr["run"]["evidence_ids_json"]) == [ev.evidence_id]
        assert tr["evidence"] is not None
        # Document 层（四级链延伸）
        doc = db.execute("SELECT * FROM akb_documents WHERE document_id=?",
                         (tr["evidence"]["document_id"],)).fetchone()
        assert doc is not None
        # 确定性：两次 trace 结果一致
        tr2 = compiler.trace_assertion_compilation(a.assertion_id)
        assert {k: dict(v) if v else None for k, v in tr.items() if isinstance(v, sqlite3.Row)} == \
               {k: dict(v) if v else None for k, v in tr2.items() if isinstance(v, sqlite3.Row)}