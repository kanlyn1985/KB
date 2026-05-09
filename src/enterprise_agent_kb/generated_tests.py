from __future__ import annotations

import html
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from .answer_api import answer_query
from .closed_loop_store import load_golden_cases_from_file, record_eval_run, sync_golden_cases
from .config import AppPaths
from .coverage import build_coverage_for_document, build_test_gap_candidates_for_document
from .answer_quality import evaluate_answer_quality
from .db import connect
from .query_api import build_query_context
from .retrieval_quality import evaluate_retrieval_quality


NETWORK_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
MIN_CASE_COUNT = 20
MAX_CASE_COUNT = 220

QUERY_REPAIR_SMOKE_CASES: list[dict[str, object]] = [
    {
        "query": "软件架构分析有哪些活动",
        "must_include": "SWE.2.BP3",
        "assert_mode": "rich_answer",
        "expected_evidence_shape": "process_activity",
        "source": "query_repair_smoke",
    },
    {
        "query": "软件架构设计有哪些活动要做",
        "must_include": "SWE.2.BP2",
        "assert_mode": "rich_answer",
        "expected_evidence_shape": "process_activity",
        "source": "query_repair_smoke",
    },
    {
        "query": "系统集成测试过程域有哪些活动",
        "must_include": "SYS.4.BP1",
        "assert_mode": "rich_answer",
        "expected_evidence_shape": "process_activity",
        "source": "query_repair_smoke",
    },
    {
        "query": "CC电阻有哪些定义",
        "must_include": "CC阻值",
        "retrieval_must_hit": ["CC", "等效电阻"],
        "assert_mode": "rich_answer",
        "expected_evidence_shape": "parameter_definition",
        "source": "query_repair_smoke",
    },
    {
        "query": "cp 9V PWM是什么意思",
        "must_include": "9V 且输出 PWM",
        "assert_mode": "rich_answer",
        "expected_evidence_shape": "parameter_definition",
        "source": "query_repair_smoke",
    },
    {
        "query": "CP的时序是什么样的",
        "must_include": "表 A.7",
        "assert_mode": "rich_answer",
        "expected_evidence_shape": "timing_table",
        "source": "query_repair_smoke",
    },
]


