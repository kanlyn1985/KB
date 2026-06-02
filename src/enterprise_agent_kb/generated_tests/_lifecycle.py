"""Golden-case lifecycle: run, evaluate, activate, detect stale, revalidate.

Extracted from `generated_tests._impl` to isolate the run-time
orchestration of generated test cases (source trace, golden test run,
query-repair smoke eval, auto-activation, staleness detection,
revalidation) from the draft and case-construction concerns.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from ..answer_api import answer_query
from ..closed_loop_store import load_golden_cases_from_file, record_eval_run
from ..config import AppPaths
from ..query_api import build_query_context
from ..answer_quality import evaluate_answer_quality
from ..retrieval_quality import evaluate_retrieval_quality
from ._case_helpers import _normalize_compare, _safe_identifier, _safe_json
from ._validators import _validate_coverage_case

EVAL_RETRIEVAL_LIMIT = 10

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
            context = build_query_context(workspace_root, str(case.get("query") or ""), limit=EVAL_RETRIEVAL_LIMIT, preferred_doc_id=target_doc_id)
            blob = json.dumps(context, ensure_ascii=False)
            retrieved_items = _retrieved_items_from_context(context)
            answer_text = ""
            answer_mode = "context_contains"
            trace_metrics = _trace_metrics_from_context(context)
        else:
            answer = answer_query(workspace_root, str(case.get("query") or ""), limit=EVAL_RETRIEVAL_LIMIT, preferred_doc_id=target_doc_id)
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
def auto_activate_golden_cases(
    workspace_root: Path,
    doc_id: str,
    max_candidates: int = 500,
    validate_on_promote: bool = True,
) -> dict[str, object]:
    """Auto-activate golden cases for uncovered source units.

    Generates coverage test drafts, validates them deterministically,
    promotes passing cases to golden.json, then rebuilds coverage.
    Only cases that pass deterministic validation are promoted.

    When validate_on_promote is True, promoted cases are additionally
    validated via source trace. Cases that fail trace validation are
    downgraded from active to draft status in the database.
    """
    paths = AppPaths.from_root(workspace_root)
    rejected_units = _load_coverage_test_rejections(paths).get(doc_id, {})
    draft = generate_coverage_test_drafts_for_document(
        workspace_root,
        doc_id,
        limit=max_candidates,
        rebuild_coverage=True,
        validate=False,
        excluded_unit_ids=set(rejected_units),
    )
    validation = validate_coverage_test_drafts_for_document(
        workspace_root,
        doc_id,
        mode="trace",
    )
    readiness = assess_coverage_test_draft_readiness_for_document(workspace_root, doc_id)
    _record_coverage_test_rejections(paths, doc_id, readiness.get("cases", []))

    promotion = promote_coverage_test_drafts_for_document(
        workspace_root,
        doc_id,
        require_validated=True,
    )

    # Post-promote validation: downgrade trace-failing cases to draft
    trace_downgraded = 0
    if validate_on_promote and int(promotion.get("promoted_case_count") or 0) > 0:
        trace_result = run_golden_source_trace_for_document(workspace_root, doc_id)
        trace_failures = [
            item for item in trace_result.get("results", [])
            if isinstance(item, dict) and not item.get("passed")
        ]
        if trace_failures:
            connection = connect(paths.db_file)
            try:
                for item in trace_failures:
                    query = str(item.get("query") or "")
                    if not query:
                        continue
                    connection.execute(
                        "UPDATE golden_cases SET status = 'draft' WHERE doc_id = ? AND query = ? AND status = 'active'",
                        (doc_id, query),
                    )
                trace_downgraded = connection.execute(
                    "SELECT changes() as c"
                ).fetchone()["c"]
                connection.commit()
            finally:
                connection.close()

    coverage_rebuild = build_coverage_for_document(workspace_root, doc_id)

    return {
        "doc_id": doc_id,
        "draft_case_count": int(draft.get("draft_case_count") or 0),
        "source_gap_count": int(draft.get("source_gap_count") or 0),
        "validation_passed_count": int(validation.get("passed_count") or 0),
        "validation_failed_count": int(validation.get("failed_count") or 0),
        "promoted_case_count": int(promotion.get("promoted_case_count") or 0),
        "added_case_count": int(promotion.get("added_case_count") or 0),
        "trace_downgraded_count": trace_downgraded,
        "test_coverage_rate": coverage_rebuild.test_coverage_rate,
        "source_unit_count": coverage_rebuild.source_unit_count,
    }
def detect_stale_golden_cases(
    workspace_root: Path,
    doc_id: str,
) -> dict[str, object]:
    """Detect golden cases that may be stale after document re-parse.

    A golden case is stale if the golden.json file was modified before
    the document's update_time in the database (meaning the document
    was re-parsed after the golden cases were generated).
    """
    paths = AppPaths.from_root(workspace_root)
    tests_dir = paths.root.parent / "tests" / "generated"
    golden_path = tests_dir / f"{doc_id}.golden.json"

    if not golden_path.exists():
        return {
            "doc_id": doc_id,
            "total_cases": 0,
            "stale_count": 0,
            "stale_cases": [],
            "fresh_cases": [],
            "has_golden_file": False,
        }

    golden_payload = json.loads(golden_path.read_text(encoding="utf-8"))
    cases = [c for c in golden_payload.get("cases", []) if isinstance(c, dict)]
    golden_mtime = golden_path.stat().st_mtime

    connection = connect(paths.db_file)
    try:
        row = connection.execute(
            "SELECT update_time FROM documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
    finally:
        connection.close()

    doc_update_time = row["update_time"] if row else None

    stale_cases = []
    fresh_cases = []
    for case in cases:
        case_mtime = float(case.get("_generated_at_ts") or 0.0) if case.get("_generated_at_ts") else golden_mtime
        is_stale = doc_update_time and case_mtime < _iso_to_timestamp(str(doc_update_time))
        if is_stale:
            stale_cases.append(case)
        else:
            fresh_cases.append(case)

    return {
        "doc_id": doc_id,
        "total_cases": len(cases),
        "stale_count": len(stale_cases),
        "stale_cases": stale_cases,
        "fresh_cases": fresh_cases,
        "has_golden_file": True,
        "doc_update_time": doc_update_time,
        "golden_mtime": golden_mtime,
    }
def revalidate_stale_golden_cases(
    workspace_root: Path,
    doc_id: str,
) -> dict[str, object]:
    """Re-validate stale golden cases and remove failing ones.

    1. Detect stale cases via detect_stale_golden_cases
    2. Re-run deterministic validation on each stale case
    3. Remove failing cases from golden.json
    4. Keep passing cases (they're still valid despite being "stale")
    5. Re-sync golden cases to SQLite
    """
    stale_info = detect_stale_golden_cases(workspace_root, doc_id)
    if not stale_info["has_golden_file"] or stale_info["stale_count"] == 0:
        return {
            "doc_id": doc_id,
            "revalidated_count": 0,
            "passed_count": 0,
            "removed_count": 0,
        }

    stale_cases = stale_info["stale_cases"]
    passed_cases = []
    removed_cases = []

    for case in stale_cases:
        if _validate_case(workspace_root, case):
            passed_cases.append(case)
        else:
            removed_cases.append(case)

    if removed_cases:
        paths = AppPaths.from_root(workspace_root)
        tests_dir = paths.root.parent / "tests" / "generated"
        golden_path = tests_dir / f"{doc_id}.golden.json"
        golden_payload = json.loads(golden_path.read_text(encoding="utf-8"))
        all_cases = [c for c in golden_payload.get("cases", []) if isinstance(c, dict)]

        removed_queries = {c.get("query") for c in removed_cases}
        filtered_cases = [c for c in all_cases if c.get("query") not in removed_queries]

        golden_payload["cases"] = filtered_cases
        golden_path.write_text(
            json.dumps(golden_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        sync_golden_cases(paths.db_file, doc_id, golden_path)

    return {
        "doc_id": doc_id,
        "revalidated_count": len(stale_cases),
        "passed_count": len(passed_cases),
        "removed_count": len(removed_cases),
    }
def _iso_to_timestamp(iso_str: str) -> float:
    """Convert ISO timestamp string to Unix timestamp float."""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0
