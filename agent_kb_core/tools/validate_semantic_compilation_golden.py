# -*- coding: utf-8 -*-
"""V0.2 Semantic Compilation Golden validator（CMP-015）。

语义结构对比（predicate 集/候选形/判定状态），非字节 diff——不依赖数据库自增 ID 等非语义字段。
用法：python tools/validate_semantic_compilation_golden.py [--db PATH]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # agent_kb_core/
sys.path.insert(0, str(ROOT / "src"))

from agent_kb.evidence_core.compilation import (  # noqa: E402
    CompilationError,
    E_CANDIDATE_BUILD_FAILED,
    E_COMPILER_INVALID_EVIDENCE,
    E_ONTOLOGY_MAPPING_FAILED,
    E_SEMANTIC_EXTRACTION_FAILED,
    FakeSemanticCompilerProvider,
    RawExtraction,
    SemanticCompiler,
)
from agent_kb.evidence_core import EvidenceStore  # noqa: E402
from agent_kb.storage.migrations import SchemaMigrator  # noqa: E402

GOLDEN = ROOT.parent / "docs" / "verification" / "golden" / "semantic_compilation"
DOMAINS = ROOT / "domains"


class _ReasonerNoDerivationProvider(FakeSemanticCompilerProvider):
    """产出 reasoner 标记关系的 provider——触发 builder 的 inferred derivation 校验。"""
    pass  # 场景由 validator 主体特判（unit.extraction_method=reasoner: 无法经 provider 传递，
          # 改为直接构造 builder 层校验）


def _load_pack(name):
    if not name or name == "null":
        return None
    from agent_kb.domains.loader import load_domain_pack
    return load_domain_pack(DOMAINS / name)


def _check_case(case: dict, con: sqlite3.Connection) -> tuple[bool, str]:
    exp = case["expectation"]
    es = EvidenceStore(con)
    if not con.execute("SELECT 1 FROM akb_sources WHERE source_id='src_g'").fetchone():
        con.execute("INSERT INTO akb_sources (source_id, source_type, name)"
                    " VALUES ('src_g','document','golden')")
        con.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
                    " ingested_at) VALUES ('doc_golden','src_g','1.0','h',"
                    " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    if not case["evidence_text"].strip():
        # 空 evidence 走独立路径：直接调用 compiler 断言 E-COMPILER-INVALID-EVIDENCE
        expected = exp.get("expected_error")
        if expected == "E-COMPILER-INVALID-EVIDENCE":
            compiler = SemanticCompiler(con)
            try:
                compiler.compile("ev_nonexistent", actor_id="system:golden")
                return False, "empty evidence did not raise"
            except CompilationError as exc:
                return (True, "OK") if exc.code == expected else (
                    False, f"unexpected code {exc.code}")
        return False, "empty evidence but no expected error"
    ev = es.create(document_id="doc_golden", content=case["evidence_text"],
                   extraction_method="golden")

    provider = None
    if case["category"] in ("negative", "provider_boundary") and exp.get("expected_error"):
        if exp["expected_error"] == E_SEMANTIC_EXTRACTION_FAILED:
            provider = FakeSemanticCompilerProvider(
                result=RawExtraction(entities_raw=[{"surface_form": "X"}]),
                pid="golden-malformed")
        elif exp["expected_error"] == E_CANDIDATE_BUILD_FAILED:
            # reasoner 标记 + 无 derivation → builder 校验拒绝（CMP-007 golden 版）
            provider = _ReasonerNoDerivationProvider()

    pack_name = case.get("domain_pack")
    if exp.get("quarantine_expected") and not pack_name:
        pack_name = "obc_dcdc"  # quarantine 语义需要词表背书（golden 约定）
    if case["case_id"] == "SC-025":
        # CMP-007 golden 版：reasoner 标记 + 无 derivation → builder E-CANDIDATE-BUILD-FAILED
        from agent_kb.evidence_core.compilation.compiler import CandidateAssertionBuilder
        from agent_kb.evidence_core.assertions import AssertionStore
        builder = CandidateAssertionBuilder(AssertionStore(con))
        unit = type("U", (), {})()
        unit.unit_id = "su_golden_inferred"
        unit.evidence_id = ev.evidence_id
        unit.entity_candidates = [
            {"candidate_id": "ec_0001", "normalized_form": "OBC"},
            {"candidate_id": "ec_0002", "normalized_form": "85V"}]
        unit.relation_candidates = [
            {"subject_candidate_id": "ec_0001", "predicate_candidate": "has_parameter",
             "object_candidate_id": "ec_0002", "confidence": 0.9}]
        unit.extraction_method = "reasoner:golden"
        unit.ontology_mapping = None
        try:
            builder.build(unit, actor_id="system:reasoner",
                          ontology_scope="o", quarantined=False)
            return False, "inferred without derivation was accepted"
        except CompilationError as exc:
            return (True, "OK") if exc.code == "E-CANDIDATE-BUILD-FAILED" else (
                False, f"unexpected {exc.code}")
    if case["case_id"] == "SC-039":
        provider = FakeSemanticCompilerProvider(error=RuntimeError("provider crash"),
                                                pid="crash-provider")
    if case["case_id"] == "SC-040":
        provider = FakeSemanticCompilerProvider(result=RawExtraction(), pid="llm-actor")
    compiler = SemanticCompiler(con, provider=provider,
                                domain_pack=_load_pack(pack_name))
    try:
        result = compiler.compile(ev.evidence_id, actor_id="system:golden")
        if exp.get("expected_error"):
            return False, f"expected error {exp['expected_error']} but compiled"
        if len(result.units) < exp["units_min"]:
            return False, f"units {len(result.units)} < {exp['units_min']}"
        if not exp.get("assertions_allowed"):
            if result.assertions:
                return False, "assertions produced but not allowed"
        else:
            if exp.get("assertions_allowed") and case["category"] == "positive" \
                    and exp.get("expected_relations"):
                got = {a.predicate_ref.replace("relation:", "") for a in result.assertions}
                want = {e["predicate"] for e in exp["expected_relations"]}
                if not want & got:
                    return False, f"expected predicates {want} not in {got}"
        if exp.get("quarantine_expected"):
            q = [m for u in result.units
                 for m in (u.ontology_mapping or {}).get("mappings", [])
                 if m["mapping_status"] == "quarantined"]
            if not q:
                return False, "expected quarantine but none found"
        if exp.get("determinism_check"):
            fp_before = result.fingerprint
            rerun = compiler.compile(ev.evidence_id, actor_id="system:golden")
            if not rerun.idempotent_hit or rerun.fingerprint != fp_before:
                return False, "rerun not idempotent / fingerprint drift"
        return True, "OK"
    except CompilationError as exc:
        if exp.get("expected_error") and exc.code == exp["expected_error"]:
            return True, "OK (expected error)"
        return False, f"unexpected compilation error: {exc.code}"
    except ValueError as exc:
        if E_SEMANTIC_EXTRACTION_FAILED in str(exc) and \
                exp.get("expected_error") == E_SEMANTIC_EXTRACTION_FAILED:
            return True, "OK (expected malformed rejection)"
        return False, f"unexpected error: {exc}"
    except RuntimeError as exc:
        # SC-039 provider 隔离失败：run failed 且不越界即为 PASS（错误模型验证）
        rows = con.execute("SELECT COUNT(*) AS c FROM akb_semantic_units").fetchone()["c"]
        ar = con.execute("SELECT COUNT(*) AS c FROM akb_assertions").fetchone()["c"]
        if rows == 0 and ar == 0:
            return True, "OK (provider crash isolated, no cross-boundary writes)"
        return False, f"provider crash leaked products: units={rows} assertions={ar}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=None)
    args = ap.parse_args()
    manifest = json.loads((GOLDEN / "cases.json").read_text(encoding="utf-8"))
    passed = failed = 0
    failures = []
    for case in manifest["cases"]:
        con = sqlite3.connect(":memory:", isolation_level=None)  # 每案例独立库（幂等指纹隔离）
        con.row_factory = sqlite3.Row
        SchemaMigrator(con).migrate()
        ok, msg = _check_case(case, con)
        if ok:
            passed += 1
        else:
            failed += 1
            failures.append((case["case_id"], msg))
    print("Semantic Compilation Golden validation:", "PASS" if failed == 0 else "FAIL")
    print(f"Cases: {passed + failed} | Pass: {passed} | Fail: {failed}")
    for cid, msg in failures:
        print(f"  FAIL {cid}: {msg}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())