def generate_coverage_test_drafts_for_document(
    workspace_root: Path,
    doc_id: str,
    *,
    limit: int | None = 50,
    rebuild_coverage: bool = False,
    validate: bool = False,
) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    tests_dir = paths.root.parent / "tests" / "generated"
    tests_dir.mkdir(parents=True, exist_ok=True)

    gap_result = build_test_gap_candidates_for_document(
        workspace_root,
        doc_id,
        limit=limit,
        rebuild=rebuild_coverage,
    )
    gap_payload = json.loads(gap_result.candidates_path.read_text(encoding="utf-8"))
    cases = [_draft_case_from_gap_candidate(item, doc_id) for item in gap_payload.get("items", []) if isinstance(item, dict)]
    if validate:
        for case in cases:
            case["validation_status"] = "passed" if _validate_case(workspace_root, case["golden_case"]) else "failed"
    else:
        for case in cases:
            case["validation_status"] = "not_validated"

    json_path = tests_dir / f"{doc_id}.coverage_test_drafts.json"
    report_path = tests_dir / f"{doc_id}.coverage_test_drafts.md"
    payload = {
        "doc_id": doc_id,
        "source": "coverage_u3_not_tested",
        "candidate_count": gap_payload.get("candidate_count", len(cases)),
        "source_gap_count": gap_payload.get("source_gap_count", len(cases)),
        "skipped_candidate_count": gap_payload.get("skipped_candidate_count", 0),
        "draft_case_count": len(cases),
        "validated": validate,
        "coverage_candidates_path": str(gap_result.candidates_path),
        "coverage_candidates_report_path": str(gap_result.report_path),
        "cases": cases,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(_render_coverage_test_draft_report(payload), encoding="utf-8")
    return {
        **payload,
        "json_path": str(json_path),
        "report_path": str(report_path),
    }


def validate_coverage_test_drafts_for_document(
    workspace_root: Path,
    doc_id: str,
    *,
    mode: str = "trace",
) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    tests_dir = paths.root.parent / "tests" / "generated"
    draft_path = tests_dir / f"{doc_id}.coverage_test_drafts.json"
    if not draft_path.exists():
        raise ValueError(f"coverage test drafts not found: {draft_path}")

    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    cases = [case for case in payload.get("cases", []) if isinstance(case, dict)]
    for case in cases:
        golden_case = case.get("golden_case")
        if isinstance(golden_case, dict):
            golden_case.setdefault("target_doc_id", doc_id)
        if isinstance(golden_case, dict) and _validate_draft_golden_case(workspace_root, golden_case, mode):
            case["validation_status"] = "passed"
        else:
            case["validation_status"] = "failed"

    payload["cases"] = cases
    payload["validated"] = True
    payload["validation_mode"] = mode
    payload["passed_count"] = sum(1 for case in cases if case.get("validation_status") == "passed")
    payload["failed_count"] = sum(1 for case in cases if case.get("validation_status") == "failed")
    report_path = tests_dir / f"{doc_id}.coverage_test_drafts.md"
    draft_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(_render_coverage_test_draft_report(payload), encoding="utf-8")
    return {
        **payload,
        "json_path": str(draft_path),
        "report_path": str(report_path),
    }


def assess_coverage_test_draft_readiness_for_document(
    workspace_root: Path,
    doc_id: str,
) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    tests_dir = paths.root.parent / "tests" / "generated"
    draft_path = tests_dir / f"{doc_id}.coverage_test_drafts.json"
    if not draft_path.exists():
        raise ValueError(f"coverage test drafts not found: {draft_path}")

    draft_payload = json.loads(draft_path.read_text(encoding="utf-8"))
    cases = [case for case in draft_payload.get("cases", []) if isinstance(case, dict)]
    assessed_cases = [_assess_draft_case_readiness(case) for case in cases]
    status_counts = _count_by_key(assessed_cases, "readiness_status")
    flag_counts: dict[str, int] = {}
    for case in assessed_cases:
        for flag in case.get("quality_flags", []):
            flag_counts[str(flag)] = flag_counts.get(str(flag), 0) + 1

    payload = {
        "doc_id": doc_id,
        "draft_case_count": len(cases),
        "status_counts": status_counts,
        "flag_counts": dict(sorted(flag_counts.items())),
        "source_draft_path": str(draft_path),
        "cases": assessed_cases,
    }
    json_path = tests_dir / f"{doc_id}.coverage_test_draft_readiness.json"
    report_path = tests_dir / f"{doc_id}.coverage_test_draft_readiness.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(_render_coverage_test_draft_readiness_report(payload), encoding="utf-8")
    return {
        **payload,
        "json_path": str(json_path),
        "report_path": str(report_path),
    }


def assess_all_coverage_test_draft_readiness(
    workspace_root: Path,
    *,
    output_dir: Path | None = None,
) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    tests_dir = paths.root.parent / "tests" / "generated"
    report_dir = output_dir or tests_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    documents = _active_document_ids(paths)
    document_results: list[dict[str, object]] = []
    total_status_counts: dict[str, int] = {}
    total_flag_counts: dict[str, int] = {}
    missing_draft_docs: list[str] = []

    for doc_id in documents:
        draft_path = tests_dir / f"{doc_id}.coverage_test_drafts.json"
        if not draft_path.exists():
            missing_draft_docs.append(doc_id)
            continue
        result = assess_coverage_test_draft_readiness_for_document(workspace_root, doc_id)
        document_results.append(
            {
                "doc_id": doc_id,
                "draft_case_count": result["draft_case_count"],
                "status_counts": result["status_counts"],
                "flag_counts": result["flag_counts"],
                "json_path": result["json_path"],
                "report_path": result["report_path"],
            }
        )
        for key, value in dict(result["status_counts"]).items():
            total_status_counts[str(key)] = total_status_counts.get(str(key), 0) + int(value)
        for key, value in dict(result["flag_counts"]).items():
            total_flag_counts[str(key)] = total_flag_counts.get(str(key), 0) + int(value)

    payload = {
        "document_count": len(documents),
        "assessed_document_count": len(document_results),
        "missing_draft_docs": missing_draft_docs,
        "status_counts": dict(sorted(total_status_counts.items())),
        "flag_counts": dict(sorted(total_flag_counts.items())),
        "documents": document_results,
    }
    json_path = report_dir / "all_docs_coverage_test_draft_readiness_2026-04-26.json"
    report_path = report_dir / "all_docs_coverage_test_draft_readiness_2026-04-26.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(_render_all_coverage_test_draft_readiness_report(payload), encoding="utf-8")
    return {
        **payload,
        "json_path": str(json_path),
        "report_path": str(report_path),
    }


def promote_coverage_test_drafts_for_document(
    workspace_root: Path,
    doc_id: str,
    *,
    require_validated: bool = True,
) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    tests_dir = paths.root.parent / "tests" / "generated"
    draft_path = tests_dir / f"{doc_id}.coverage_test_drafts.json"
    if not draft_path.exists():
        raise ValueError(f"coverage test drafts not found: {draft_path}")

    draft_payload = json.loads(draft_path.read_text(encoding="utf-8"))
    if require_validated and not draft_payload.get("validated"):
        raise ValueError("coverage test drafts must be validated before promotion")

    promoted_cases = _promotable_draft_cases(draft_payload)
    golden_path = tests_dir / f"{doc_id}.golden.json"
    golden_payload = _load_or_create_golden_payload(paths, doc_id, golden_path)
    existing_cases = [case for case in golden_payload.get("cases", []) if isinstance(case, dict)]
    merged_cases = _dedupe_cases([*existing_cases, *promoted_cases])
    added_count = len(merged_cases) - len(_dedupe_cases(existing_cases))
    golden_payload["cases"] = merged_cases
    golden_payload["coverage_promoted_case_count"] = sum(1 for case in merged_cases if case.get("source") == "coverage")
    golden_path.write_text(json.dumps(golden_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    safe_doc_id = _safe_identifier(doc_id.lower())
    py_path = tests_dir / f"test_{safe_doc_id}_golden.py"
    py_path.write_text(_render_pytest_file(doc_id, merged_cases), encoding="utf-8")
    connection = connect(paths.db_file)
    try:
        sync_golden_cases(connection, doc_id, merged_cases)
        connection.commit()
    finally:
        connection.close()

    return {
        "doc_id": doc_id,
        "promoted_case_count": len(promoted_cases),
        "added_case_count": added_count,
        "total_case_count": len(merged_cases),
        "json_path": str(golden_path),
        "pytest_path": str(py_path),
        "draft_path": str(draft_path),
    }


def generate_golden_tests_for_document(
    workspace_root: Path,
    doc_id: str,
    *,
    validate_cases: bool = True,
    include_network: bool = True,
) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    tests_dir = paths.root.parent / "tests" / "generated"
    tests_dir.mkdir(parents=True, exist_ok=True)

    try:
        document = connection.execute(
            """
            SELECT doc_id, source_filename, page_count
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        if document is None:
            raise ValueError(f"document not found: {doc_id}")

        facts = connection.execute(
            """
            SELECT fact_type, predicate, object_value, qualifiers_json
            FROM facts
            WHERE source_doc_id = ?
            ORDER BY fact_id
            """,
            (doc_id,),
        ).fetchall()
        evidence_rows = connection.execute(
            """
            SELECT page_no, normalized_text, confidence
            FROM evidence
            WHERE doc_id = ?
            ORDER BY page_no, evidence_id
            """,
            (doc_id,),
        ).fetchall()
        wiki_rows = connection.execute(
            """
            SELECT page_type, title, slug
            FROM wiki_pages
            WHERE json_extract(source_doc_ids_json, '$[0]') = ?
            ORDER BY page_id
            """,
            (doc_id,),
        ).fetchall()

        target_case_count = _target_case_count(
            int(document["page_count"] or 0),
            len(facts),
            len(evidence_rows),
        )

        local_context = _build_local_context(document, facts, evidence_rows, wiki_rows)
        network_target = min(target_case_count, max(8, math.ceil(target_case_count * 0.6)))
        network_cases = _build_network_cases(local_context, network_target) if include_network else []
        network_candidate_count = len(network_cases)
        local_cases = _build_local_cases(local_context, target_case_count * 2)
        supplemental_cases = _build_local_cases(local_context, target_case_count * 3, extra_round=True)
        rq_target = max(5, math.ceil(target_case_count * 0.3))
        retrieval_quality_cases = _build_retrieval_quality_cases(local_context, rq_target)
        aq_target = max(3, math.ceil(target_case_count * 0.1))
        answer_quality_cases = _build_answer_quality_cases(local_context, aq_target)

        candidate_pool = _dedupe_cases([*retrieval_quality_cases, *answer_quality_cases, *network_cases, *local_cases, *supplemental_cases])
        cases = (
            _select_validated_cases(workspace_root, candidate_pool, target_case_count)
            if validate_cases
            else _select_cases_without_validation(candidate_pool, target_case_count)
        )
        if len(cases) < MIN_CASE_COUNT:
            extra_candidates = _dedupe_cases([*candidate_pool, *_build_last_resort_cases(local_context)])
            cases = (
                _select_validated_cases(workspace_root, extra_candidates, MIN_CASE_COUNT)
                if validate_cases
                else _select_cases_without_validation(extra_candidates, MIN_CASE_COUNT)
            )
        for case in cases:
            case["target_doc_id"] = doc_id
        if not validate_cases:
            cases = [case for case in cases if _validate_case_source_trace(workspace_root, case)]

        coverage = _page_coverage_summary(local_context, cases)

        json_path = tests_dir / f"{doc_id}.golden.json"
        json_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "source_filename": document["source_filename"],
                    "page_count": document["page_count"],
                    "target_case_count": target_case_count,
                    "validated_during_generation": validate_cases,
                    "network_enabled": include_network,
                    "network_candidate_count": network_candidate_count,
                    "network_case_count": sum(1 for item in cases if item.get("source") == "network"),
                    "local_case_count": sum(1 for item in cases if item.get("source") == "local"),
                    "page_coverage_count": coverage["page_coverage_count"],
                    "covered_pages": coverage["covered_pages"],
                    "uncovered_pages": coverage["uncovered_pages"],
                    "cases": cases,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        safe_doc_id = _safe_identifier(doc_id.lower())
        py_path = tests_dir / f"test_{safe_doc_id}_golden.py"
        py_path.write_text(_render_pytest_file(doc_id, cases), encoding="utf-8")
        sync_golden_cases(connection, doc_id, cases)
        connection.commit()

        return {
            "doc_id": doc_id,
            "source_filename": document["source_filename"],
            "page_count": document["page_count"],
            "target_case_count": target_case_count,
            "case_count": len(cases),
            "validated_during_generation": validate_cases,
            "network_enabled": include_network,
            "network_candidate_count": network_candidate_count,
            "network_case_count": sum(1 for item in cases if item.get("source") == "network"),
            "local_case_count": sum(1 for item in cases if item.get("source") == "local"),
            "page_coverage_count": coverage["page_coverage_count"],
            "covered_pages": coverage["covered_pages"],
            "uncovered_pages": coverage["uncovered_pages"],
            "json_path": str(json_path),
            "pytest_path": str(py_path),
            "cases": cases,
        }
    finally:
        connection.close()


def _draft_case_from_gap_candidate(candidate: dict[str, object], doc_id: str) -> dict[str, object]:
    must_include_values = [
        str(item).strip()
        for item in candidate.get("recommended_must_include", [])
        if str(item).strip()
    ]
    if not must_include_values:
        must_include_values = [str(candidate.get("semantic_key") or "").strip()]
    must_include_values = [item for item in must_include_values if item]
    primary_must_include = must_include_values[0] if must_include_values else str(candidate.get("semantic_key") or "")
    assert_mode = str(candidate.get("recommended_assert_mode") or "rich_answer").strip() or "rich_answer"
    golden_assert_mode = "context_contains" if assert_mode == "context_contains" else "rich_answer"
    query = str(candidate.get("recommended_query_seed") or "").strip()

    golden_case = {
        "kind": _draft_kind_for_unit(str(candidate.get("unit_type") or "")),
        "query": query,
        "must_include": primary_must_include,
        "source": "coverage",
        "assert_mode": golden_assert_mode,
        "target_doc_id": doc_id,
    }
    page_no = int(candidate.get("page_no") or 0)
    if page_no:
        golden_case["page_no"] = page_no

    return {
        "name": _draft_case_name(candidate),
        "status": "draft",
        "unit_id": candidate.get("unit_id"),
        "unit_type": candidate.get("unit_type"),
        "importance": candidate.get("importance"),
        "page_no": page_no,
        "semantic_key": candidate.get("semantic_key"),
        "query": query,
        "must_include": must_include_values,
        "assert_mode": assert_mode,
        "recommended_suite": candidate.get("recommended_suite"),
        "source_excerpt": candidate.get("source_excerpt"),
        "covered_by": candidate.get("covered_by") or {},
        "golden_case": golden_case,
    }


def _draft_kind_for_unit(unit_type: str) -> str:
    if unit_type == "definition_unit":
        return "coverage_definition"
    if unit_type == "parameter_row_unit":
        return "coverage_parameter_value"
    if unit_type == "requirement_unit":
        return "coverage_requirement"
    return "coverage_gap"


def _draft_case_name(candidate: dict[str, object]) -> str:
    unit_type = str(candidate.get("unit_type") or "unit").replace("_unit", "")
    unit_id = re.sub(r"[^A-Za-z0-9]+", "_", str(candidate.get("unit_id") or "")).strip("_").lower()
    return f"coverage_{unit_type}_{unit_id}"[:120]


def _render_coverage_test_draft_report(payload: dict[str, object]) -> str:
    lines = [
        "# Coverage Test Drafts",
        "",
        f"- doc_id: {payload['doc_id']}",
        f"- source_gap_count: {payload['source_gap_count']}",
        f"- skipped_candidate_count: {payload['skipped_candidate_count']}",
        f"- draft_case_count: {payload['draft_case_count']}",
        f"- validated: {payload['validated']}",
        f"- passed_count: {payload.get('passed_count', 0)}",
        f"- failed_count: {payload.get('failed_count', 0)}",
        "",
        "## Draft Cases",
        "",
    ]
    cases = list(payload.get("cases") or [])
    if not cases:
        lines.append("- none")
        return "\n".join(lines) + "\n"
    for case in cases[:100]:
        lines.append(
            f"- {case['name']} | page {case['page_no']} | {case['semantic_key']} | "
            f"query: {case['query']} | validation: {case['validation_status']}"
        )
    return "\n".join(lines) + "\n"


def _assess_draft_case_readiness(draft_case: dict[str, object]) -> dict[str, object]:
    query = str(draft_case.get("query") or "").strip()
    semantic_key = str(draft_case.get("semantic_key") or "").strip()
    source_excerpt = str(draft_case.get("source_excerpt") or "").strip()
    unit_type = str(draft_case.get("unit_type") or "").strip()
    must_include = [str(item).strip() for item in draft_case.get("must_include", []) if str(item).strip()]
    validation_status = str(draft_case.get("validation_status") or "not_validated")

    flags: list[str] = []
    reasons: list[str] = []
    score = 100

    if not query:
        flags.append("empty_query")
        reasons.append("query is empty")
        score -= 50
    if not semantic_key:
        flags.append("empty_semantic_key")
        reasons.append("semantic key is empty")
        score -= 35
    if not must_include:
        flags.append("empty_must_include")
        reasons.append("must_include is empty")
        score -= 40

    hard_noise = _draft_hard_noise_flags(query, semantic_key, source_excerpt, unit_type)
    flags.extend(hard_noise)
    if hard_noise:
        reasons.append("query or anchor looks like document noise rather than user intent")
        score -= 55

    soft_noise = _draft_soft_noise_flags(query, semantic_key, source_excerpt, unit_type)
    flags.extend(soft_noise)
    if soft_noise:
        reasons.append("query needs human review before it becomes a stable golden case")
        score -= 25

    anchor_blob = " ".join([semantic_key, *must_include])
    if anchor_blob and not _is_structured_clause_anchor(anchor_blob) and not _is_usable_golden_anchor(anchor_blob):
        flags.append("weak_anchor")
        reasons.append("must-hit anchor is too short, too symbolic, or too noisy")
        score -= 30

    if validation_status == "passed":
        score += 10
    elif validation_status == "failed":
        flags.append("validation_failed")
        reasons.append("existing validation failed")
        score -= 60
    else:
        flags.append("not_validated")
        reasons.append("quality gate passed only as a draft; retrieval validation has not run")

    score = max(0, min(100, score))
    status = _readiness_status(score, flags, validation_status)
    assessed = dict(draft_case)
    assessed.update(
        {
            "readiness_status": status,
            "readiness_score": score,
            "quality_flags": _unique_values(flags),
            "readiness_reasons": _unique_values(reasons),
        }
    )
    return assessed


def _readiness_status(score: int, flags: list[str], validation_status: str) -> str:
    hard_flags = {
        "empty_query",
        "empty_semantic_key",
        "empty_must_include",
        "document_boilerplate",
        "table_syntax_noise",
        "abstract_or_reference_noise",
        "standalone_unit_or_label",
        "weak_anchor",
        "validation_failed",
    }
    if any(flag in hard_flags for flag in flags) or score < 45:
        return "reject"
    if validation_status == "passed" and score >= 70:
        return "promotable"
    if score >= 70:
        return "ready_for_validation"
    return "needs_review"


def _draft_hard_noise_flags(query: str, semantic_key: str, source_excerpt: str, unit_type: str) -> list[str]:
    blob = " ".join([query, semantic_key, source_excerpt])
    compact = re.sub(r"\s+", " ", blob).strip()
    flags: list[str] = []
    if not compact:
        return flags
    if unit_type != "parameter_row_unit" and (
        re.search(r"\|\s*:?-{2,}:?\s*\|", compact) or compact.count("|") >= 4
    ):
        flags.append("table_syntax_noise")
    if re.search(r"\b(?:VDA\s+QMC|AUTOMOTIVE\s+SPICE|PUBLIC|Copyright|All rights reserved)\b", compact, re.I):
        flags.append("document_boilerplate")
    if re.search(r"\b(?:Abstract|References|Bibliography|Foreword|Contents)\b", compact, re.I):
        flags.append("abstract_or_reference_noise")
    label = re.sub(r"\s+", "", semantic_key)
    if label in {"VA", "Hz", "V", "A", "%", "时刻", "项目", "要求", "参数", "符号", "单位", "备注"}:
        flags.append("standalone_unit_or_label")
    if "[SPACE]" in compact or "[space]" in compact:
        flags.append("document_boilerplate")
    return _unique_values(flags)


def _draft_soft_noise_flags(query: str, semantic_key: str, source_excerpt: str, unit_type: str) -> list[str]:
    blob = " ".join([query, semantic_key, source_excerpt])
    flags: list[str] = []
    if len(re.sub(r"\s+", "", semantic_key)) > 42:
        flags.append("overlong_semantic_key")
    if re.search(r"条款\s*\d+(?:\.\d+)*", blob):
        flags.append("clause_reference_query")
    if re.search(r"\b(?:BP|GP|PA|ACQ|SYS|SWE|MAN|SUP)\.\d+(?:\.[A-Z]+\d+)?\b", blob):
        flags.append("process_code_query")
    if unit_type == "definition_unit" and re.search(r"过程组|过程名称|Process group|Process name", blob, re.I):
        flags.append("taxonomy_heading_query")
    if unit_type == "parameter_row_unit" and re.search(r"^(?:修正正弦波|单相\s*\d+\s*V|三相\s*\d+\s*V)$", semantic_key):
        flags.append("low_value_parameter_query")
    return _unique_values(flags)


def _is_structured_clause_anchor(value: str) -> bool:
    compact = re.sub(r"\s+", " ", value or "").strip()
    return bool(re.search(r"\b[A-Z]?\d+(?:\.\d+)+\b", compact) and re.search(r"[\u4e00-\u9fff]{2,}", compact))


def _count_by_key(items: list[dict[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "")
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _render_coverage_test_draft_readiness_report(payload: dict[str, object]) -> str:
    lines = [
        "# Coverage Test Draft Readiness",
        "",
        f"- doc_id: {payload['doc_id']}",
        f"- draft_case_count: {payload['draft_case_count']}",
        f"- status_counts: {json.dumps(payload['status_counts'], ensure_ascii=False)}",
        f"- flag_counts: {json.dumps(payload['flag_counts'], ensure_ascii=False)}",
        "",
        "## Cases",
        "",
    ]
    cases = list(payload.get("cases") or [])
    if not cases:
        lines.append("- none")
        return "\n".join(lines) + "\n"
    for case in cases[:120]:
        flags = ",".join(str(flag) for flag in case.get("quality_flags", [])) or "-"
        lines.append(
            f"- {case.get('readiness_status')} | score {case.get('readiness_score')} | "
            f"page {case.get('page_no')} | {case.get('semantic_key')} | query: {case.get('query')} | flags: {flags}"
        )
    return "\n".join(lines) + "\n"


def _render_all_coverage_test_draft_readiness_report(payload: dict[str, object]) -> str:
    lines = [
        "# All Docs Coverage Test Draft Readiness",
        "",
        f"- document_count: {payload['document_count']}",
        f"- assessed_document_count: {payload['assessed_document_count']}",
        f"- missing_draft_docs: {', '.join(payload.get('missing_draft_docs') or []) or 'none'}",
        f"- status_counts: {json.dumps(payload['status_counts'], ensure_ascii=False)}",
        f"- flag_counts: {json.dumps(payload['flag_counts'], ensure_ascii=False)}",
        "",
        "## Documents",
        "",
    ]
    for doc in payload.get("documents", []):
        lines.append(
            f"- {doc['doc_id']} | drafts {doc['draft_case_count']} | "
            f"statuses {json.dumps(doc['status_counts'], ensure_ascii=False)} | "
            f"flags {json.dumps(doc['flag_counts'], ensure_ascii=False)}"
        )
    return "\n".join(lines) + "\n"


def _active_document_ids(paths: AppPaths) -> list[str]:
    connection = connect(paths.db_file)
    try:
        rows = connection.execute(
            """
            SELECT doc_id
            FROM documents
            WHERE is_active = 1
            ORDER BY doc_id
            """
        ).fetchall()
    finally:
        connection.close()
    return [str(row["doc_id"]) for row in rows]


def _promotable_draft_cases(draft_payload: dict[str, object]) -> list[dict[str, str]]:
    promoted: list[dict[str, str]] = []
    for draft_case in draft_payload.get("cases", []):
        if not isinstance(draft_case, dict):
            continue
        readiness = _assess_draft_case_readiness(draft_case)
        if readiness["readiness_status"] not in {"promotable", "ready_for_validation"}:
            continue
        if draft_payload.get("validated") and draft_case.get("validation_status") != "passed":
            continue
        golden_case = draft_case.get("golden_case")
        if not isinstance(golden_case, dict):
            continue
        case = {
            key: value
            for key, value in golden_case.items()
            if key in {"kind", "query", "must_include", "source", "assert_mode", "page_no", "target_doc_id"}
        }
        case["coverage_unit_id"] = str(draft_case.get("unit_id") or "")
        case["coverage_semantic_key"] = str(draft_case.get("semantic_key") or "")
        promoted.append(case)
    return _dedupe_cases(promoted)


def _load_or_create_golden_payload(paths: AppPaths, doc_id: str, golden_path: Path) -> dict[str, object]:
    if golden_path.exists():
        payload = json.loads(golden_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.setdefault("doc_id", doc_id)
            payload.setdefault("cases", [])
            return payload

    connection = connect(paths.db_file)
    try:
        document = connection.execute(
            """
            SELECT source_filename, page_count
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
    finally:
        connection.close()

    if document is None:
        raise ValueError(f"document not found: {doc_id}")
    return {
        "doc_id": doc_id,
        "source_filename": document["source_filename"],
        "page_count": document["page_count"],
        "target_case_count": 0,
        "network_candidate_count": 0,
        "network_case_count": 0,
        "local_case_count": 0,
        "page_coverage_count": 0,
        "covered_pages": [],
        "uncovered_pages": [],
        "cases": [],
    }


def _target_case_count(page_count: int, fact_count: int, evidence_count: int) -> int:
    content_factor = min(20, max(0, fact_count // 8) + max(0, evidence_count // 6))
    proportional = max(MIN_CASE_COUNT, math.ceil(page_count * 0.55) + content_factor)
    return max(MIN_CASE_COUNT, min(MAX_CASE_COUNT, max(page_count, proportional)))


def _build_local_context(document, facts, evidence_rows, wiki_rows) -> dict[str, object]:
    fact_items = []
    for row in facts:
        fact_items.append(
            {
                "fact_type": row["fact_type"],
                "predicate": row["predicate"],
                "object_value": _safe_json(row["object_value"]),
                "qualifiers_json": _safe_json(row["qualifiers_json"]),
            }
        )

    evidence_items = [dict(row) for row in evidence_rows]
    wiki_items = [dict(row) for row in wiki_rows]

    standard_code = ""
    title = ""
    publication_date = ""
    effective_date = ""
    term_definitions: list[dict[str, str]] = []
    section_headings: list[dict[str, object]] = []

    for item in fact_items:
        payload = item["object_value"]
        if not isinstance(payload, dict):
            continue
        if item["fact_type"] == "document_standard" and not standard_code:
            standard_code = str(payload.get("value", "")).strip()
        elif item["fact_type"] == "document_title" and not title:
            title = str(payload.get("value", "")).strip()
        elif item["fact_type"] == "document_lifecycle" and item["predicate"] == "publication_date" and not publication_date:
            publication_date = str(payload.get("value", "")).strip()
        elif item["fact_type"] == "document_lifecycle" and item["predicate"] == "effective_date" and not effective_date:
            effective_date = str(payload.get("value", "")).strip()
        elif item["fact_type"] in {"term_definition", "concept_definition"}:
            term = str(payload.get("term", "")).strip()
            definition = str(payload.get("definition", "")).strip()
            if term and definition:
                term_definitions.append({"term": term, "definition": definition})
        elif item["fact_type"] == "section_heading":
            title_value = str(payload.get("title", "")).strip()
            if title_value:
                section_headings.append(
                    {
                        "title": title_value,
                        "page_no": int(item["qualifiers_json"].get("page_no", 0))
                        if isinstance(item["qualifiers_json"], dict)
                        else 0,
                    }
                )

    normalized_texts = [
        document["source_filename"],
        standard_code,
        title,
        publication_date,
        effective_date,
        *[json.dumps(item["object_value"], ensure_ascii=False) for item in fact_items],
        *[str(item["normalized_text"]) for item in evidence_items],
        *[str(item["title"]) for item in wiki_items],
    ]
    local_corpus = "\n".join(part for part in normalized_texts if part)

    return {
        "doc_id": document["doc_id"],
        "source_filename": document["source_filename"],
        "page_count": int(document["page_count"] or 0),
        "standard_code": standard_code,
        "title": title,
        "publication_date": publication_date,
        "effective_date": effective_date,
        "facts": fact_items,
        "evidence": evidence_items,
        "wiki": wiki_items,
        "term_definitions": term_definitions,
        "section_headings": section_headings,
        "local_corpus": local_corpus,
        "pages_with_evidence": sorted({int(item["page_no"]) for item in evidence_items if int(item.get("page_no") or 0) > 0}),
    }


def _build_network_cases(local_context: dict[str, object], target_count: int) -> list[dict[str, object]]:
    if target_count <= 0:
        return []

    search_queries = _build_search_queries(local_context)
    cases: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    page_fetch_budget = 6

    for query in search_queries:
        for hit in _search_duckduckgo(query):
            if page_fetch_budget <= 0:
                return _dedupe_cases(cases)[:target_count]
            if hit["url"] in seen_urls:
                continue
            seen_urls.add(hit["url"])
            page_fetch_budget -= 1

            source_text = "\n".join(
                part for part in [hit["title"], hit["snippet"], _fetch_page_text(hit["url"])] if part
            )
            if not source_text.strip():
                continue

            extracted = _extract_network_metadata(source_text)
            candidates = _network_cases_from_metadata(local_context, extracted, hit["url"])
            for case in candidates:
                cases.append(case)
                if len(_dedupe_cases(cases)) >= target_count:
                    break
    return _dedupe_cases(cases)[:target_count]


def _build_answer_quality_cases(
    local_context: dict[str, object],
    target_count: int,
) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    seen_queries: set[str] = set()

    def _add_aq(query: str, must_include: list[str], *, expected_answer_mode: str, forbidden_contains: list[str], expected_evidence_shape: str, query_type: str = "parameter_lookup") -> None:
        normalized_query = re.sub(r"\s+", " ", query).strip()
        if normalized_query in seen_queries:
            return
        if not must_include or not _is_usable_golden_anchor(must_include[0]):
            return
        seen_queries.add(normalized_query)
        case: dict[str, object] = {
            "kind": "answer_quality",
            "query": normalized_query,
            "must_include": must_include[0],
            "retrieval_must_hit": must_include,
            "assert_mode": "rich_answer",
            "expected_answer_mode": expected_answer_mode,
            "forbidden_contains": forbidden_contains,
            "expected_evidence_shape": expected_evidence_shape,
            "source": "local_aq",
            "query_type": query_type,
        }
        cases.append(case)

    parameter_facts = [
        f for f in local_context.get("facts", [])
        if f.get("fact_type") == "parameter_value"
        and isinstance(_safe_json(f.get("object_value")), dict)
    ]
    seen_param_keys: set[str] = set()
    for fact in parameter_facts:
        payload = _safe_json(fact.get("object_value"))
        if not isinstance(payload, dict):
            continue
        parameter = str(payload.get("parameter") or "").strip()
        symbol = str(payload.get("symbol") or "").strip()
        unit = str(payload.get("unit", "")).strip()
        key_parts = [p for p in [parameter, symbol] if p]
        key = "|".join(key_parts)
        if key in seen_param_keys or not key_parts:
            continue
        seen_param_keys.add(key)
        if not parameter or not symbol:
            continue
        if not _is_usable_parameter_label(parameter):
            continue
        _add_aq(
            query=f"{parameter}是多少",
            must_include=[parameter, unit] if unit else [parameter],
            expected_answer_mode="parameter_value",
            forbidden_contains=["没有找到足够的结构化结果。", "GB：代替"],
            expected_evidence_shape="parameter_value",
            query_type="parameter_lookup",
        )

    return _dedupe_cases(cases)[:target_count]

    return _dedupe_cases(cases)[:target_count]


def _build_search_queries(local_context: dict[str, object]) -> list[str]:
    filename_stem = Path(str(local_context["source_filename"])).stem
    standard_code = str(local_context.get("standard_code", "")).replace("—", "-")
    title = str(local_context.get("title", ""))
    queries = [
        f"{standard_code} {title}".strip(),
        f"{standard_code} {filename_stem}".strip(),
        filename_stem,
        standard_code,
        title,
    ]
    deduped: list[str] = []
    for item in queries:
        cleaned = re.sub(r"\s+", " ", item).strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped[:4]


def _search_duckduckgo(query: str) -> list[dict[str, str]]:
    try:
        response = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": NETWORK_USER_AGENT},
            timeout=8.0,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception:
        return []

    hits: list[dict[str, str]] = []
    title_matches = list(
        re.finditer(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            response.text,
            re.S,
        )
    )
    snippet_matches = list(
        re.finditer(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>|<div[^>]*class="result__snippet"[^>]*>(.*?)</div>',
            response.text,
            re.S,
        )
    )

    for index, match in enumerate(title_matches[:8]):
        raw_url = html.unescape(match.group(1))
        title = _strip_html(html.unescape(match.group(2)))
        snippet = ""
        if index < len(snippet_matches):
            body = snippet_matches[index].group(1) or snippet_matches[index].group(2) or ""
            snippet = _strip_html(html.unescape(body))
        url = _resolve_duckduckgo_url(raw_url)
        if url:
            hits.append({"title": title, "snippet": snippet, "url": url})
    return hits


def _resolve_duckduckgo_url(raw_url: str) -> str:
    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url
    parsed = urlparse(raw_url)
    if "duckduckgo.com" not in parsed.netloc:
        return raw_url
    uddg = parse_qs(parsed.query).get("uddg")
    if not uddg:
        return ""
    return unquote(uddg[0])


def _fetch_page_text(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return ""
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": NETWORK_USER_AGENT},
            timeout=6.0,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception:
        return ""

    text = _strip_html(response.text)
    return re.sub(r"\s+", " ", text).strip()[:5000]


def _extract_network_metadata(text: str) -> dict[str, list[str]]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    metadata: dict[str, list[str]] = {
        "standard_codes": _unique_matches(
            r"(?:GB/T|GB|ISO|IEC|QC/T|QC)\s*[A-Z]?\s*[\d.]+(?:[-—]\d{2,4})?",
            cleaned,
        ),
        "dates": _unique_matches(r"\b\d{4}[-/]\d{2}[-/]\d{2}\b", cleaned),
        "status": _unique_matches(r"(?:Status[:：]?\s*[A-Za-z]+|现行|有效|Valid)", cleaned, flags=re.I),
        "titles": _extract_candidate_titles(cleaned),
        "scope": _extract_scope_sentences(cleaned),
        "organizations": _extract_organizations(cleaned),
    }
    return metadata


def _network_cases_from_metadata(
    local_context: dict[str, object],
    metadata: dict[str, list[str]],
    source_url: str,
) -> list[dict[str, str]]:
    standard_code = str(local_context.get("standard_code", "")).strip()
    title = str(local_context.get("title", "")).strip()
    publication_date = str(local_context.get("publication_date", "")).strip()
    effective_date = str(local_context.get("effective_date", "")).strip()

    cases: list[dict[str, str]] = []
    if standard_code and _is_valid_standard_code(standard_code):
        cases.append(
            _case(
                "network_standard",
                f"{standard_code} 的标准号是什么？",
                standard_code,
                source="network",
                assert_mode="rich_answer",
                source_url=source_url,
            )
        )
    if publication_date:
        cases.append(
            _case(
                "network_publication_date",
                f"{standard_code or title} 的发布日期是什么？",
                publication_date,
                source="network",
                assert_mode="rich_answer",
                source_url=source_url,
            )
        )
    if effective_date:
        cases.append(
            _case(
                "network_effective_date",
                f"{standard_code or title} 的实施日期是什么？",
                effective_date,
                source="network",
                assert_mode="rich_answer",
                source_url=source_url,
            )
        )
    if title:
        cases.append(
            _case(
                "network_title",
                f"{standard_code or title} 的中文名称是什么？",
                title,
                source="network",
                assert_mode="rich_answer",
                source_url=source_url,
            )
        )

    for value in metadata.get("titles", [])[:3]:
        if value != title:
            cases.append(
                _case(
                    "network_title_variant",
                    f"{standard_code or title} 的名称或公开标题是什么？",
                    value,
                    source="network",
                    assert_mode="rich_answer",
                    source_url=source_url,
                )
            )

    for value in metadata.get("organizations", [])[:4]:
        cases.append(
            _case(
                "network_org",
                f"{standard_code or title} 的发布或起草信息中是否包含 {value}？",
                value,
                source="network",
                assert_mode="context_contains",
                source_url=source_url,
            )
        )

    for value in metadata.get("scope", [])[:4]:
        cases.append(
            _case(
                "network_scope",
                f"{standard_code or title} 适用于什么对象或范围？",
                value,
                source="network",
                assert_mode="rich_answer",
                source_url=source_url,
            )
        )

    return cases


def _build_local_cases(
    local_context: dict[str, object],
    target_count: int,
    extra_round: bool = False,
) -> list[dict[str, str]]:
    if target_count <= 0:
        return []

    cases: list[dict[str, str]] = []
    standard_code = str(local_context.get("standard_code", "")).strip()
    title = str(local_context.get("title", "")).strip()
    publication_date = str(local_context.get("publication_date", "")).strip()
    effective_date = str(local_context.get("effective_date", "")).strip()

    if standard_code and _is_valid_standard_code(standard_code):
        for query in [
            f"{standard_code} 的标准号和实施日期是什么？",
            f"{standard_code} 对应的标准编号是什么？",
            f"{standard_code} 的现行标准号是什么？",
        ]:
            cases.append(_case("standard", _scope_query(local_context, query), standard_code, source="local", assert_mode="context_contains"))

    if publication_date:
        for query in [
            f"{standard_code or title} 的发布日期是什么？",
            f"{standard_code or title} 是哪一天发布的？",
        ]:
            cases.append(_case("publication_date", _scope_query(local_context, query), publication_date, source="local", assert_mode="rich_answer"))

    if effective_date:
        for query in [
            f"{standard_code or title} 的实施日期是什么？",
            f"{standard_code or title} 从哪一天开始实施？",
        ]:
            cases.append(_case("effective_date", _scope_query(local_context, query), effective_date, source="local", assert_mode="rich_answer"))

    if title and _is_usable_golden_anchor(title):
        cases.append(_case("title", _scope_query(local_context, f"{standard_code or title} 这份文档的标题是什么？"), title, source="local", assert_mode="context_contains"))

    for item in list(local_context.get("term_definitions", []))[:8]:
        term = _strip_markdown_bold(str(item["term"]).strip())
        definition = _strip_markdown_bold(str(item["definition"]).strip())
        if not term or not definition or not _is_usable_golden_anchor(term) or not _is_usable_golden_anchor(definition):
            continue
        if _looks_like_person_name(term):
            continue
        definition_query_prefix = f"在{standard_code}中，" if standard_code else ""
        cases.append(
            _case(
                "definition",
                _scope_query(local_context, f"{definition_query_prefix}什么是{term}？"),
                term,
                source="local",
                assert_mode="context_contains",
            )
        )
        cases.append(
            _case(
                "definition_detail",
                _scope_query(local_context, f"{definition_query_prefix}{term} 的定义是什么？"),
                _definition_anchor(definition),
                source="local",
                assert_mode="context_contains",
            )
        )

    sampled_headings = _sample_headings(list(local_context.get("section_headings", [])), 4 if not extra_round else 6)
    for heading in sampled_headings:
        title_value = str(heading["title"]).strip()
        if not title_value or not _is_usable_golden_anchor(title_value):
            continue
        cases.append(
            _case(
                "section",
                _scope_query(local_context, f"在{standard_code or '该文档'}中，是否包含“{title_value}”这一章节？"),
                title_value,
                source="local",
                assert_mode="context_contains",
                page_no=int(heading.get("page_no") or 0),
            )
        )

    evidence_cases = _cases_from_evidence(local_context, list(local_context.get("evidence", [])), extra_round=extra_round)
    cases.extend(evidence_cases)

    return _dedupe_cases(cases)[:target_count]


def _cases_from_evidence(
    local_context: dict[str, object],
    evidence_items: list[dict[str, object]],
    extra_round: bool = False,
) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    sentence_budget = 10 if not extra_round else 18
    sentence_items: list[tuple[str, int]] = []
    seen_sentences: set[str] = set()

    for item in evidence_items:
        text = str(item.get("normalized_text", "")).strip()
        if not text:
            continue
        for sentence in _extract_candidate_sentences(text):
            if sentence not in seen_sentences:
                sentence_items.append((sentence, int(item.get("page_no") or 0)))
                seen_sentences.add(sentence)
            if len(sentence_items) >= sentence_budget:
                break
        if len(sentence_items) >= sentence_budget:
            break

    for sentence, page_no in sentence_items:
        anchor = _definition_anchor(sentence)
        if not _is_usable_golden_anchor(anchor):
            continue
        if "适用于" in sentence:
            query = anchor
        elif "规定了" in sentence:
            query = anchor
        elif "发布" in sentence and re.search(r"\d{4}-\d{2}-\d{2}", sentence):
            query = anchor
        elif "实施" in sentence and re.search(r"\d{4}-\d{2}-\d{2}", sentence):
            query = anchor
        else:
            query = anchor
        cases.append(
            _case(
                "evidence",
                _scope_query(local_context, query),
                anchor,
                source="local",
                assert_mode="context_contains",
                page_no=page_no,
            )
        )

    return cases


def _doc_scope_label(local_context: dict[str, object]) -> str:
    standard_code = str(local_context.get("standard_code", "")).strip()
    if standard_code and _is_valid_standard_code(standard_code):
        return standard_code
    title = str(local_context.get("title", "")).strip()
    if title:
        return title
    source_filename = str(local_context.get("source_filename", "")).strip()
    if source_filename:
        return Path(source_filename).stem
    return str(local_context.get("doc_id", "")).strip()


def _scope_query(local_context: dict[str, object], query: str) -> str:
    scope = _doc_scope_label(local_context)
    query = re.sub(r"\s+", " ", query).strip()
    if not scope:
        return query
    if scope in query:
        return query
    return f"{scope}：{query}"


def _build_page_coverage_cases(local_context: dict[str, object]) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    per_page_seen: set[int] = set()

    for evidence_item in list(local_context.get("evidence", [])):
        page_no = int(evidence_item.get("page_no") or 0)
        if page_no <= 0 or page_no in per_page_seen:
            continue
        text = str(evidence_item.get("normalized_text", "")).strip()
        sentence = _select_page_anchor_sentence(text) or _select_page_anchor_fragment(text)
        if not sentence:
            continue
        per_page_seen.add(page_no)
        anchor = _definition_anchor(sentence, max_chars=38)
        if not _is_usable_golden_anchor(anchor):
            continue
        query = f"第{page_no}页 {anchor}"
        cases.append(
            _case(
                "page_coverage",
                query,
                anchor,
                source="local",
                assert_mode="context_contains",
                page_no=page_no,
            )
        )

    return cases


def _build_retrieval_quality_cases(
    local_context: dict[str, object],
    target_count: int,
) -> list[dict[str, object]]:
    if target_count <= 0:
        return []

    standard_code = str(local_context.get("standard_code", "")).strip()
    title = str(local_context.get("title", "")).strip()
    scope_label = standard_code or title or str(local_context.get("doc_id", "")).strip()
    cases: list[dict[str, object]] = []
    seen_queries: set[str] = set()

    def _add_rq(query, must_hit, expected_pages=None, expected_sections=None, negative_expected=None, difficulty="medium", query_type="scenario"):
        normalized_query = re.sub(r"\s+", " ", query).strip()
        if normalized_query in seen_queries:
            return
        if not must_hit or not _is_usable_golden_anchor(must_hit[0] if must_hit else ""):
            return
        seen_queries.add(normalized_query)
        case: dict[str, object] = {
            "kind": "retrieval_quality",
            "query": normalized_query,
            "must_include": must_hit[0],
            "retrieval_must_hit": must_hit,
            "assert_mode": "rich_answer",
            "source": "local_rq",
            "expected_pages": expected_pages or [],
            "expected_sections": expected_sections or [],
            "negative_expected": negative_expected or [],
            "difficulty": difficulty,
            "query_type": query_type,
        }
        if "expected_pages" in case and not case["expected_pages"]:
            del case["expected_pages"]
        if "expected_sections" in case and not case["expected_sections"]:
            del case["expected_sections"]
        if "negative_expected" in case and not case["negative_expected"]:
            del case["negative_expected"]
        cases.append(case)

    def _add_aq(query: str, must_include: list[str], *, expected_answer_mode: str, forbidden_contains: list[str], expected_evidence_shape: str, query_type: str = "parameter_lookup") -> None:
        """Add an answer_quality case for testing answer correctness."""
        nonlocal cases, seen_queries
        normalized_query = re.sub(r"\s+", " ", query).strip()
        if normalized_query in seen_queries:
            return
        if not must_include or not _is_usable_golden_anchor(must_include[0]):
            return
        seen_queries.add(normalized_query)
        case: dict[str, object] = {
            "kind": "answer_quality",
            "query": normalized_query,
            "must_include": must_include[0],
            "retrieval_must_hit": must_include,
            "assert_mode": "rich_answer",
            "expected_answer_mode": expected_answer_mode,
            "forbidden_contains": forbidden_contains,
            "expected_evidence_shape": expected_evidence_shape,
            "source": "local_aq",
            "query_type": query_type,
        }
        if "forbidden_contains" in case and not case["forbidden_contains"]:
            del case["forbidden_contains"]
        cases.append(case)

    for item in list(local_context.get("term_definitions", [])):
        term = _strip_markdown_bold(str(item["term"]).strip())
        definition = _strip_markdown_bold(str(item["definition"]).strip())
        if not term or not definition or not _is_usable_golden_anchor(term) or not _is_usable_golden_anchor(definition):
            continue
        if _looks_like_person_name(term):
            continue
        _add_rq(
            query=f"什么是{term}？",
            must_hit=[term],
            expected_sections=[term],
            query_type="definition",
        )
        _add_rq(
            query=f"{scope_label}中{term}的定义是什么？",
            must_hit=[term],
            expected_sections=[term],
            query_type="definition",
        )

    parameter_facts = [
        f for f in local_context.get("facts", [])
        if f.get("fact_type") == "parameter_value"
        and isinstance(_safe_json(f.get("object_value")), dict)
    ]
    seen_param_keys: set[str] = set()
    for fact in parameter_facts:
        payload = _safe_json(fact.get("object_value"))
        if not isinstance(payload, dict):
            continue
        parameter = str(payload.get("parameter") or "").strip()
        symbol = str(payload.get("symbol") or "").strip()
        table_title = str(payload.get("table_title") or "").strip()
        object_name = str(payload.get("object") or "").strip()
        state = str(payload.get("state") or "").strip()
        qualifiers = _safe_json(fact.get("qualifiers_json"))
        page_no = int(qualifiers.get("page_no", 0)) if isinstance(qualifiers, dict) else 0
        key_parts = [p for p in [object_name, parameter, symbol] if p]
        key = "|".join(key_parts)
        if key in seen_param_keys or not key_parts:
            continue
        seen_param_keys.add(key)
        label = key_parts[0]
        if not _is_usable_parameter_label(label):
            continue
        _add_rq(
            query=f"{label}的参数要求是什么？",
            must_hit=[label],
            expected_pages=[page_no] if page_no else [],
            expected_sections=[table_title] if table_title else [],
            query_type="parameter_lookup",
        )
        if parameter and symbol:
            _add_rq(
            query=f"{symbol}代表什么参数？",
            must_hit=[parameter],
            expected_pages=[page_no] if page_no else [],
            expected_sections=[table_title] if table_title else [],
            query_type="parameter_lookup",
        )

    if local_context.get("term_definitions"):
        top_terms = [str(t.get("term", "")) for t in local_context["term_definitions"][:6] if str(t.get("term", "")).strip()]
        if len(top_terms) >= 2:
            pair = "和".join(top_terms[:2])
            _add_rq(
                query=f"{pair}有什么区别？",
                must_hit=top_terms[:2],
                query_type="comparison",
                difficulty="hard",
            )

    requirement_facts = [
        f for f in local_context.get("facts", [])
        if f.get("fact_type") == "requirement"
        and isinstance(_safe_json(f.get("object_value")), dict)
    ]
    seen_req_keys: set[str] = set()
    for fact in requirement_facts[:40]:
        payload = _safe_json(fact.get("object_value"))
        if not isinstance(payload, dict):
            continue
        subject = str(payload.get("subject") or payload.get("topic") or "").strip()
        content = str(payload.get("content") or "").strip()
        section_title = str(payload.get("title") or "").strip()
        qualifiers = _safe_json(fact.get("qualifiers_json"))
        page_no = int(qualifiers.get("page_no", 0)) if isinstance(qualifiers, dict) else 0
        if not subject or subject in seen_req_keys:
            continue
        if len(subject) < 3 or len(subject) > 30:
            continue
        seen_req_keys.add(subject)
        _add_rq(
            query=f"{subject}有什么要求？",
            must_hit=[subject],
            expected_pages=[page_no] if page_no else [],
            expected_sections=[section_title] if section_title else [],
            query_type="general_search",
        )

    process_facts = [
        f for f in local_context.get("facts", [])
        if f.get("fact_type") == "process_fact"
        and isinstance(_safe_json(f.get("object_value")), dict)
    ]
    seen_proc_keys: set[str] = set()
    for fact in process_facts[:30]:
        payload = _safe_json(fact.get("object_value"))
        if not isinstance(payload, dict):
            continue
        proc_name = str(payload.get("process_name") or payload.get("title") or "").strip()
        section = str(payload.get("section") or "").strip()
        qualifiers = _safe_json(fact.get("qualifiers_json"))
        page_no = int(qualifiers.get("page_no", 0)) if isinstance(qualifiers, dict) else 0
        clean_name = re.sub(r"^\d+[\.\s]+", "", proc_name).strip()
        if not clean_name or clean_name in seen_proc_keys or len(clean_name) < 3:
            continue
        seen_proc_keys.add(clean_name)
        _add_rq(
            query=f"{clean_name}的流程是什么？",
            must_hit=[clean_name],
            expected_pages=[page_no] if page_no else [],
            expected_sections=[section] if section else [],
            query_type="timing_lookup",
        )

    threshold_facts = [
        f for f in local_context.get("facts", [])
        if f.get("fact_type") == "threshold"
        and isinstance(_safe_json(f.get("object_value")), dict)
    ]
    seen_thr_keys: set[str] = set()
    for fact in threshold_facts[:20]:
        payload = _safe_json(fact.get("object_value"))
        if not isinstance(payload, dict):
            continue
        parameter = str(payload.get("parameter") or "").strip()
        condition = str(payload.get("condition") or "").strip()
        section_title = str(payload.get("title") or "").strip()
        qualifiers = _safe_json(fact.get("qualifiers_json"))
        page_no = int(qualifiers.get("page_no", 0)) if isinstance(qualifiers, dict) else 0
        label = parameter or condition
        if not label or label in seen_thr_keys or len(label) < 3:
            continue
        seen_thr_keys.add(label)
        _add_rq(
            query=f"{label}的限值是多少？",
            must_hit=[label],
            expected_pages=[page_no] if page_no else [],
            expected_sections=[section_title] if section_title else [],
            query_type="parameter_lookup",
        )

    return _dedupe_cases(cases)[:target_count]


def _build_last_resort_cases(local_context: dict[str, object]) -> list[dict[str, str]]:
    standard_code = str(local_context.get("standard_code", "")).strip()
    title = str(local_context.get("title", "")).strip()
    cases: list[dict[str, str]] = []
    for heading in list(local_context.get("section_headings", [])):
        title_value = str(heading.get("title", "")).strip()
        if not title_value or not _is_usable_golden_anchor(title_value):
            continue
        query = _scope_query(local_context, f"{standard_code or title} {title_value}")
        cases.append(
            _case(
                "keyword_section",
                query,
                title_value,
                source="local",
                assert_mode="context_contains",
                page_no=int(heading.get("page_no") or 0),
            )
        )
    for term_item in list(local_context.get("term_definitions", [])):
        term = str(term_item.get("term", "")).strip()
        if term and _is_usable_golden_anchor(term):
            query = _scope_query(local_context, f"{standard_code or title} {term}")
            cases.append(_case("keyword_term", query, term, source="local", assert_mode="context_contains"))
    for wiki_item in list(local_context.get("wiki", [])):
        wiki_title = str(wiki_item.get("title", "")).strip()
        if wiki_title and _is_usable_golden_anchor(wiki_title):
            query = _scope_query(local_context, wiki_title)
            cases.append(
                _case(
                    "keyword_wiki",
                    query,
                    wiki_title,
                    source="local",
                    assert_mode="context_contains",
                )
            )
    evidence_budget = 24
    for evidence_item in list(local_context.get("evidence", [])):
        text = str(evidence_item.get("normalized_text", "")).strip()
        if not text:
            continue
        for sentence in _extract_candidate_sentences(text):
            anchor = _definition_anchor(sentence, max_chars=28)
            if len(anchor) < 10 or not _is_usable_golden_anchor(anchor):
                continue
            cases.append(
                _case(
                    "keyword_evidence",
                    _scope_query(local_context, anchor),
                    anchor,
                    source="local",
                    assert_mode="context_contains",
                    page_no=int(evidence_item.get("page_no") or 0),
                )
            )
            evidence_budget -= 1
            if evidence_budget <= 0:
                break
        if evidence_budget <= 0:
            break
    return cases


def _sample_headings(headings: list[dict[str, object]], budget: int) -> list[dict[str, object]]:
    if len(headings) <= budget:
        return headings
    step = max(1, len(headings) // budget)
    sampled = [headings[index] for index in range(0, len(headings), step)]
    return sampled[:budget]


def _is_usable_golden_anchor(value: str) -> bool:
    text = re.sub(r"\s+", "", value or "")
    if len(text) < 6:
        return False
    if any((ord(ch) < 32 or 127 <= ord(ch) <= 159) for ch in text):
        return False
    if any(marker in text for marker in ("!!!", "!!!!!", "----", "����")):
        return False
    if re.search(r"[犀-狿]{4,}", text):
        return False
    semantic_chars = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", text)
    if len(semantic_chars) < 4:
        return False
    if len(re.findall(r"\d", text)) / max(len(semantic_chars), 1) > 0.6:
        return False
    symbol_count = len(re.findall(r"[^A-Za-z0-9\u4e00-\u9fff]", text))
    if symbol_count / max(len(text), 1) > 0.25:
        return False
    if re.search(r"[A-Z]{4,}", text) and not re.search(r"[a-z\u4e00-\u9fff]", text) and not _is_valid_standard_code(text):
        return False
    has_language_run = bool(re.search(r"[A-Za-z]{3,}", text) or re.search(r"[\u4e00-\u9fff]{2,}", text))
    if not has_language_run:
        return False
    return len(semantic_chars) / max(len(text), 1) >= 0.65


def _is_valid_standard_code(value: str) -> bool:
    return bool(re.search(r"\b(?:GB/T|GBT|GB|QC/T|QC|ISO|IEC)\s*[\d.]+(?:[-—]\d{2,4})?\b", value, re.I))


def _looks_like_person_name(term: str) -> bool:
    if not term:
        return False
    cleaned = re.sub(r"\s+", "", term)
    parts = re.split(r"[,，、;；]", cleaned)
    if len(parts) >= 2:
        all_cjk = all(re.fullmatch(r"[\u4e00-\u9fff]{2,4}", p) for p in parts if p)
        if all_cjk and len(parts) >= 2:
            return True
    if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", cleaned):
        if not re.search(r"[技术方法系统设备装置器电压电流功率温度]", cleaned):
            pass
    return False


def _strip_markdown_bold(text: str) -> str:
    stripped = re.sub(r"\*\*([^*]{1,300})\*\*", r"\1", text)
    stripped = re.sub(r"\*([^*]{1,100})\*", r"\1", stripped)
    return stripped.strip()


def _is_usable_parameter_label(label: str) -> bool:
    if not label or len(label) < 2 or len(label) > 50:
        return False
    if re.search(r"[·•\u2022\u2023\u25E6\uff65]", label):
        return False
    if label.startswith(")") or label.startswith("-"):
        return False
    return True


def _case(
    kind: str,
    query: str,
    must_include: str,
    *,
    source: str,
    assert_mode: str,
    page_no: int | None = None,
    source_url: str | None = None,
) -> dict[str, str]:
    payload = {
        "kind": kind,
        "query": re.sub(r"\s+", " ", query).strip(),
        "must_include": re.sub(r"\s+", " ", must_include).strip(),
        "source": source,
        "assert_mode": assert_mode,
    }
    if page_no:
        payload["page_no"] = int(page_no)
    if source_url:
        payload["source_url"] = source_url
    return payload


def _dedupe_cases(cases: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for case in cases:
        key = (
            case.get("query", ""),
            _normalize_compare(case.get("must_include", "")),
            case.get("assert_mode", ""),
        )
        if key in seen or not case.get("must_include"):
            continue
        seen.add(key)
        deduped.append(case)
    return deduped


def _contains_locally(local_corpus: str, expected: str) -> bool:
    if not expected:
        return False
    return _normalize_compare(expected) in _normalize_compare(local_corpus)


def _extract_candidate_titles(text: str) -> list[str]:
    titles: list[str] = []
    for pattern in [
        r"(Automotive DC-AC power inverter)",
        r"(汽车电源逆变器)",
        r"(电动汽车用传导式车载充电机)",
        r"(电动汽车传导充电系统[^。；]{0,60})",
    ]:
        titles.extend(_unique_matches(pattern, text, flags=re.I))
    return titles[:6]


def _extract_scope_sentences(text: str) -> list[str]:
    scopes: list[str] = []
    for match in re.finditer(r"((?:本标准|本文件).{0,80}?(?:规定了|适用于).{0,120}[。；])", text):
        scopes.append(_definition_anchor(match.group(1)))
    for match in re.finditer(r"((?:This standard|This document).{0,140}?(?:specifies|applies to).{0,180}\.)", text, re.I):
        scopes.append(_definition_anchor(match.group(1)))
    return _unique_values(scopes)[:6]


def _extract_organizations(text: str) -> list[str]:
    organizations: list[str] = []
    for pattern in [
        r"(中华人民共和国工业和信息化部)",
        r"(全国汽车标准化技术委员会[^，。；]{0,40})",
        r"(上海汽车集团股份有限公司技术中心)",
        r"(长沙汽车电器研究所)",
    ]:
        organizations.extend(_unique_matches(pattern, text))
    return _unique_values(organizations)[:6]


def _unique_matches(pattern: str, text: str, *, flags: int = 0) -> list[str]:
    return _unique_values(match.group(0).strip() for match in re.finditer(pattern, text, flags))


def _unique_values(values) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value)).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped


def _extract_candidate_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[。；.!?])\s+", cleaned)
    sentences: list[str] = []
    for part in parts:
        segment = part.strip()
        if len(segment) < 16:
            continue
        if "<table" in segment.lower():
            continue
        if segment not in sentences:
            sentences.append(segment)
    return sentences[:6]


def _select_page_anchor_sentence(text: str) -> str:
    sentences = _extract_candidate_sentences(text)
    ranked = sorted(sentences, key=_page_sentence_score, reverse=True)
    return ranked[0] if ranked else ""


def _select_page_anchor_fragment(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", _strip_html(text)).strip()
    if not cleaned:
        return ""
    for pattern in [
        r"(QC/T\s*[\d.]+[—-]\d{4})",
        r"(GB/T\s*[\d.]+[—-]\d{4})",
        r"(第\s*\d+\s*部分[^，。；]{0,18})",
        r"([一二三四五六七八九十\d]+\s*[范围要求试验方法检验规则术语定义保护功能效率电压功率]{1,8}[^，。；]{0,18})",
    ]:
        match = re.search(pattern, cleaned, re.I)
        if match:
            return match.group(1).strip()
    if len(cleaned) <= 28:
        return cleaned
    return cleaned[:28].rstrip(" ，,;；。")


def _page_sentence_score(sentence: str) -> tuple[int, int]:
    penalty = 1 if any(token in sentence for token in ("目次", "目 次", "前言", "目录", "chapter", "contents")) else 0
    signal = sum(1 for token in ("适用于", "规定", "要求", "试验", "定义", "保护", "输出", "电压", "功率", "效率") if token in sentence)
    return (signal - penalty, len(sentence))


def _definition_anchor(text: str, max_chars: int = 42) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip(" ，,;；。")


def _query_anchor(text: str, max_chars: int = 18) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip(" ，,;；。") + "..."


def _strip_html(text: str) -> str:
    stripped = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
    stripped = re.sub(r"<style.*?</style>", " ", stripped, flags=re.S | re.I)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    return html.unescape(stripped)


def _safe_json(value: object) -> object:
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def _normalize_compare(value: str) -> str:
    text = value.lower()
    text = text.replace("—", "-").replace("／", "/")
    text = re.sub(r"\s+", "", text)
    return text


def _render_pytest_file(doc_id: str, cases: list[dict[str, str]]) -> str:
    safe_doc_id = _safe_identifier(doc_id.lower())
    lines = [
        "from __future__ import annotations",
        "",
        "import json",
        "from pathlib import Path",
        "",
        "import pytest",
        "",
        "from enterprise_agent_kb.answer_api import answer_query",
        "from enterprise_agent_kb.query_api import build_query_context",
        "",
        'WORKSPACE = Path("knowledge_base")',
        "",
        "",
        "def _normalize(value: str) -> str:",
        '    text = value.lower().replace("—", "-").replace("／", "/")',
        '    return "".join(text.split())',
        "",
        "",
        "def _assert_case(case: dict[str, str]) -> None:",
        '    expected = _normalize(case["must_include"])',
        '    target_doc_id = str(case.get("target_doc_id") or "") or None',
        '    if case.get("assert_mode") == "context_contains":',
        '        context = build_query_context(WORKSPACE, case["query"], limit=8, preferred_doc_id=target_doc_id)',
        '        blob = json.dumps(context, ensure_ascii=False)',
        '    else:',
        '        answer = answer_query(WORKSPACE, case["query"], limit=8, preferred_doc_id=target_doc_id)',
        '        blob = "\\n".join(',
        '            [',
        '                str(answer.get("direct_answer", "")),',
        '                *[str(item) for item in answer.get("summary", [])],',
        '                *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_facts", [])],',
        '                *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_evidence", [])],',
        '                *[json.dumps(item, ensure_ascii=False) for item in answer.get("related_wiki_pages", [])],',
        '            ]',
        '        )',
        '    if target_doc_id:',
        '        assert _normalize(target_doc_id) in _normalize(blob)',
        '    assert expected in _normalize(blob)',
        "",
    ]
    for index, case in enumerate(cases, start=1):
        marker_lines = _pytest_marker_lines_for_case(case)
        lines.extend(
            [
                "@pytest.mark.integration",
                "@pytest.mark.benchmark",
                *marker_lines,
                f"def test_{safe_doc_id}_golden_{index}() -> None:",
                f"    case = {json.dumps(case, ensure_ascii=False)!r}",
                "    _assert_case(json.loads(case))",
                "",
            ]
        )
    return "\n".join(lines)


def _pytest_marker_lines_for_case(case: dict[str, str]) -> list[str]:
    markers: list[str] = []
    source = str(case.get("source") or "").strip()
    kind = str(case.get("kind") or "").strip()
    if source == "coverage" or kind.startswith("coverage_"):
        markers.append("@pytest.mark.coverage")
    if kind == "page_coverage":
        markers.append("@pytest.mark.page_coverage")
    return markers


def _select_validated_cases(
    workspace_root: Path,
    candidate_pool: list[dict[str, str]],
    target_count: int,
) -> list[dict[str, str]]:
    prioritized = _prioritize_cases(candidate_pool)
    validated: list[dict[str, str]] = []
    selected_keys: set[tuple[str, str, str]] = set()

    network_candidates = [case for case in prioritized if case.get("source") == "network"]
    other_candidates = [
        case for case in prioritized
        if case.get("source") != "network"
    ]

    network_quota = 0
    if network_candidates:
        network_quota = max(1, min(6, math.ceil(target_count * 0.2)))

    validated.extend(_validate_into(workspace_root, network_candidates, network_quota, selected_keys))
    if len(validated) < target_count:
        validated.extend(_validate_into(workspace_root, other_candidates, target_count - len(validated), selected_keys))
    if len(validated) < target_count:
        validated.extend(_validate_into(workspace_root, network_candidates, target_count - len(validated), selected_keys))

    return validated[:target_count]


def _select_cases_without_validation(
    candidate_pool: list[dict[str, str]],
    target_count: int,
) -> list[dict[str, str]]:
    prioritized = _prioritize_cases(candidate_pool)
    selected: list[dict[str, str]] = []
    selected_keys: set[tuple[str, str, str]] = set()
    covered_pages: set[int] = set()

    rq_candidates = [c for c in prioritized if c.get("kind") == "retrieval_quality"]
    aq_candidates = [c for c in prioritized if c.get("kind") == "answer_quality"]
    other_candidates = [c for c in prioritized if c.get("kind") not in {"retrieval_quality", "answer_quality"}]

    rq_quota = max(5, math.ceil(target_count * 0.3)) if rq_candidates else 0
    aq_quota = max(3, math.ceil(target_count * 0.1)) if aq_candidates else 0

    for case in rq_candidates[:rq_quota]:
        key = (case.get("query", ""), _normalize_compare(case.get("must_include", "")), case.get("assert_mode", ""))
        if key in selected_keys:
            continue
        selected.append(case)
        selected_keys.add(key)

    for case in aq_candidates[:aq_quota]:
        if len(selected) >= target_count:
            break
        key = (case.get("query", ""), _normalize_compare(case.get("must_include", "")), case.get("assert_mode", ""))
        if key in selected_keys:
            continue
        selected.append(case)
        selected_keys.add(key)

    for case in other_candidates:
        if len(selected) >= target_count:
            break
        key = (case.get("query", ""), _normalize_compare(case.get("must_include", "")), case.get("assert_mode", ""))
        if key in selected_keys:
            continue
        selected.append(case)
        selected_keys.add(key)

    for case in rq_candidates[rq_quota:]:
        if len(selected) >= target_count:
            break
        key = (case.get("query", ""), _normalize_compare(case.get("must_include", "")), case.get("assert_mode", ""))
        if key in selected_keys:
            continue
        selected.append(case)
        selected_keys.add(key)

    return selected


def _validate_into(
    workspace_root: Path,
    cases: list[dict[str, str]],
    limit: int,
    selected_keys: set[tuple[str, str, str]],
) -> list[dict[str, str]]:
    accepted: list[dict[str, str]] = []
    if limit <= 0:
        return accepted
    for case in cases:
        key = (
            case.get("query", ""),
            _normalize_compare(case.get("must_include", "")),
            case.get("assert_mode", ""),
        )
        if key in selected_keys:
            continue
        if _validate_case(workspace_root, case):
            accepted.append(case)
            selected_keys.add(key)
        if len(accepted) >= limit:
            break
    return accepted


def _validate_page_coverage(
    workspace_root: Path,
    cases: list[dict[str, str]],
    limit: int,
    selected_keys: set[tuple[str, str, str]],
) -> list[dict[str, str]]:
    accepted: list[dict[str, str]] = []
    covered_pages: set[int] = set()
    if limit <= 0:
        return accepted
    for case in cases:
        page_no = int(case.get("page_no") or 0)
        if page_no in covered_pages:
            continue
        key = (
            case.get("query", ""),
            _normalize_compare(case.get("must_include", "")),
            case.get("assert_mode", ""),
        )
        if key in selected_keys:
            continue
        if _validate_case(workspace_root, case):
            accepted.append(case)
            covered_pages.add(page_no)
            selected_keys.add(key)
        if len(accepted) >= limit:
            break
    return accepted


def _prioritize_cases(candidate_pool: list[dict[str, str]]) -> list[dict[str, str]]:
    prioritized: list[dict[str, str]] = []
    used_pages: set[int] = set()
    remainder: list[dict[str, str]] = []

    for case in candidate_pool:
        page_no = int(case.get("page_no") or 0)
        if case.get("kind") == "page_coverage" and page_no > 0 and page_no not in used_pages:
            prioritized.append(case)
            used_pages.add(page_no)
        else:
            remainder.append(case)

    remainder.sort(key=_case_priority)
    for case in remainder:
        page_no = int(case.get("page_no") or 0)
        if page_no > 0 and page_no not in used_pages:
            prioritized.append(case)
            used_pages.add(page_no)
        else:
            prioritized.append(case)
    return prioritized


def _case_priority(case: dict[str, str]) -> tuple[int, int]:
    kind = str(case.get("kind", ""))
    page_no = int(case.get("page_no") or 0)
    if kind == "page_coverage":
        rank = 0
    elif kind == "retrieval_quality":
        rank = 1
    elif kind in {"evidence", "definition", "definition_detail", "network_scope"}:
        rank = 2
    elif kind in {"standard", "publication_date", "effective_date", "network_standard", "network_publication_date", "network_effective_date"}:
        rank = 3
    elif kind in {"section", "keyword_evidence", "keyword_term"}:
        rank = 4
    else:
        rank = 5
    return (rank, page_no or 10_000)


def _validate_case(workspace_root: Path, case: dict[str, str]) -> bool:
    expected = _normalize_compare(case.get("must_include", ""))
    if not expected:
        return False
    target_doc_id = str(case.get("target_doc_id") or "").strip() or None

    try:
        if case.get("assert_mode") == "context_contains":
            context = build_query_context(workspace_root, case["query"], limit=8, preferred_doc_id=target_doc_id)
            blob = json.dumps(context, ensure_ascii=False)
        else:
            answer = answer_query(workspace_root, case["query"], limit=8, preferred_doc_id=target_doc_id)
            blob = "\n".join(
                [
                    str(answer.get("direct_answer", "")),
                    *[str(item) for item in answer.get("summary", [])],
                    *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_facts", [])],
                    *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_evidence", [])],
                    *[json.dumps(item, ensure_ascii=False) for item in answer.get("related_wiki_pages", [])],
                ]
            )
    except Exception:
        return False

    normalized_blob = _normalize_compare(blob)
    if target_doc_id and _normalize_compare(target_doc_id) not in normalized_blob:
        return False
    return _matches_expected_anchor(expected, normalized_blob)


def _validate_draft_golden_case(workspace_root: Path, case: dict[str, str], mode: str) -> bool:
    if mode == "trace":
        return _validate_case_source_trace(workspace_root, case)
    if mode == "answer":
        return _validate_case(workspace_root, case)
    if mode == "hybrid":
        return _validate_case_source_trace(workspace_root, case) and _validate_case(workspace_root, case)
    raise ValueError(f"unsupported validation mode: {mode}")


def run_golden_source_trace_for_document(workspace_root: Path, doc_id: str) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    tests_dir = paths.root.parent / "tests" / "generated"
    golden_path = tests_dir / f"{doc_id}.golden.json"
    if not golden_path.exists():
        generate_golden_tests_for_document(workspace_root, doc_id, validate_cases=False, include_network=False)
    payload = json.loads(golden_path.read_text(encoding="utf-8"))
    cases = [case for case in payload.get("cases", []) if isinstance(case, dict)]

    results: list[dict[str, object]] = []
    for index, case in enumerate(cases, start=1):
        passed = _validate_case_source_trace(workspace_root, case)
        results.append(
            {
                "index": index,
                "kind": case.get("kind"),
                "query": case.get("query"),
                "target_doc_id": case.get("target_doc_id") or doc_id,
                "passed": passed,
            }
        )

    passed_count = sum(1 for item in results if item["passed"])
    failed_count = len(results) - passed_count
    return {
        "doc_id": doc_id,
        "json_path": str(golden_path),
        "case_count": len(results),
        "passed": passed_count,
        "failed": failed_count,
        "success": failed_count == 0,
        "results": results,
    }


def _validate_case_source_trace(workspace_root: Path, case: dict[str, str]) -> bool:
    expected = _normalize_compare(str(case.get("must_include") or ""))
    target_doc_id = str(case.get("target_doc_id") or "").strip()
    if not expected or not target_doc_id:
        return False

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        evidence_rows = connection.execute(
            """
            SELECT normalized_text
            FROM evidence
            WHERE doc_id = ?
            """,
            (target_doc_id,),
        ).fetchall()
        fact_rows = connection.execute(
            """
            SELECT predicate, object_value, qualifiers_json
            FROM facts
            WHERE source_doc_id = ?
            """,
            (target_doc_id,),
        ).fetchall()
        wiki_rows = connection.execute(
            """
            SELECT title, slug
            FROM wiki_pages
            WHERE json_extract(source_doc_ids_json, '$[0]') = ?
            """,
            (target_doc_id,),
        ).fetchall()
    finally:
        connection.close()

    blob = "\n".join(
        [
            *[str(row["normalized_text"] or "") for row in evidence_rows],
            *[f"{row['predicate']} {row['object_value'] or ''} {row['qualifiers_json'] or ''}" for row in fact_rows],
            *[f"{row['title'] or ''} {row['slug'] or ''}" for row in wiki_rows],
        ]
    )
    return _matches_expected_anchor(expected, _normalize_compare(blob))


def _matches_expected_anchor(expected: str, normalized_blob: str) -> bool:
    if not expected:
        return False
    if expected in normalized_blob:
        return True
    compact = expected.strip()
    if len(compact) >= 18 and compact[:18] in normalized_blob:
        return True
    semantic_expected = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]", "", compact)
    semantic_blob = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]", "", normalized_blob)
    if len(semantic_expected) >= 16 and semantic_expected[:16] in semantic_blob:
        return True
    tokens = [token for token in re.split(r"[^A-Za-z0-9\u4e00-\u9fff]+", compact) if len(token) >= 2]
    if len(tokens) >= 2:
        matched = sum(1 for token in tokens[:6] if _normalize_compare(token) in normalized_blob)
        return matched >= min(2, len(tokens))
    return False


def _page_coverage_summary(local_context: dict[str, object], cases: list[dict[str, str]]) -> dict[str, object]:
    all_pages = list(local_context.get("pages_with_evidence", []))
    covered_pages = sorted({int(item.get("page_no") or 0) for item in cases if int(item.get("page_no") or 0) > 0})
    uncovered_pages = [page for page in all_pages if page not in covered_pages]
    return {
        "page_coverage_count": len(covered_pages),
        "covered_pages": covered_pages,
        "uncovered_pages": uncovered_pages,
    }


def run_golden_tests_for_document(
    workspace_root: Path,
    doc_id: str,
    *,
    marker: str = "integration or benchmark",
) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    tests_dir = paths.root.parent / "tests" / "generated"
    safe_doc_id = _safe_identifier(doc_id.lower())
    py_path = tests_dir / f"test_{safe_doc_id}_golden.py"
    if not py_path.exists():
        generate_golden_tests_for_document(workspace_root, doc_id)
    if not py_path.exists():
        raise ValueError(f"generated pytest file missing for {doc_id}")

    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-m",
        marker,
        str(py_path),
    ]
    completed = subprocess.run(
        command,
        cwd=str(paths.root.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1200,
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    combined = "\n".join(part for part in [stdout, stderr] if part).strip()
    passed, failed = _parse_pytest_counts(combined)
    pytest_counts = _parse_pytest_count_summary(combined)
    golden_path = tests_dir / f"{doc_id}.golden.json"
    summary = _build_golden_case_summary(golden_path, passed, failed)
    eval_run_id = None
    connection = connect(paths.db_file)
    try:
        cases = load_golden_cases_from_file(golden_path)
        sync_golden_cases(connection, doc_id, cases)
        structured_results = _evaluate_golden_cases_for_eval(workspace_root, doc_id, cases)
        eval_run_id = record_eval_run(
            connection,
            suite_id=f"golden:{doc_id}",
            cases=cases,
            summary={
                **summary,
                "doc_id": doc_id,
                "passed": passed,
                "failed": failed,
                "pytest_counts": pytest_counts,
                "return_code": completed.returncode,
            },
            command=" ".join(command),
            success=completed.returncode == 0,
            output=combined[-12000:],
            case_results=structured_results,
        )
        connection.commit()
    finally:
        connection.close()
    return {
        "doc_id": doc_id,
        "eval_run_id": eval_run_id,
        "pytest_path": str(py_path),
        "command": " ".join(command),
        "return_code": completed.returncode,
        "passed": passed,
        "failed": failed,
        "pytest_counts": pytest_counts,
        "success": completed.returncode == 0,
        "summary": summary,
        "output": combined[-12000:],
    }


def run_query_repair_smoke_eval(workspace_root: Path) -> dict[str, object]:
    cases = [
        {
            "case_id": _stable_eval_case_id("query_repair_smoke", index, case),
            **dict(case),
        }
        for index, case in enumerate(QUERY_REPAIR_SMOKE_CASES, start=1)
    ]
    case_results = [
        {
            "case_id": str(case["case_id"]),
            **_evaluate_single_golden_case(workspace_root, case),
        }
        for index, case in enumerate(cases, start=1)
    ]
    passed = sum(1 for item in case_results if item.get("passed"))
    failed = len(case_results) - passed
    summary = {
        "suite": "query_repair_smoke",
        "total": len(case_results),
        "passed": passed,
        "failed": failed,
    }

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        sync_golden_cases(connection, "QUERY-REPAIR", cases, source="query_repair_smoke")
        eval_run_id = record_eval_run(
            connection,
            suite_id="regression:query_repair_smoke",
            cases=cases,
            summary=summary,
            command="eakb run-query-repair-smoke",
            success=failed == 0,
            output=json.dumps(summary, ensure_ascii=False),
            case_results=case_results,
        )
        connection.commit()
    finally:
        connection.close()

    return {
        "eval_run_id": eval_run_id,
        "success": failed == 0,
        "summary": summary,
        "results": case_results,
    }


def _evaluate_golden_cases_for_eval(
    workspace_root: Path,
    doc_id: str,
    cases: list[dict[str, object]],
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("case_id") or _stable_eval_case_id(doc_id, index, case))
        results.append({"case_id": case_id, **_evaluate_single_golden_case(workspace_root, case)})
    return results


def _stable_eval_case_id(doc_id: str, index: int, case: dict[str, object]) -> str:
    import hashlib

    blob = json.dumps(
        [doc_id, index, case.get("query"), case.get("must_include"), case.get("assert_mode")],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return "CASE-" + hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16].upper()


def _evaluate_single_golden_case(workspace_root: Path, case: dict[str, object]) -> dict[str, object]:
    expected = _normalize_compare(str(case.get("must_include") or ""))
    target_doc_id = str(case.get("target_doc_id") or "").strip() or None
    negative_expected = _case_string_list(case.get("negative_expected"))
    if not expected:
        return {
            "passed": False,
            "failure_reason": "expected_anchor_missing",
            "retrieved_items": [],
            "answer": "",
            "metrics": {"expected_present": False},
        }
    try:
        if case.get("assert_mode") == "context_contains":
            context = build_query_context(workspace_root, str(case.get("query") or ""), limit=8, preferred_doc_id=target_doc_id)
            blob = json.dumps(context, ensure_ascii=False)
            retrieved_items = _retrieved_items_from_context(context)
            answer_text = ""
            answer_mode = "context_contains"
            trace_metrics = _trace_metrics_from_context(context)
        else:
            answer = answer_query(workspace_root, str(case.get("query") or ""), limit=8, preferred_doc_id=target_doc_id)
            context = answer.get("context") if isinstance(answer.get("context"), dict) else {}
            blob = "\n".join(
                [
                    str(answer.get("direct_answer", "")),
                    *[str(item) for item in answer.get("summary", [])],
                    *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_facts", [])],
                    *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_evidence", [])],
                    *[json.dumps(item, ensure_ascii=False) for item in answer.get("related_wiki_pages", [])],
                ]
            )
            retrieved_items = _retrieved_items_from_answer(answer)
            retrieval_items = _retrieved_items_from_context(context)
            if retrieval_items:
                retrieved_items = retrieval_items
            answer_text = str(answer.get("direct_answer") or "")
            answer_mode = str(answer.get("answer_mode") or "")
            trace_metrics = _trace_metrics_from_answer(answer)
    except Exception as exc:
        return {
            "passed": False,
            "failure_reason": f"evaluation_exception:{type(exc).__name__}",
            "retrieved_items": [],
            "answer": "",
            "metrics": {"exception": str(exc)[:500]},
        }

    normalized_blob = _normalize_compare(blob)
    expected_present = _matches_expected_anchor(expected, normalized_blob)
    target_doc_present = not target_doc_id or _normalize_compare(target_doc_id) in normalized_blob
    negative_hits = [
        item for item in negative_expected
        if item and _normalize_compare(item) in normalized_blob
    ]
    retrieval_quality = evaluate_retrieval_quality(
        case=case,
        retrieved_items=retrieved_items,
        trace_metrics=trace_metrics,
    )
    answer_quality = evaluate_answer_quality(
        case=case,
        answer_text=answer_text or blob,
        retrieved_items=retrieved_items,
        expected_present=expected_present,
        target_doc_present=target_doc_present,
        negative_hits=negative_hits,
        answer_mode=answer_mode,
        trace_metrics=trace_metrics,
    )
    expected_shape = str(answer_quality.get("expected_evidence_shape") or case.get("expected_evidence_shape") or case.get("evidence_shape") or "").strip()
    passed = bool(answer_quality.get("answer_pass"))
    failure_attribution = str(answer_quality.get("failure_attribution") or "")
    if passed:
        failure_reason = None
    elif failure_attribution == "forbidden_content":
        failure_reason = "negative_expected_hit"
    elif failure_attribution == "expected_answer_missing" and case.get("assert_mode") == "context_contains":
        failure_reason = "retrieval_miss"
    else:
        failure_reason = failure_attribution or "answer_quality_failed"
    return {
        "passed": passed,
        "failure_reason": failure_reason,
        "retrieved_items": retrieved_items,
        "answer": answer_text,
            "metrics": {
                "expected_present": expected_present,
                "target_doc_present": target_doc_present,
                "negative_hits": negative_hits,
                "answer_mode": answer_mode,
                "retrieval_quality": retrieval_quality,
                "answer_quality": answer_quality,
                "expected_evidence_shape": expected_shape,
                **trace_metrics,
            },
        }


def _retrieved_items_from_context(context: dict[str, object]) -> list[dict[str, object]]:
    items = []
    for hit in list(context.get("hits") or [])[:10]:
        if not isinstance(hit, dict):
            continue
        items.append(
            {
                "result_type": hit.get("result_type"),
                "result_id": hit.get("result_id"),
                "doc_id": hit.get("doc_id"),
                "page_no": hit.get("page_no"),
                "score": hit.get("score"),
                "snippet": str(hit.get("snippet") or "")[:500],
                "graph_source": bool(hit.get("graph_source")),
                "channel": hit.get("channel"),
                "channels": hit.get("channels") or [],
            }
        )
    return items


def _retrieved_items_from_answer(answer: dict[str, object]) -> list[dict[str, object]]:
    items = []
    for fact in list(answer.get("supporting_facts") or [])[:8]:
        if isinstance(fact, dict):
            items.append(
                {
                    "result_type": "fact",
                    "result_id": fact.get("fact_id"),
                    "doc_id": fact.get("doc_id"),
                    "page_no": fact.get("page_no"),
                    "snippet": json.dumps(fact.get("object"), ensure_ascii=False)[:500],
                    "graph_source": bool(fact.get("graph_path")),
                    "graph_relation": fact.get("graph_relation"),
                }
            )
    for evidence in list(answer.get("supporting_evidence") or [])[:5]:
        if isinstance(evidence, dict):
            items.append(
                {
                    "result_type": "evidence",
                    "result_id": evidence.get("evidence_id"),
                    "doc_id": evidence.get("doc_id"),
                    "page_no": evidence.get("page_no"),
                    "snippet": str(evidence.get("snippet") or "")[:500],
                }
            )
    return items[:10]


def _trace_metrics_from_answer(answer: dict[str, object]) -> dict[str, object]:
    context = answer.get("context") if isinstance(answer.get("context"), dict) else {}
    metrics = _trace_metrics_from_context(context)
    metrics["answer_mode"] = str(answer.get("answer_mode") or metrics.get("answer_mode") or "")
    metrics["fallback_reason"] = str(answer.get("fallback_reason") or "")
    return metrics


def _trace_metrics_from_context(context: dict[str, object]) -> dict[str, object]:
    retrieval_plan = context.get("retrieval_plan") if isinstance(context.get("retrieval_plan"), dict) else {}
    topic_resolution = context.get("topic_resolution") if isinstance(context.get("topic_resolution"), dict) else {}
    evidence_judgement = context.get("evidence_judgement") if isinstance(context.get("evidence_judgement"), dict) else {}
    shape_diagnostics = evidence_judgement.get("shape_diagnostics") if isinstance(evidence_judgement.get("shape_diagnostics"), dict) else {}
    shape_contract = shape_diagnostics.get("shape_contract") if isinstance(shape_diagnostics.get("shape_contract"), dict) else {}
    shape_contract_diagnosis = shape_diagnostics.get("shape_contract_diagnosis") if isinstance(shape_diagnostics.get("shape_contract_diagnosis"), dict) else {}
    candidates = topic_resolution.get("candidate_entities") if isinstance(topic_resolution.get("candidate_entities"), list) else []
    candidate_names = [
        str(item.get("canonical_name") or "")
        for item in candidates
        if isinstance(item, dict)
    ][:5]
    hits = context.get("hits") if isinstance(context.get("hits"), list) else []
    return {
        "query_type": (context.get("rewrite") or {}).get("query_type") if isinstance(context.get("rewrite"), dict) else "",
        "retrieval_channels": retrieval_plan.get("channels") if isinstance(retrieval_plan.get("channels"), list) else [],
        "graph_candidate_count": int(retrieval_plan.get("graph_candidate_count") or 0),
        "routing_summary_hit_count": int(retrieval_plan.get("routing_summary_hit_count") or 0),
        "topic_resolution_confidence": float(topic_resolution.get("confidence") or 0.0),
        "topic_candidate_names": candidate_names,
        "top_hit_doc_ids": [
            str(item.get("doc_id") or "")
            for item in hits[:5]
            if isinstance(item, dict)
        ],
        "top_hit_ids": [
            str(item.get("result_id") or "")
            for item in hits[:5]
            if isinstance(item, dict)
        ],
        "top_hit_graph_source_count": sum(
            1 for item in hits[:5]
            if isinstance(item, dict) and item.get("graph_source")
        ),
        "evidence_judge_sufficient": bool(evidence_judgement.get("sufficient")),
        "evidence_judge_reason": str(evidence_judgement.get("reason") or ""),
        "evidence_shape": str(evidence_judgement.get("evidence_shape") or ""),
        "evidence_shape_diagnostics": shape_diagnostics,
        "shape_contract_query_type": str(shape_contract.get("query_type") or ""),
        "shape_contract_allowed_shapes": _case_string_list(shape_contract.get("allowed_shapes")),
        "shape_contract_required": shape_contract.get("required") if isinstance(shape_contract, dict) else None,
        "shape_contract_matched": shape_contract.get("matched") if isinstance(shape_contract, dict) else None,
        "shape_contract_failure_reason": str(shape_contract_diagnosis.get("reason") or ""),
        "shape_contract_suggested_action": str(shape_contract_diagnosis.get("action") or ""),
    }


def _case_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _build_golden_case_summary(golden_path: Path, passed: int, failed: int) -> dict[str, object]:
    if not golden_path.exists():
        return {
            "total": passed + failed,
            "passed": passed,
            "failed": failed,
            "coverage_recall": {"total": 0, "passed": 0, "failed": 0},
            "answer_quality": {"total": 0, "passed": 0, "failed": 0},
        }
    payload = json.loads(golden_path.read_text(encoding="utf-8"))
    cases = [case for case in payload.get("cases", []) if isinstance(case, dict)]
    coverage_cases = [case for case in cases if case.get("assert_mode") == "context_contains"]
    answer_cases = [case for case in cases if case.get("assert_mode") != "context_contains"]
    total = len(cases)
    success = failed == 0
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "coverage_recall": {
            "label": "覆盖召回",
            "total": len(coverage_cases),
            "passed": len(coverage_cases) if success else None,
            "failed": 0 if success else None,
            "description": "验证原文片段能进入检索上下文，不代表最终回答质量。",
        },
        "answer_quality": {
            "label": "答案质量",
            "total": len(answer_cases),
            "passed": len(answer_cases) if success else None,
            "failed": 0 if success else None,
            "description": "验证最终答案、摘要或依据中包含关键答案。",
        },
        "case_mix": {
            "context_contains": len(coverage_cases),
            "rich_answer": len(answer_cases),
        },
    }


def run_coverage_promoted_tests_for_document(
    workspace_root: Path,
    doc_id: str,
    *,
    validation_mode: str = "trace",
) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    tests_dir = paths.root.parent / "tests" / "generated"
    golden_path = tests_dir / f"{doc_id}.golden.json"
    if not golden_path.exists():
        raise ValueError(f"golden file missing for {doc_id}: {golden_path}")

    payload = json.loads(golden_path.read_text(encoding="utf-8"))
    cases = [
        case
        for case in payload.get("cases", [])
        if isinstance(case, dict)
        and (case.get("source") == "coverage" or str(case.get("kind") or "").startswith("coverage_"))
    ]
    results: list[dict[str, object]] = []
    for index, case in enumerate(cases, start=1):
        validation = _validate_coverage_case(workspace_root, doc_id, case, validation_mode=validation_mode)
        results.append(
            {
                "index": index,
                "query": case.get("query"),
                "kind": case.get("kind"),
                "coverage_unit_id": case.get("coverage_unit_id"),
                "passed": validation["passed"],
                "validation_mode": validation["mode"],
            }
        )
    passed_count = sum(1 for item in results if item["passed"])
    failed_count = len(results) - passed_count
    return {
        "doc_id": doc_id,
        "json_path": str(golden_path),
        "case_count": len(results),
        "validation_mode": validation_mode,
        "passed": passed_count,
        "failed": failed_count,
        "success": failed_count == 0,
        "results": results,
    }


def run_coverage_promoted_pytest_for_document(workspace_root: Path, doc_id: str) -> dict[str, object]:
    return run_golden_tests_for_document(workspace_root, doc_id, marker="coverage")


def _validate_coverage_case(
    workspace_root: Path,
    doc_id: str,
    case: dict[str, str],
    *,
    validation_mode: str,
) -> dict[str, object]:
    mode = validation_mode if validation_mode in {"trace", "context", "rich", "hybrid"} else "trace"

    if mode == "trace":
        return _validate_coverage_case_trace(workspace_root, doc_id, case)

    if mode == "context":
        context_case = dict(case)
        context_case["assert_mode"] = "context_contains"
        return {
            "passed": _validate_case(workspace_root, context_case),
            "mode": "context_contains",
        }

    if _validate_case(workspace_root, case):
        return {"passed": True, "mode": str(case.get("assert_mode") or "rich_answer")}
    if mode == "rich":
        return {"passed": False, "mode": "failed"}

    context_case = dict(case)
    context_case["assert_mode"] = "context_contains"
    if _validate_case(workspace_root, context_case):
        return {"passed": True, "mode": "context_fallback"}
    return {"passed": False, "mode": "failed"}


def _validate_coverage_case_trace(workspace_root: Path, doc_id: str, case: dict[str, str]) -> dict[str, object]:
    unit_id = str(case.get("coverage_unit_id") or "").strip()
    semantic_key = str(case.get("coverage_semantic_key") or case.get("must_include") or "").strip()
    if not unit_id:
        return {"passed": False, "mode": "trace_missing_unit_id"}

    paths = AppPaths.from_root(workspace_root)
    matrix_path = paths.coverage_reports / f"{doc_id}.coverage_matrix.json"
    if not matrix_path.exists():
        build_coverage_for_document(workspace_root, doc_id)
    if not matrix_path.exists():
        return {"passed": False, "mode": "trace_missing_matrix"}

    payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    for row in payload.get("items", []):
        if not isinstance(row, dict) or str(row.get("unit_id") or "") != unit_id:
            continue
        covered_by = row.get("covered_by") if isinstance(row.get("covered_by"), dict) else {}
        has_trace = bool(covered_by.get("evidence_ids")) and bool(covered_by.get("fact_ids"))
        has_object = bool(covered_by.get("entity_ids") or covered_by.get("wiki_page_ids"))
        row_semantic_key = str(row.get("semantic_key") or "")
        semantic_match = not semantic_key or _matches_expected_anchor(
            _normalize_compare(semantic_key),
            _normalize_compare(row_semantic_key),
        )
        return {
            "passed": has_trace and has_object and semantic_match,
            "mode": "trace_matrix",
        }
    return {"passed": False, "mode": "trace_unit_not_found"}


def _parse_pytest_counts(output: str) -> tuple[int, int]:
    passed = 0
    failed = 0
    passed_match = re.search(r"(\d+)\s+passed", output)
    failed_match = re.search(r"(\d+)\s+failed", output)
    if passed_match:
        passed = int(passed_match.group(1))
    if failed_match:
        failed = int(failed_match.group(1))
    return passed, failed


def _parse_pytest_count_summary(output: str) -> dict[str, int]:
    keys = ("passed", "failed", "deselected", "skipped", "xfailed", "xpassed", "error", "errors")
    counts = {key: 0 for key in keys}
    for key in keys:
        matches = re.findall(rf"(\d+)\s+{re.escape(key)}\b", str(output or ""), flags=re.IGNORECASE)
        if matches:
            counts[key] = int(matches[-1])
    counts["selected"] = counts["passed"] + counts["failed"] + counts["skipped"] + counts["xfailed"] + counts["xpassed"] + counts["error"] + counts["errors"]
    counts["collected"] = counts["selected"] + counts["deselected"]
    return counts


def _safe_identifier(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "generated"
