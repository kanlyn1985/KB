from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .closed_loop_store import _runtime_code_version, record_eval_run, sync_golden_cases, utc_now
from .config import AppPaths
from .db import connect
from .query_api import build_query_context
from .retrieval_quality import evaluate_retrieval_quality


@dataclass(frozen=True)
class UserQueryRetrievalEvalResult:
    eval_run_id: str
    suite_id: str
    case_count: int
    passed: int
    failed: int
    success: bool
    json_path: Path
    report_path: Path


def run_user_query_retrieval_eval(
    workspace_root: Path,
    *,
    case_file: Path | None = None,
    suite_id: str = "regression:user_query_retrieval",
    limit: int = 10,
    output_dir: Path | None = None,
) -> UserQueryRetrievalEvalResult:
    paths = AppPaths.from_root(workspace_root)
    cases_path = case_file or _default_case_file(paths.root.parent)
    cases = _load_cases(cases_path)
    timestamp = utc_now()
    case_results = [
        _evaluate_case(paths.root, case, index=index, limit=limit)
        for index, case in enumerate(cases, start=1)
    ]
    passed = sum(1 for item in case_results if item.get("passed"))
    failed = len(case_results) - passed
    summary = _summary(cases, case_results, cases_path)

    connection = connect(paths.db_file)
    try:
        sync_golden_cases(connection, "USER-QUERY-RETRIEVAL", cases, source="user_query_retrieval")
        eval_run_id = record_eval_run(
            connection,
            suite_id=suite_id,
            cases=cases,
            summary=summary,
            command=f"eakb run-user-query-retrieval-eval --case-file {cases_path} --limit {limit}",
            success=failed == 0,
            output=json.dumps(summary, ensure_ascii=False),
            code_version=_runtime_code_version(),
            case_results=case_results,
        )
        connection.commit()
    finally:
        connection.close()

    report_dir = output_dir or paths.root.parent / "tests" / "generated"
    report_dir.mkdir(parents=True, exist_ok=True)
    date_token = timestamp[:10]
    json_path = report_dir / f"user_query_retrieval_eval_{date_token}.json"
    report_path = report_dir / f"user_query_retrieval_eval_{date_token}.md"
    payload = {
        "eval_run_id": eval_run_id,
        "suite_id": suite_id,
        "generated_at": timestamp,
        "case_file": str(cases_path),
        "summary": summary,
        "results": case_results,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(_render_report(payload), encoding="utf-8")
    return UserQueryRetrievalEvalResult(
        eval_run_id=eval_run_id,
        suite_id=suite_id,
        case_count=len(cases),
        passed=passed,
        failed=failed,
        success=failed == 0,
        json_path=json_path,
        report_path=report_path,
    )


def _default_case_file(repo_root: Path) -> Path:
    return repo_root / "tests" / "generated" / "real_user_query_retrieval_cases_2026-05-01.json"


def _load_cases(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(raw_cases, list):
        raise ValueError(f"case file must contain a list or cases array: {path}")
    cases: list[dict[str, object]] = []
    for index, item in enumerate(raw_cases, start=1):
        if not isinstance(item, dict):
            continue
        case = dict(item)
        case.setdefault("case_id", _case_id(index, case))
        case.setdefault("assert_mode", "context_contains")
        case.setdefault("source", "user_query_retrieval")
        cases.append(case)
    return cases


def _case_id(index: int, case: dict[str, object]) -> str:
    name = str(case.get("name") or "").strip()
    if name:
        return f"UQRET-{name}"
    return f"UQRET-{index:04d}"


def _evaluate_case(workspace_root: Path, case: dict[str, object], *, index: int, limit: int) -> dict[str, object]:
    case_id = str(case.get("case_id") or _case_id(index, case))
    query = str(case.get("query") or "").strip()
    preferred_doc_id = str(case.get("target_doc_id") or case.get("expected_doc_id") or "").strip() or None
    try:
        context = build_query_context(workspace_root, query, limit=limit, preferred_doc_id=preferred_doc_id)
    except Exception as exc:
        return {
            "case_id": case_id,
            "passed": False,
            "failure_reason": f"evaluation_exception:{type(exc).__name__}",
            "retrieved_items": [],
            "answer": "",
            "metrics": {"exception": str(exc)[:500]},
        }

    retrieved_items = _retrieved_items_from_context(context)
    trace_metrics = _trace_metrics_from_context(context)
    if context.get("clarification_required"):
        retrieval_quality = _clarification_retrieval_quality()
    else:
        retrieval_quality = evaluate_retrieval_quality(
            case=case,
            retrieved_items=retrieved_items,
            trace_metrics=trace_metrics,
        )
    contract = _case_contract_result(case, context, trace_metrics, retrieved_items)
    passed = bool(retrieval_quality.get("failure_attribution") == "ok" and contract["passed"])
    failure_reason = None if passed else _failure_reason(retrieval_quality, contract)
    return {
        "case_id": case_id,
        "passed": passed,
        "failure_reason": failure_reason,
        "retrieved_items": retrieved_items,
        "answer": "",
        "metrics": {
            **trace_metrics,
            "retrieval_quality": retrieval_quality,
            "contract": contract,
        },
    }


def _case_contract_result(
    case: dict[str, object],
    context: dict[str, object],
    trace_metrics: dict[str, object],
    retrieved_items: list[dict[str, object]],
) -> dict[str, object]:
    failures: list[str] = []
    expected_query_type = str(case.get("expected_query_type") or "").strip()
    if expected_query_type and trace_metrics.get("query_type") != expected_query_type:
        failures.append("query_type_mismatch")

    clarification_required = bool(context.get("clarification_required"))
    expected_clarification_required = _bool_or_none(case.get("expected_clarification_required"))
    if expected_clarification_required is not None and clarification_required != expected_clarification_required:
        failures.append("clarification_requirement_mismatch")

    expected_clarification_options = _string_list(case.get("expected_clarification_options"))
    if expected_clarification_options and not _clarification_options_cover(context, expected_clarification_options):
        failures.append("clarification_options_missing")

    min_graph = _int_or_none(case.get("expected_min_graph_candidates"))
    if not clarification_required and min_graph is not None and int(trace_metrics.get("graph_candidate_count") or 0) < min_graph:
        failures.append("graph_missing")

    expected_top_entity = str(case.get("expected_top_entity_contains") or "").strip()
    top_entity = (trace_metrics.get("topic_candidate_names") or [""])[0] if trace_metrics.get("topic_candidate_names") else ""
    if expected_top_entity and expected_top_entity not in str(top_entity):
        failures.append("topic_resolution_wrong")

    expected_doc_id = str(case.get("expected_doc_id") or case.get("target_doc_id") or "").strip()
    if expected_doc_id:
        top_doc_ids = [str(item.get("doc_id") or "") for item in retrieved_items[:5]]
        if expected_doc_id not in top_doc_ids:
            failures.append("expected_doc_missing")

    forbidden_ids = _string_list(case.get("forbidden_result_ids"))
    top_ids = [str(item.get("result_id") or "") for item in retrieved_items[:10]]
    if any(item in top_ids for item in forbidden_ids):
        failures.append("forbidden_result_hit")

    return {
        "passed": not failures,
        "failures": failures,
        "expected_query_type": expected_query_type,
        "actual_query_type": trace_metrics.get("query_type"),
        "expected_clarification_required": expected_clarification_required,
        "actual_clarification_required": clarification_required,
        "expected_clarification_options": expected_clarification_options,
        "expected_min_graph_candidates": min_graph,
        "actual_graph_candidate_count": trace_metrics.get("graph_candidate_count"),
        "expected_top_entity_contains": expected_top_entity,
        "actual_top_entity": top_entity,
        "expected_doc_id": expected_doc_id,
        "top_doc_ids": [str(item.get("doc_id") or "") for item in retrieved_items[:5]],
        "forbidden_result_ids": forbidden_ids,
        "top_result_ids": top_ids[:5],
    }


def _failure_reason(retrieval_quality: dict[str, object], contract: dict[str, object]) -> str:
    failures = [str(item) for item in contract.get("failures") or []]
    if failures:
        priority = [
            "query_type_mismatch",
            "clarification_requirement_mismatch",
            "clarification_options_missing",
            "topic_resolution_wrong",
            "graph_missing",
            "expected_doc_missing",
            "forbidden_result_hit",
        ]
        for item in priority:
            if item in failures:
                return item
        return failures[0]
    return str(retrieval_quality.get("failure_attribution") or "retrieval_quality_failed")


def _clarification_retrieval_quality() -> dict[str, object]:
    return {
        "must_hit_total": 0,
        "must_hit_found": 0,
        "must_hit_missing": [],
        "must_hit_best_rank": None,
        "mrr": None,
        "negative_hit_count": 0,
        "negative_hits": [],
        "negative_hit_rate": 0.0,
        "top_k": 0,
        "hit_count": 0,
        "failure_attribution": "ok",
        "recall_at_5": None,
        "recall_at_10": None,
    }


def _clarification_options_cover(context: dict[str, object], expected_options: list[str]) -> bool:
    clarification = context.get("clarification") if isinstance(context.get("clarification"), dict) else {}
    options = clarification.get("options") if isinstance(clarification.get("options"), list) else []
    option_blob = json.dumps(options, ensure_ascii=False).lower()
    return all(str(option).strip().lower() in option_blob for option in expected_options if str(option).strip())


def _retrieved_items_from_context(context: dict[str, object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
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
                "snippet": str(hit.get("snippet") or "")[:800],
                "graph_source": bool(hit.get("graph_source")),
                "channel": hit.get("channel"),
                "channels": hit.get("channels") or [],
            }
        )
    return items


def _trace_metrics_from_context(context: dict[str, object]) -> dict[str, object]:
    retrieval_plan = context.get("retrieval_plan") if isinstance(context.get("retrieval_plan"), dict) else {}
    topic_resolution = context.get("topic_resolution") if isinstance(context.get("topic_resolution"), dict) else {}
    candidates = topic_resolution.get("candidate_entities") if isinstance(topic_resolution.get("candidate_entities"), list) else []
    hits = context.get("hits") if isinstance(context.get("hits"), list) else []
    return {
        "query_type": (context.get("rewrite") or {}).get("query_type") if isinstance(context.get("rewrite"), dict) else "",
        "retrieval_channels": retrieval_plan.get("channels") if isinstance(retrieval_plan.get("channels"), list) else [],
        "graph_candidate_count": int(retrieval_plan.get("graph_candidate_count") or 0),
        "routing_summary_hit_count": int(retrieval_plan.get("routing_summary_hit_count") or 0),
        "topic_resolution_confidence": float(topic_resolution.get("confidence") or 0.0),
        "topic_candidate_names": [
            str(item.get("canonical_name") or "")
            for item in candidates[:5]
            if isinstance(item, dict)
        ],
        "top_hit_ids": [
            str(item.get("result_id") or "")
            for item in hits[:5]
            if isinstance(item, dict)
        ],
        "top_hit_doc_ids": [
            str(item.get("doc_id") or "")
            for item in hits[:5]
            if isinstance(item, dict)
        ],
        "retrieval_run_id": context.get("retrieval_run_id"),
    }


def _summary(
    cases: list[dict[str, object]],
    case_results: list[dict[str, object]],
    case_file: Path,
) -> dict[str, object]:
    passed = sum(1 for item in case_results if item.get("passed"))
    failed = len(case_results) - passed
    failure_counts: dict[str, int] = {}
    query_type_counts: dict[str, int] = {}
    graph_engaged = 0
    for item in case_results:
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        query_type = str(metrics.get("query_type") or "unknown")
        query_type_counts[query_type] = query_type_counts.get(query_type, 0) + 1
        if int(metrics.get("graph_candidate_count") or 0) > 0:
            graph_engaged += 1
        if not item.get("passed"):
            reason = str(item.get("failure_reason") or "unknown")
            failure_counts[reason] = failure_counts.get(reason, 0) + 1
    return {
        "suite": "user_query_retrieval",
        "case_file": str(case_file),
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / max(1, len(cases)), 6),
        "graph_engagement_rate": round(graph_engaged / max(1, len(cases)), 6),
        "failure_counts": dict(sorted(failure_counts.items())),
        "query_type_counts": dict(sorted(query_type_counts.items())),
    }


def _render_report(payload: dict[str, object]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    lines = [
        "# User Query Retrieval Eval",
        "",
        f"- Eval run: {payload.get('eval_run_id')}",
        f"- Case file: {payload.get('case_file')}",
        f"- Total: {summary.get('total', 0)}",
        f"- Passed: {summary.get('passed', 0)}",
        f"- Failed: {summary.get('failed', 0)}",
        f"- Pass rate: {summary.get('pass_rate', 0)}",
        f"- Graph engagement rate: {summary.get('graph_engagement_rate', 0)}",
        "",
        "## Failure Counts",
    ]
    failure_counts = summary.get("failure_counts") if isinstance(summary.get("failure_counts"), dict) else {}
    if failure_counts:
        lines.extend(f"- {key}: {value}" for key, value in failure_counts.items())
    else:
        lines.append("- none")
    lines.extend(["", "## Failed Cases"])
    failed = [item for item in results if isinstance(item, dict) and not item.get("passed")]
    if not failed:
        lines.append("- none")
    for item in failed:
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        contract = metrics.get("contract") if isinstance(metrics.get("contract"), dict) else {}
        lines.extend(
            [
                f"- {item.get('case_id')}: {item.get('failure_reason')}",
                f"  - query_type: {contract.get('actual_query_type')}",
                f"  - top_entity: {contract.get('actual_top_entity')}",
                f"  - graph_candidate_count: {contract.get('actual_graph_candidate_count')}",
                f"  - top_result_ids: {contract.get('top_result_ids')}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: object) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None
