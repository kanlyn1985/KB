"""Coverage test draft generation, validation, readiness, and promotion.

Extracted from `generated_tests._impl` to isolate the draft lifecycle
(generate, validate, assess readiness, close gaps, promote) from the
golden-case construction and lifecycle-management concerns.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import AppPaths
from ..coverage import build_coverage_for_document, build_test_gap_candidates_for_document
from ..coverage_diagnostics import build_all_docs_uncovered_priority_report
from ..closed_loop_store import sync_golden_cases
from ..db import connect
from ._case_builders import _dedupe_cases, _load_or_create_golden_payload, _render_pytest_file
from ._case_helpers import _count_by_key, _normalize_compare, _safe_identifier, _safe_json, _unique_values
from ._context import _active_document_ids
from ._lifecycle import run_coverage_promoted_tests_for_document
from ._validators import _is_structured_clause_anchor, _is_usable_golden_anchor, _validate_draft_golden_case

def generate_coverage_test_drafts_for_document(
    workspace_root: Path,
    doc_id: str,
    *,
    limit: int | None = 50,
    rebuild_coverage: bool = False,
    validate: bool = False,
    excluded_unit_ids: set[str] | None = None,
) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    tests_dir = paths.root.parent / "tests" / "generated"
    tests_dir.mkdir(parents=True, exist_ok=True)

    gap_result = build_test_gap_candidates_for_document(
        workspace_root,
        doc_id,
        limit=limit,
        rebuild=rebuild_coverage,
        excluded_unit_ids=excluded_unit_ids,
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
        "excluded_candidate_count": gap_payload.get("excluded_candidate_count", 0),
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
def close_coverage_test_gaps(
    workspace_root: Path,
    *,
    doc_ids: list[str] | None = None,
    limit_per_doc: int | None = 25,
    validation_mode: str = "trace",
    rebuild_coverage: bool = False,
    promote: bool = True,
) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    selected_doc_ids = doc_ids or _active_document_ids(paths)
    documents: list[dict[str, object]] = []
    totals = {
        "draft_case_count": 0,
        "validation_passed_count": 0,
        "validation_failed_count": 0,
        "promoted_case_count": 0,
        "added_case_count": 0,
        "coverage_test_passed": 0,
        "coverage_test_failed": 0,
    }

    for doc_id in selected_doc_ids:
        rejected_units = _load_coverage_test_rejections(paths).get(doc_id, {})
        draft = generate_coverage_test_drafts_for_document(
            workspace_root,
            doc_id,
            limit=limit_per_doc,
            rebuild_coverage=rebuild_coverage,
            validate=False,
            excluded_unit_ids=set(rejected_units),
        )
        validation = validate_coverage_test_drafts_for_document(
            workspace_root,
            doc_id,
            mode=validation_mode,
        )
        readiness = assess_coverage_test_draft_readiness_for_document(workspace_root, doc_id)
        rejection_update = _record_coverage_test_rejections(
            paths,
            doc_id,
            readiness.get("cases", []),
        )
        promotion: dict[str, object] | None = None
        coverage_run: dict[str, object] | None = None
        coverage_rebuild: dict[str, object] | None = None
        if promote:
            promotion = promote_coverage_test_drafts_for_document(
                workspace_root,
                doc_id,
                require_validated=True,
            )
            coverage_run = run_coverage_promoted_tests_for_document(
                workspace_root,
                doc_id,
                validation_mode=validation_mode,
            )
            coverage_rebuild_result = build_coverage_for_document(workspace_root, doc_id)
            coverage_rebuild = {
                "source_unit_count": coverage_rebuild_result.source_unit_count,
                "test_coverage_rate": coverage_rebuild_result.test_coverage_rate,
                "uncovered_counts": coverage_rebuild_result.uncovered_counts,
                "summary_path": str(coverage_rebuild_result.summary_path),
            }

        document_result = {
            "doc_id": doc_id,
            "draft_case_count": int(draft.get("draft_case_count") or 0),
            "source_gap_count": int(draft.get("source_gap_count") or 0),
            "skipped_candidate_count": int(draft.get("skipped_candidate_count") or 0),
            "excluded_candidate_count": int(draft.get("excluded_candidate_count") or 0),
            "validation_passed_count": int(validation.get("passed_count") or 0),
            "validation_failed_count": int(validation.get("failed_count") or 0),
            "new_rejection_count": int(rejection_update.get("new_rejection_count") or 0),
            "total_rejection_count": int(rejection_update.get("total_rejection_count") or 0),
            "promoted_case_count": int(promotion.get("promoted_case_count") or 0) if promotion else 0,
            "added_case_count": int(promotion.get("added_case_count") or 0) if promotion else 0,
            "pruned_obsolete_case_count": int(promotion.get("pruned_obsolete_case_count") or 0) if promotion else 0,
            "coverage_test_passed": int(coverage_run.get("passed") or 0) if coverage_run else 0,
            "coverage_test_failed": int(coverage_run.get("failed") or 0) if coverage_run else 0,
            "draft_path": draft.get("json_path"),
            "validation_path": validation.get("json_path"),
            "golden_path": promotion.get("json_path") if promotion else None,
            "coverage_summary_path": coverage_rebuild.get("summary_path") if coverage_rebuild else None,
        }
        documents.append(document_result)
        totals["draft_case_count"] += document_result["draft_case_count"]
        totals["validation_passed_count"] += document_result["validation_passed_count"]
        totals["validation_failed_count"] += document_result["validation_failed_count"]
        totals["promoted_case_count"] += document_result["promoted_case_count"]
        totals["added_case_count"] += document_result["added_case_count"]
        totals["coverage_test_passed"] += document_result["coverage_test_passed"]
        totals["coverage_test_failed"] += document_result["coverage_test_failed"]

    priority_report = build_all_docs_uncovered_priority_report(
        workspace_root,
        rebuild_missing_coverage=False,
    )
    payload = {
        "document_count": len(selected_doc_ids),
        "limit_per_doc": limit_per_doc,
        "validation_mode": validation_mode,
        "promote": promote,
        "totals": totals,
        "documents": documents,
        "uncovered_priority_report": {
            "document_count": priority_report.document_count,
            "issue_count": priority_report.issue_count,
            "json_path": str(priority_report.json_path),
            "report_path": str(priority_report.report_path),
        },
        "success": totals["validation_failed_count"] == 0 and totals["coverage_test_failed"] == 0,
    }
    output_path = paths.coverage_reports / "coverage_test_gap_closure_latest.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["json_path"] = str(output_path)
    return payload
def _coverage_test_rejections_path(paths: AppPaths) -> Path:
    return paths.coverage_reports / "coverage_test_gap_rejections.json"
def _load_coverage_test_rejections(paths: AppPaths) -> dict[str, dict[str, object]]:
    path = _coverage_test_rejections_path(paths)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    docs = payload.get("documents") if isinstance(payload.get("documents"), dict) else {}
    result: dict[str, dict[str, object]] = {}
    for doc_id, units in docs.items():
        if isinstance(units, dict):
            result[str(doc_id)] = dict(units)
    return result
def _record_coverage_test_rejections(
    paths: AppPaths,
    doc_id: str,
    assessed_cases: object,
) -> dict[str, int]:
    existing = _load_coverage_test_rejections(paths)
    doc_rejections = dict(existing.get(doc_id, {}))
    before_count = len(doc_rejections)
    for case in assessed_cases if isinstance(assessed_cases, list) else []:
        if not isinstance(case, dict):
            continue
        status = str(case.get("readiness_status") or "")
        if status in {"promotable", "ready_for_validation"}:
            continue
        unit_id = str(case.get("unit_id") or "").strip()
        if not unit_id:
            continue
        doc_rejections[unit_id] = {
            "readiness_status": status,
            "semantic_key": case.get("semantic_key"),
            "query": case.get("query"),
            "quality_flags": case.get("quality_flags") or [],
            "readiness_reasons": case.get("readiness_reasons") or [],
        }
    existing[doc_id] = doc_rejections
    path = _coverage_test_rejections_path(paths)
    path.write_text(
        json.dumps(
            {
                "documents": existing,
                "total_rejection_count": sum(len(units) for units in existing.values()),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "new_rejection_count": max(len(doc_rejections) - before_count, 0),
        "total_rejection_count": len(doc_rejections),
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
    existing_cases, pruned_obsolete_count = _prune_obsolete_coverage_cases(
        workspace_root,
        doc_id,
        existing_cases,
    )
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
        "pruned_obsolete_case_count": pruned_obsolete_count,
        "total_case_count": len(merged_cases),
        "json_path": str(golden_path),
        "pytest_path": str(py_path),
        "draft_path": str(draft_path),
    }
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
    unit_type = str(candidate.get("unit_type") or "")
    assert_mode = str(candidate.get("recommended_assert_mode") or "rich_answer").strip() or "rich_answer"
    golden_assert_mode = "context_contains" if assert_mode == "context_contains" else "rich_answer"
    query = str(candidate.get("recommended_query_seed") or "").strip()

    golden_case = {
        "kind": _draft_kind_for_unit(unit_type),
        "query": query,
        "must_include": primary_must_include,
        "source": "coverage",
        "assert_mode": golden_assert_mode,
        "target_doc_id": doc_id,
        "expected_doc_id": doc_id,
    }
    evidence_shape = _draft_expected_shape_for_unit(unit_type)
    if evidence_shape:
        golden_case["expected_evidence_shape"] = evidence_shape

    # Enrich assertions based on unit type
    if unit_type == "parameter_row_unit" and golden_assert_mode != "context_contains":
        golden_case["assert_mode"] = "parameter_value"
        if not evidence_shape:
            golden_case["expected_evidence_shape"] = "parameter_table_row"
        # Add unit from metadata as an additional must_include anchor
        metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
        unit_name = str(metadata.get("unit") or "").strip()
        if unit_name and unit_name not in must_include_values:
            golden_case["must_include"] = f"{primary_must_include} {unit_name}"

    page_no = int(candidate.get("page_no") or 0)
    if page_no:
        golden_case["page_no"] = page_no

    return {
        "name": _draft_case_name(candidate),
        "status": "draft",
        "unit_id": candidate.get("unit_id"),
        "unit_type": unit_type,
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
def _draft_expected_shape_for_unit(unit_type: str) -> str:
    if unit_type == "definition_unit":
        return "term_definition"
    if unit_type == "parameter_row_unit":
        return "parameter_definition"
    if unit_type == "requirement_unit":
        return "requirement"
    if unit_type == "process_unit":
        return "process_activity"
    return ""
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
        f"- excluded_candidate_count: {payload.get('excluded_candidate_count', 0)}",
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
            if key
            in {
                "kind",
                "query",
                "must_include",
                "source",
                "assert_mode",
                "page_no",
                "target_doc_id",
                "expected_evidence_shape",
            }
        }
        case["coverage_unit_id"] = str(draft_case.get("unit_id") or "")
        case["coverage_semantic_key"] = str(draft_case.get("semantic_key") or "")
        promoted.append(case)
    return _dedupe_cases(promoted)
def _prune_obsolete_coverage_cases(
    workspace_root: Path,
    doc_id: str,
    cases: list[dict[str, object]],
) -> tuple[list[dict[str, object]], int]:
    active_unit_ids, active_semantic_keys = _active_coverage_unit_identity(workspace_root, doc_id)
    if not active_unit_ids and not active_semantic_keys:
        return cases, 0
    kept: list[dict[str, object]] = []
    pruned = 0
    for case in cases:
        unit_id = str(case.get("coverage_unit_id") or "").strip()
        is_coverage_case = case.get("source") == "coverage" or str(case.get("kind") or "").startswith("coverage_")
        semantic_key = _normalize_compare(str(case.get("coverage_semantic_key") or case.get("must_include") or ""))
        has_active_trace = bool(unit_id and unit_id in active_unit_ids) or bool(semantic_key and semantic_key in active_semantic_keys)
        if is_coverage_case and unit_id and not has_active_trace:
            pruned += 1
            continue
        kept.append(case)
    return kept, pruned
def _active_coverage_unit_identity(workspace_root: Path, doc_id: str) -> tuple[set[str], set[str]]:
    paths = AppPaths.from_root(workspace_root)
    matrix_path = paths.coverage_reports / f"{doc_id}.coverage_matrix.json"
    if not matrix_path.exists():
        build_coverage_for_document(workspace_root, doc_id)
    if not matrix_path.exists():
        return set(), set()
    try:
        payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set(), set()
    unit_ids: set[str] = set()
    semantic_keys: set[str] = set()
    for row in payload.get("items", []):
        if not isinstance(row, dict):
            continue
        unit_id = str(row.get("unit_id") or "").strip()
        if unit_id:
            unit_ids.add(unit_id)
        semantic_key = _normalize_compare(str(row.get("semantic_key") or ""))
        if semantic_key:
            semantic_keys.add(semantic_key)
    return unit_ids, semantic_keys
