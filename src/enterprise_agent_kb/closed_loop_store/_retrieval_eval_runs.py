"""Retrieval runs, eval runs, and run-comparison analytics.

Extracted from `closed_loop_store._impl` to isolate run lifecycle (record,
list, detail, scope backfill) and the run-to-run comparison logic from
the failure-diagnostic and repair-task concerns. Cross-module callers
inside this package must import via `from ._retrieval_eval_runs import ...`.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ._golden_cases import _ensure_golden_cases_columns, _golden_case_id, utc_now
from ._helpers import (
    _as_int,
    _clip,
    _json_list,
    _json_object,
    _mean_metric,
    _normalize_text,
    _optional_text,
    _pytest_output_counts,
    _ratio,
    _safe_float,
    _safe_json,
    _stable_id,
    _string_ids,
    _text_values,
    re_sub_whitespace,
)
from ._runtime import _runtime_code_version, _short_hash

def record_retrieval_run(
    connection,
    *,
    query: str,
    query_type: str | None,
    doc_scope: str | None,
    retrieved_evidence_ids: list[object],
    reranked_ids: list[object],
    scores: dict[str, object],
    metadata: dict[str, object] | None = None,
) -> str | None:
    now = utc_now()
    run_id = _stable_id("RET", query, query_type, doc_scope, reranked_ids[:20], now)
    try:
        _ensure_retrieval_runs_columns(connection)
        connection.execute(
            """
            INSERT INTO retrieval_runs (
                run_id, query, query_type, doc_scope,
                retrieved_evidence_ids_json, reranked_ids_json, scores_json,
                code_version, metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                _normalize_text(query),
                _optional_text(query_type),
                _optional_text(doc_scope),
                json.dumps(retrieved_evidence_ids, ensure_ascii=False),
                json.dumps(reranked_ids, ensure_ascii=False),
                json.dumps(scores, ensure_ascii=False, sort_keys=True, default=str),
                _runtime_code_version(),
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True, default=str),
                now,
            ),
        )
    except sqlite3.DatabaseError:
        return None
    return run_id


def _ensure_retrieval_runs_columns(connection) -> None:
    rows = connection.execute("PRAGMA table_info(retrieval_runs)").fetchall()
    columns = {str(row["name"]) for row in rows}
    if "code_version" not in columns:
        connection.execute("ALTER TABLE retrieval_runs ADD COLUMN code_version TEXT")


def record_eval_run(
    connection,
    *,
    suite_id: str,
    cases: list[dict[str, object]],
    summary: dict[str, object],
    command: str,
    success: bool,
    output: str,
    code_version: str | None = None,
    case_results: list[dict[str, object]] | None = None,
) -> str:
    now = utc_now()
    stored_code_version = code_version if code_version is not None else _runtime_code_version()
    eval_run_id = _stable_id("EVAL", suite_id, now, command)
    config_hash = _short_hash({"suite_id": suite_id, "case_count": len(cases), "command": command})
    summary_with_quality = dict(summary)
    if case_results:
        summary_with_quality["retrieval_quality"] = _retrieval_quality_summary(case_results)
        summary_with_quality["answer_quality"] = _answer_quality_summary(case_results)
        summary_with_quality["evidence_shape_quality"] = _evidence_shape_quality_summary(case_results)
        summary_with_quality["shape_contract_quality"] = _shape_contract_quality_summary(case_results)
    else:
        summary_with_quality.setdefault("retrieval_quality", _retrieval_quality_summary([]))
        summary_with_quality.setdefault("answer_quality", _answer_quality_summary([]))
        summary_with_quality.setdefault("evidence_shape_quality", _evidence_shape_quality_summary([]))
        summary_with_quality.setdefault("shape_contract_quality", _shape_contract_quality_summary([]))
    summary_with_quality.setdefault("pytest_counts", _pytest_output_counts(output))
    summary_with_quality.setdefault("eval_scope", _eval_scope_summary(cases, case_results or [], output))
    connection.execute(
        """
        INSERT INTO eval_runs (
            eval_run_id, suite_id, started_at, finished_at, config_hash,
            code_version, result_summary_json, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            eval_run_id,
            suite_id,
            now,
            now,
            config_hash,
            stored_code_version,
            json.dumps(summary_with_quality, ensure_ascii=False),
            "passed" if success else "failed",
        ),
    )
    results_by_case_id = {
        str(item.get("case_id")): item
        for item in (case_results or [])
        if str(item.get("case_id") or "")
    }
    for index, case in enumerate(cases, start=1):
        case_scope = _case_scope_from_suite_id(suite_id)
        case_id = str(case.get("case_id") or _golden_case_id(case_scope, index, case))
        structured = results_by_case_id.get(case_id, {})
        result_passed = bool(structured.get("passed")) if structured else bool(success)
        failure_reason = structured.get("failure_reason") if structured else (None if success else "pytest_failed")
        retrieved_items = structured.get("retrieved_items") if structured else []
        answer_text = structured.get("answer") if structured else _clip(output, 4000)
        metrics = structured.get("metrics") if structured else {"coarse_result_from_pytest": True}
        connection.execute(
            """
            INSERT INTO eval_results (
                eval_run_id, case_id, passed, failure_reason,
                retrieved_items_json, answer_text, metrics_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eval_run_id,
                case_id,
                1 if result_passed else 0,
                str(failure_reason) if failure_reason else None,
                json.dumps(retrieved_items if isinstance(retrieved_items, list) else [], ensure_ascii=False),
                _clip(str(answer_text or ""), 4000),
                json.dumps(metrics if isinstance(metrics, dict) else {}, ensure_ascii=False),
                now,
            ),
        )
    return eval_run_id


def load_golden_cases_from_file(golden_path: Path) -> list[dict[str, object]]:
    if not golden_path.exists():
        return []
    payload = json.loads(golden_path.read_text(encoding="utf-8"))
    return [case for case in payload.get("cases", []) if isinstance(case, dict)]


def list_eval_runs(connection, *, suite_id: str | None = None, limit: int = 30) -> list[dict[str, object]]:
    params: list[object] = []
    where = ""
    if suite_id:
        where = "WHERE suite_id = ?"
        params.append(suite_id)
    params.append(max(1, min(int(limit), 200)))
    rows = connection.execute(
        f"""
        SELECT eval_run_id, suite_id, started_at, finished_at, config_hash,
               code_version, result_summary_json, status
        FROM eval_runs
        {where}
        ORDER BY started_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [_eval_run_row(row) for row in rows]


def backfill_eval_run_scope_metadata(connection, *, limit: int = 200) -> dict[str, object]:
    rows = connection.execute(
        """
        SELECT eval_run_id, result_summary_json
        FROM eval_runs
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (max(1, min(int(limit), 1000)),),
    ).fetchall()
    updated_eval_run_ids: list[str] = []
    for row in rows:
        eval_run_id = str(row["eval_run_id"] or "")
        summary = _safe_json(row["result_summary_json"], {})
        if not isinstance(summary, dict):
            summary = {}
        needs_update = False
        if not isinstance(summary.get("eval_scope"), dict):
            summary["eval_scope"] = _legacy_eval_scope_summary(connection, eval_run_id, summary)
            needs_update = True
        if not isinstance(summary.get("pytest_counts"), dict):
            summary["pytest_counts"] = _legacy_pytest_counts_summary(summary)
            needs_update = True
        if needs_update:
            connection.execute(
                """
                UPDATE eval_runs
                SET result_summary_json = ?
                WHERE eval_run_id = ?
                """,
                (json.dumps(summary, ensure_ascii=False), eval_run_id),
            )
            updated_eval_run_ids.append(eval_run_id)
    return {
        "checked_count": len(rows),
        "updated_count": len(updated_eval_run_ids),
        "updated_eval_run_ids": updated_eval_run_ids,
    }


def list_retrieval_runs(
    connection,
    *,
    query: str | None = None,
    query_type: str | None = None,
    limit: int = 30,
) -> list[dict[str, object]]:
    _ensure_retrieval_runs_columns(connection)
    clauses: list[str] = []
    params: list[object] = []
    if query:
        clauses.append("query LIKE ?")
        params.append(f"%{query}%")
    if query_type:
        clauses.append("query_type = ?")
        params.append(query_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(int(limit), 200)))
    rows = connection.execute(
        f"""
        SELECT run_id, query, query_type, doc_scope,
               retrieved_evidence_ids_json, reranked_ids_json, scores_json,
               code_version, metadata_json, created_at
        FROM retrieval_runs
        {where}
        ORDER BY created_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [_retrieval_run_row(row, include_detail=False) for row in rows]


def get_retrieval_run_detail(connection, run_id: str) -> dict[str, object] | None:
    _ensure_retrieval_runs_columns(connection)
    row = connection.execute(
        """
        SELECT run_id, query, query_type, doc_scope,
               retrieved_evidence_ids_json, reranked_ids_json, scores_json,
               code_version, metadata_json, created_at
        FROM retrieval_runs
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    return _retrieval_run_row(row, include_detail=True)


def get_eval_run_detail(connection, eval_run_id: str) -> dict[str, object] | None:
    _ensure_golden_cases_columns(connection)
    row = connection.execute(
        """
        SELECT eval_run_id, suite_id, started_at, finished_at, config_hash,
               code_version, result_summary_json, status
        FROM eval_runs
        WHERE eval_run_id = ?
        """,
        (eval_run_id,),
    ).fetchone()
    if row is None:
        return None
    result_rows = connection.execute(
        """
        SELECT r.eval_run_id, r.case_id, r.passed, r.failure_reason,
               r.retrieved_items_json, r.answer_text, r.metrics_json, r.created_at,
               c.doc_id, c.assert_mode, c.query, c.must_hit_json,
               c.negative_expected_json, c.expected_pages_json,
               c.expected_sections_json, c.expected_evidence_shape,
               c.status AS case_status, c.source
        FROM eval_results r
        LEFT JOIN golden_cases c ON c.case_id = r.case_id
        WHERE r.eval_run_id = ?
        ORDER BY r.passed ASC, r.case_id ASC
        """,
        (eval_run_id,),
    ).fetchall()
    return {
        **_eval_run_row(row),
        "results": [_eval_result_row(result) for result in result_rows],
    }

def compare_eval_runs(
    connection,
    current_eval_run_id: str,
    baseline_eval_run_id: str | None = None,
) -> dict[str, object] | None:
    current = get_eval_run_detail(connection, current_eval_run_id)
    if current is None:
        return None
    baseline_id = baseline_eval_run_id or _previous_eval_run_id(
        connection,
        str(current.get("suite_id") or ""),
        str(current.get("started_at") or ""),
        current_eval_run_id,
    )
    if not baseline_id:
        return {
            "current_eval_run_id": current_eval_run_id,
            "baseline_eval_run_id": None,
            "has_baseline": False,
            "new_failures": [],
            "fixed_failures": [],
            "stable_passes": [],
            "stable_failures": [],
            "added_cases": [],
            "removed_cases": [],
            "added_case_count": 0,
            "removed_case_count": 0,
            "retrieval_quality_delta": _retrieval_quality_delta(current.get("result_summary"), None),
            "answer_quality_delta": _answer_quality_delta(current.get("result_summary"), None),
            "answer_regression_count": 0,
            "retrieval_regression_count": 0,
            "stable_pass_rate": None,
        }
    baseline = get_eval_run_detail(connection, baseline_id)
    if baseline is None:
        return None

    current_results = {
        str(item.get("case_id")): item
        for item in current.get("results", [])
        if isinstance(item, dict) and str(item.get("case_id") or "")
    }
    baseline_results = {
        str(item.get("case_id")): item
        for item in baseline.get("results", [])
        if isinstance(item, dict) and str(item.get("case_id") or "")
    }
    compared_case_ids = sorted(set(current_results) | set(baseline_results))
    added_cases: list[dict[str, object]] = []
    removed_cases: list[dict[str, object]] = []
    new_failures: list[dict[str, object]] = []
    fixed_failures: list[dict[str, object]] = []
    stable_passes: list[str] = []
    stable_failures: list[str] = []
    answer_regression_count = 0
    retrieval_regression_count = 0
    for case_id in compared_case_ids:
        current_result = current_results.get(case_id)
        baseline_result = baseline_results.get(case_id)
        if current_result is None:
            removed_cases.append(_case_churn_item(case_id, baseline_result, "removed"))
            continue
        if baseline_result is None:
            added_cases.append(_case_churn_item(case_id, current_result, "added"))
            continue
        current_passed = bool(current_result.get("passed"))
        baseline_passed = bool(baseline_result.get("passed"))
        if baseline_passed and not current_passed:
            item = _comparison_case_item(case_id, current_result, baseline_result)
            new_failures.append(item)
            if _is_retrieval_failure(item):
                retrieval_regression_count += 1
            else:
                answer_regression_count += 1
        elif not baseline_passed and current_passed:
            fixed_failures.append(_comparison_case_item(case_id, current_result, baseline_result))
        elif current_passed and baseline_passed:
            stable_passes.append(case_id)
        else:
            stable_failures.append(case_id)

    comparable_count = len([case_id for case_id in compared_case_ids if case_id in current_results and case_id in baseline_results])
    return {
        "current_eval_run_id": current_eval_run_id,
        "baseline_eval_run_id": baseline_id,
        "has_baseline": True,
        "new_failures": new_failures,
        "fixed_failures": fixed_failures,
        "stable_passes": stable_passes,
        "stable_failures": stable_failures,
        "added_cases": added_cases,
        "removed_cases": removed_cases,
        "new_failure_count": len(new_failures),
        "fixed_failure_count": len(fixed_failures),
        "stable_pass_count": len(stable_passes),
        "stable_failure_count": len(stable_failures),
        "added_case_count": len(added_cases),
        "removed_case_count": len(removed_cases),
        "stable_pass_rate": round(len(stable_passes) / comparable_count, 6) if comparable_count else None,
        "retrieval_quality_delta": _retrieval_quality_delta(current.get("result_summary"), baseline.get("result_summary")),
        "answer_quality_delta": _answer_quality_delta(current.get("result_summary"), baseline.get("result_summary")),
        "answer_regression_count": answer_regression_count,
        "retrieval_regression_count": retrieval_regression_count,
    }



def _previous_eval_run_id(connection, suite_id: str, started_at: str, current_eval_run_id: str) -> str | None:
    row = connection.execute(
        """
        SELECT eval_run_id
        FROM eval_runs
        WHERE suite_id = ?
          AND eval_run_id != ?
          AND started_at <= ?
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (suite_id, current_eval_run_id, started_at),
    ).fetchone()
    if row is not None:
        return str(row["eval_run_id"])
    row = connection.execute(
        """
        SELECT eval_run_id
        FROM eval_runs
        WHERE suite_id = ?
          AND eval_run_id != ?
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (suite_id, current_eval_run_id),
    ).fetchone()
    return str(row["eval_run_id"]) if row is not None else None


def _comparison_case_item(case_id: str, current: dict[str, object], baseline: dict[str, object]) -> dict[str, object]:
    current_metrics = current.get("metrics") if isinstance(current.get("metrics"), dict) else {}
    baseline_metrics = baseline.get("metrics") if isinstance(baseline.get("metrics"), dict) else {}
    current_quality = current_metrics.get("retrieval_quality") if isinstance(current_metrics.get("retrieval_quality"), dict) else {}
    baseline_quality = baseline_metrics.get("retrieval_quality") if isinstance(baseline_metrics.get("retrieval_quality"), dict) else {}
    current_answer_quality = current_metrics.get("answer_quality") if isinstance(current_metrics.get("answer_quality"), dict) else {}
    baseline_answer_quality = baseline_metrics.get("answer_quality") if isinstance(baseline_metrics.get("answer_quality"), dict) else {}
    case = current.get("case") if isinstance(current.get("case"), dict) else {}
    return {
        "case_id": case_id,
        "query": case.get("query"),
        "current": {
            "passed": bool(current.get("passed")),
            "failure_reason": current.get("failure_reason"),
            "answer_mode": current_metrics.get("answer_mode"),
            "retrieval_failure_attribution": current_quality.get("failure_attribution"),
            "answer_failure_attribution": current_answer_quality.get("failure_attribution"),
            "answer_pass": current_answer_quality.get("answer_pass"),
            "recall_at_5": current_quality.get("recall_at_5"),
            "mrr": current_quality.get("mrr"),
        },
        "baseline": {
            "passed": bool(baseline.get("passed")),
            "failure_reason": baseline.get("failure_reason"),
            "answer_mode": baseline_metrics.get("answer_mode"),
            "retrieval_failure_attribution": baseline_quality.get("failure_attribution"),
            "answer_failure_attribution": baseline_answer_quality.get("failure_attribution"),
            "answer_pass": baseline_answer_quality.get("answer_pass"),
            "recall_at_5": baseline_quality.get("recall_at_5"),
            "mrr": baseline_quality.get("mrr"),
        },
    }


def _case_churn_item(case_id: str, result: dict[str, object] | None, status: str) -> dict[str, object]:
    item = result if isinstance(result, dict) else {}
    case = item.get("case") if isinstance(item.get("case"), dict) else {}
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    return {
        "case_id": case_id,
        "status": status,
        "query": case.get("query"),
        "passed": bool(item.get("passed")),
        "failure_reason": item.get("failure_reason"),
        "assert_mode": case.get("assert_mode"),
        "expected_evidence_shape": case.get("expected_evidence_shape"),
        "answer_mode": metrics.get("answer_mode"),
        "query_type": metrics.get("query_type"),
    }


def _is_retrieval_failure(item: dict[str, object]) -> bool:
    current = item.get("current") if isinstance(item.get("current"), dict) else {}
    reason = str(current.get("failure_reason") or "").lower()
    attribution = str(current.get("retrieval_failure_attribution") or "")
    if "retrieval" in reason or "miss" in reason:
        return True
    return attribution in {"retrieval_miss", "graph_not_engaged", "topic_resolution_empty", "rank_too_low", "negative_hit"}


def _retrieval_quality_delta(current_summary: object, baseline_summary: object) -> dict[str, object]:
    current = current_summary if isinstance(current_summary, dict) else {}
    baseline = baseline_summary if isinstance(baseline_summary, dict) else {}
    current_quality = current.get("retrieval_quality") if isinstance(current.get("retrieval_quality"), dict) else {}
    baseline_quality = baseline.get("retrieval_quality") if isinstance(baseline.get("retrieval_quality"), dict) else {}
    return {
        "current": current_quality,
        "baseline": baseline_quality or None,
        "recall_at_5_delta": _metric_delta(current_quality, baseline_quality, "recall_at_5"),
        "recall_at_10_delta": _metric_delta(current_quality, baseline_quality, "recall_at_10"),
        "mrr_delta": _metric_delta(current_quality, baseline_quality, "mrr"),
        "negative_hit_rate_delta": _metric_delta(current_quality, baseline_quality, "negative_hit_rate"),
    }


def _answer_quality_delta(current_summary: object, baseline_summary: object) -> dict[str, object]:
    current = current_summary if isinstance(current_summary, dict) else {}
    baseline = baseline_summary if isinstance(baseline_summary, dict) else {}
    current_quality = current.get("answer_quality") if isinstance(current.get("answer_quality"), dict) else {}
    baseline_quality = baseline.get("answer_quality") if isinstance(baseline.get("answer_quality"), dict) else {}
    return {
        "current": current_quality,
        "baseline": baseline_quality or None,
        "answer_pass_rate_delta": _metric_delta(current_quality, baseline_quality, "answer_pass_rate"),
        "answer_mode_accuracy_delta": _metric_delta(current_quality, baseline_quality, "answer_mode_accuracy"),
        "forbidden_hit_rate_delta": _metric_delta(current_quality, baseline_quality, "forbidden_hit_rate"),
        "render_artifact_rate_delta": _metric_delta(current_quality, baseline_quality, "render_artifact_rate"),
        "evidence_sufficient_rate_delta": _metric_delta(current_quality, baseline_quality, "evidence_sufficient_rate"),
    }


def _metric_delta(current: dict[str, object], baseline: dict[str, object], key: str) -> float | None:
    if key not in current or key not in baseline:
        return None
    try:
        return round(float(current.get(key)) - float(baseline.get(key)), 6)
    except (TypeError, ValueError):
        return None


def _case_scope_from_suite_id(suite_id: str) -> str:
    if ":" in suite_id:
        prefix, suffix = suite_id.split(":", 1)
        if prefix in {"golden", "coverage", "regression"} and suffix.strip():
            return suffix.strip()
    return suite_id


def _eval_run_row(row) -> dict[str, object]:
    return {
        "eval_run_id": row["eval_run_id"],
        "suite_id": row["suite_id"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "config_hash": row["config_hash"],
        "code_version": row["code_version"],
        "result_summary": _safe_json(row["result_summary_json"], {}),
        "status": row["status"],
    }


def _retrieval_run_row(row, *, include_detail: bool) -> dict[str, object]:
    metadata = _safe_json(row["metadata_json"], {})
    scores = _safe_json(row["scores_json"], {})
    reranked_ids = _safe_json(row["reranked_ids_json"], [])
    retrieved_evidence_ids = _safe_json(row["retrieved_evidence_ids_json"], [])
    diagnostics = _retrieval_run_diagnostics(
        reranked_ids=reranked_ids if isinstance(reranked_ids, list) else [],
        retrieved_evidence_ids=retrieved_evidence_ids if isinstance(retrieved_evidence_ids, list) else [],
        metadata=metadata if isinstance(metadata, dict) else {},
    )
    direct_evidence_hit_count = len(retrieved_evidence_ids) if isinstance(retrieved_evidence_ids, list) else 0
    linked_evidence_hit_count = int(diagnostics.get("linked_evidence_count") or 0)
    summary = {
        "run_id": row["run_id"],
        "query": row["query"],
        "query_type": row["query_type"],
        "doc_scope": row["doc_scope"],
        "created_at": row["created_at"],
        "code_version": row["code_version"] if "code_version" in row.keys() else None,
        "hit_count": len(reranked_ids) if isinstance(reranked_ids, list) else 0,
        "evidence_hit_count": direct_evidence_hit_count + linked_evidence_hit_count,
        "direct_evidence_hit_count": direct_evidence_hit_count,
        "linked_evidence_hit_count": linked_evidence_hit_count,
        "diagnostics": diagnostics,
    }
    if not include_detail:
        if isinstance(metadata, dict):
            summary["channels"] = (metadata.get("retrieval_plan") or {}).get("channels", [])
            summary["graph_hit_count"] = metadata.get("graph_hit_count", 0)
        return summary
    return {
        **summary,
        "retrieved_evidence_ids": retrieved_evidence_ids,
        "reranked_ids": reranked_ids,
        "scores": scores,
        "metadata": metadata,
    }


def _retrieval_run_diagnostics(
    *,
    reranked_ids: list[object],
    retrieved_evidence_ids: list[object],
    metadata: dict[str, object],
) -> dict[str, object]:
    retrieval_plan = metadata.get("retrieval_plan") if isinstance(metadata.get("retrieval_plan"), dict) else {}
    topic_resolution = metadata.get("topic_resolution") if isinstance(metadata.get("topic_resolution"), dict) else {}
    rerank_explanations = metadata.get("rerank_explanations") if isinstance(metadata.get("rerank_explanations"), list) else []
    channels = [str(item) for item in retrieval_plan.get("channels") or []]
    type_counts = _result_type_counts(reranked_ids)
    graph_candidate_count = _as_int(metadata.get("graph_hit_count"))
    if graph_candidate_count is None:
        graph_candidate_count = _as_int(retrieval_plan.get("graph_candidate_count")) or 0
    routing_summary_hit_count = _as_int(metadata.get("direct_routing_hit_count"))
    if routing_summary_hit_count is None:
        routing_summary_hit_count = _as_int(retrieval_plan.get("routing_summary_hit_count")) or 0
    linked_evidence_ids = metadata.get("linked_evidence_ids") if isinstance(metadata.get("linked_evidence_ids"), list) else []
    linked_evidence_count = _as_int(metadata.get("linked_evidence_count"))
    if linked_evidence_count is None:
        linked_evidence_count = len(linked_evidence_ids)
    hit_count = _as_int(metadata.get("hit_count"))
    if hit_count is None:
        hit_count = len(reranked_ids)
    candidate_count = _as_int(metadata.get("candidate_count_before_limit")) or hit_count
    topic_confidence = _safe_float(topic_resolution.get("confidence"))
    candidate_entity_ids = topic_resolution.get("candidate_entity_ids")
    candidate_entities = topic_resolution.get("candidate_entities")
    topic_entity_count = len(candidate_entity_ids) if isinstance(candidate_entity_ids, list) else 0
    if topic_entity_count == 0 and isinstance(candidate_entities, list):
        topic_entity_count = len(candidate_entities)
    top_graph_source_count = 0
    for item in rerank_explanations:
        if isinstance(item, dict) and item.get("graph_source"):
            top_graph_source_count += 1

    graph_status = "not_requested"
    if "graph" in channels:
        if topic_entity_count <= 0:
            graph_status = "no_topic_entities"
        elif graph_candidate_count <= 0:
            graph_status = "no_graph_candidates"
        elif top_graph_source_count <= 0 and rerank_explanations:
            graph_status = "graph_candidates_lost_after_rerank"
        else:
            graph_status = "engaged"

    evidence_status = "direct" if retrieved_evidence_ids else "empty"
    if not retrieved_evidence_ids and linked_evidence_count > 0:
        evidence_status = "linked"
    elif not retrieved_evidence_ids and type_counts.get("fact", 0) > 0:
        evidence_status = "facts_without_evidence_links"

    channel_hit_counts = {
        "graph": graph_candidate_count,
        "routing_summary": routing_summary_hit_count,
        "facts": type_counts.get("fact", 0),
        "evidence": len(retrieved_evidence_ids),
        "linked_evidence": linked_evidence_count,
        "wiki": type_counts.get("wiki", 0),
        "document": type_counts.get("document", 0),
    }
    risk_flags: list[str] = []
    if hit_count <= 0:
        risk_flags.append("no_retrieval_hits")
    if "graph" in channels and graph_candidate_count <= 0:
        risk_flags.append("graph_channel_empty")
    if "graph" in channels and graph_candidate_count > 0 and graph_status == "graph_candidates_lost_after_rerank":
        risk_flags.append("graph_candidates_lost_after_rerank")
    if "evidence" in channels and not retrieved_evidence_ids and linked_evidence_count <= 0:
        risk_flags.append("evidence_channel_empty")
    if type_counts.get("fact", 0) > 0 and not retrieved_evidence_ids and linked_evidence_count <= 0:
        risk_flags.append("facts_without_evidence_links")
    if type_counts.get("fact", 0) > 0 and not retrieved_evidence_ids and linked_evidence_count > 0:
        risk_flags.append("evidence_only_linked_to_facts")
    if topic_confidence <= 0 and "graph" in channels:
        risk_flags.append("topic_resolution_empty")
    elif 0 < topic_confidence < 0.5:
        risk_flags.append("topic_resolution_low_confidence")
    if candidate_count > hit_count and hit_count <= 0:
        risk_flags.append("candidates_dropped_before_limit")

    return {
        "channels": channels,
        "channel_hit_counts": channel_hit_counts,
        "top_result_type_counts": type_counts,
        "graph_status": graph_status,
        "evidence_status": evidence_status,
        "linked_evidence_count": linked_evidence_count,
        "topic_resolution_confidence": topic_confidence,
        "topic_entity_count": topic_entity_count,
        "candidate_count_before_limit": candidate_count,
        "risk_flags": sorted(set(risk_flags)),
    }


def _result_type_counts(reranked_ids: list[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in reranked_ids:
        prefix = str(item or "").split(":", 1)[0].strip() or "unknown"
        counts[prefix] = counts.get(prefix, 0) + 1
    return dict(sorted(counts.items()))


def _retrieval_quality_summary(case_results: list[dict[str, object]]) -> dict[str, object]:
    quality_items: list[dict[str, object]] = []
    for item in case_results:
        if not isinstance(item, dict):
            continue
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        quality = metrics.get("retrieval_quality") if isinstance(metrics.get("retrieval_quality"), dict) else None
        if quality:
            quality_items.append(quality)
    total = len(quality_items)
    if not total:
        return {
            "total": 0,
            "recall_at_5": None,
            "recall_at_10": None,
            "mrr": None,
            "negative_hit_rate": None,
            "failure_attribution_counts": {},
        }
    attribution_counts: dict[str, int] = {}
    for quality in quality_items:
        attribution = str(quality.get("failure_attribution") or "unknown")
        attribution_counts[attribution] = attribution_counts.get(attribution, 0) + 1
    return {
        "total": total,
        "recall_at_5": _mean_metric(quality_items, "recall_at_5"),
        "recall_at_10": _mean_metric(quality_items, "recall_at_10"),
        "mrr": _mean_metric(quality_items, "mrr"),
        "negative_hit_rate": _mean_metric(quality_items, "negative_hit_rate"),
        "ok_count": attribution_counts.get("ok", 0),
        "failure_attribution_counts": dict(sorted(attribution_counts.items())),
    }


def _answer_quality_summary(case_results: list[dict[str, object]]) -> dict[str, object]:
    quality_items: list[dict[str, object]] = []
    for item in case_results:
        if not isinstance(item, dict):
            continue
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        quality = metrics.get("answer_quality") if isinstance(metrics.get("answer_quality"), dict) else None
        if quality:
            quality_items.append(quality)
    total = len(quality_items)
    if not total:
        return {
            "total": 0,
            "answer_pass_rate": None,
            "answer_mode_accuracy": None,
            "forbidden_hit_rate": None,
            "render_artifact_rate": None,
            "evidence_sufficient_rate": None,
            "failure_attribution_counts": {},
        }
    attribution_counts: dict[str, int] = {}
    for quality in quality_items:
        attribution = str(quality.get("failure_attribution") or "unknown")
        attribution_counts[attribution] = attribution_counts.get(attribution, 0) + 1
    mode_items = [item for item in quality_items if item.get("answer_mode_match") is not None]
    evidence_items = [item for item in quality_items if item.get("evidence_sufficient") is not None]
    return {
        "total": total,
        "answer_pass_rate": _ratio(sum(1 for item in quality_items if item.get("answer_pass")), total),
        "answer_mode_accuracy": _ratio(sum(1 for item in mode_items if item.get("answer_mode_match")), len(mode_items)) if mode_items else None,
        "forbidden_hit_rate": _ratio(sum(1 for item in quality_items if int(item.get("forbidden_hit_count") or 0) > 0), total),
        "render_artifact_rate": _ratio(sum(1 for item in quality_items if int(item.get("render_artifact_hit_count") or 0) > 0), total),
        "evidence_sufficient_rate": _ratio(sum(1 for item in evidence_items if item.get("evidence_sufficient")), len(evidence_items)) if evidence_items else None,
        "ok_count": attribution_counts.get("ok", 0),
        "failure_attribution_counts": dict(sorted(attribution_counts.items())),
    }


def _evidence_shape_quality_summary(case_results: list[dict[str, object]]) -> dict[str, object]:
    expected_items: list[dict[str, object]] = []
    actual_counts: dict[str, int] = {}
    expected_counts: dict[str, int] = {}
    mismatch_examples: list[dict[str, object]] = []
    for item in case_results:
        if not isinstance(item, dict):
            continue
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        actual = str(metrics.get("evidence_shape") or "").strip()
        expected = str(metrics.get("expected_evidence_shape") or "").strip()
        match = _evidence_shape_match_value(metrics)
        if actual:
            actual_counts[actual] = actual_counts.get(actual, 0) + 1
        if expected:
            expected_counts[expected] = expected_counts.get(expected, 0) + 1
            expected_items.append({"case_id": item.get("case_id"), "expected": expected, "actual": actual, "match": match})
            if match is False and len(mismatch_examples) < 10:
                mismatch_examples.append({"case_id": item.get("case_id"), "expected": expected, "actual": actual or None})
    total = len(expected_items)
    return {
        "total_expected": total,
        "shape_match_rate": _ratio(sum(1 for item in expected_items if item.get("match") is True), total) if total else None,
        "mismatch_count": sum(1 for item in expected_items if item.get("match") is False),
        "actual_shape_counts": dict(sorted(actual_counts.items())),
        "expected_shape_counts": dict(sorted(expected_counts.items())),
        "mismatch_examples": mismatch_examples,
    }


def _evidence_shape_match_value(metrics: dict[str, object]) -> bool | None:
    direct = metrics.get("evidence_shape_match")
    if isinstance(direct, bool):
        return direct
    contract = metrics.get("contract") if isinstance(metrics.get("contract"), dict) else {}
    contract_value = contract.get("evidence_shape_match")
    if isinstance(contract_value, bool):
        return contract_value
    quality = metrics.get("answer_quality") if isinstance(metrics.get("answer_quality"), dict) else {}
    quality_value = quality.get("evidence_shape_match")
    if isinstance(quality_value, bool):
        return quality_value
    shape_contract = _shape_contract_match_value(metrics)
    return shape_contract


def _shape_contract_quality_summary(case_results: list[dict[str, object]]) -> dict[str, object]:
    total = 0
    matched_count = 0
    mismatch_count = 0
    missing_count = 0
    mismatch_by_query_type: dict[str, int] = {}
    missing_by_query_type: dict[str, int] = {}
    matched_by_query_type: dict[str, int] = {}
    failure_reason_counts: dict[str, int] = {}
    for item in case_results:
        if not isinstance(item, dict):
            continue
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        query_type = str(metrics.get("shape_contract_query_type") or metrics.get("query_type") or "unknown").strip() or "unknown"
        matched = _shape_contract_match_value(metrics)
        reason = _shape_contract_failure_reason(metrics)
        if reason:
            failure_reason_counts[reason] = failure_reason_counts.get(reason, 0) + 1
        if matched is None:
            if metrics.get("query_type") or metrics.get("evidence_shape"):
                missing_count += 1
                missing_by_query_type[query_type] = missing_by_query_type.get(query_type, 0) + 1
            continue
        total += 1
        if matched is True:
            matched_count += 1
            matched_by_query_type[query_type] = matched_by_query_type.get(query_type, 0) + 1
        else:
            mismatch_count += 1
            mismatch_by_query_type[query_type] = mismatch_by_query_type.get(query_type, 0) + 1
    return {
        "contract_total": total,
        "contract_matched_count": matched_count,
        "contract_mismatch_count": mismatch_count,
        "contract_missing_count": missing_count,
        "contract_match_rate": _ratio(matched_count, total) if total else None,
        "matched_by_query_type": dict(sorted(matched_by_query_type.items())),
        "mismatch_by_query_type": dict(sorted(mismatch_by_query_type.items())),
        "missing_by_query_type": dict(sorted(missing_by_query_type.items())),
        "failure_reason_counts": dict(sorted(failure_reason_counts.items())),
    }


def _shape_contract_match_value(metrics: dict[str, object]) -> bool | None:
    if "shape_contract_matched" in metrics:
        value = metrics.get("shape_contract_matched")
        if isinstance(value, bool):
            return value
    diagnostics = metrics.get("evidence_shape_diagnostics") if isinstance(metrics.get("evidence_shape_diagnostics"), dict) else {}
    contract = diagnostics.get("shape_contract") if isinstance(diagnostics.get("shape_contract"), dict) else {}
    value = contract.get("matched")
    return value if isinstance(value, bool) else None


def _shape_contract_failure_reason(metrics: dict[str, object]) -> str:
    direct = str(metrics.get("shape_contract_failure_reason") or "").strip()
    if direct:
        return direct
    diagnostics = metrics.get("evidence_shape_diagnostics") if isinstance(metrics.get("evidence_shape_diagnostics"), dict) else {}
    diagnosis = diagnostics.get("shape_contract_diagnosis") if isinstance(diagnostics.get("shape_contract_diagnosis"), dict) else {}
    return str(diagnosis.get("reason") or "").strip()

def _eval_result_row(row) -> dict[str, object]:
    return {
        "eval_run_id": row["eval_run_id"],
        "case_id": row["case_id"],
        "passed": bool(row["passed"]),
        "failure_reason": row["failure_reason"],
        "retrieved_items": _safe_json(row["retrieved_items_json"], []),
        "answer": row["answer_text"],
        "metrics": _safe_json(row["metrics_json"], {}),
        "created_at": row["created_at"],
        "case": {
            "doc_id": row["doc_id"],
            "assert_mode": row["assert_mode"],
            "query": row["query"],
            "must_hit": _safe_json(row["must_hit_json"], []),
            "negative_expected": _safe_json(row["negative_expected_json"], []),
            "expected_pages": _safe_json(row["expected_pages_json"], []),
            "expected_sections": _safe_json(row["expected_sections_json"], []),
            "expected_evidence_shape": row["expected_evidence_shape"],
            "status": row["case_status"],
            "source": row["source"],
        },
    }

def _eval_scope_summary(cases: list[dict[str, object]], case_results: list[dict[str, object]], output: str) -> dict[str, object]:
    declared_case_count = len([case for case in cases if isinstance(case, dict)])
    evaluated_case_ids = {
        str(item.get("case_id") or "").strip()
        for item in case_results
        if isinstance(item, dict) and str(item.get("case_id") or "").strip()
    }
    evaluated_case_count = len(evaluated_case_ids) if evaluated_case_ids else len([item for item in case_results if isinstance(item, dict)])
    pytest_counts = _pytest_output_counts(output)
    pytest_summary_detected = pytest_counts["collected"] > 0
    unevaluated_case_count = max(0, declared_case_count - evaluated_case_count)
    return {
        "declared_case_count": declared_case_count,
        "evaluated_case_count": evaluated_case_count,
        "unevaluated_case_count": unevaluated_case_count,
        "coverage_rate": _ratio(evaluated_case_count, declared_case_count) if declared_case_count else None,
        "pytest_summary_detected": pytest_summary_detected,
        "pytest_selected_count": pytest_counts["selected"],
        "pytest_deselected_count": pytest_counts["deselected"],
        "pytest_collected_count": pytest_counts["collected"],
        "source": "record_eval_run",
    }


def _legacy_eval_scope_summary(connection, eval_run_id: str, summary: dict[str, object]) -> dict[str, object]:
    row = connection.execute(
        "SELECT COUNT(*) AS count FROM eval_results WHERE eval_run_id = ?",
        (eval_run_id,),
    ).fetchone()
    evaluated_case_count = int(row["count"] or 0) if row is not None else 0
    declared_case_count = _as_int(summary.get("total"))
    if declared_case_count is None or declared_case_count < evaluated_case_count:
        declared_case_count = evaluated_case_count
    unevaluated_case_count = max(0, declared_case_count - evaluated_case_count)
    return {
        "declared_case_count": declared_case_count,
        "evaluated_case_count": evaluated_case_count,
        "unevaluated_case_count": unevaluated_case_count,
        "coverage_rate": _ratio(evaluated_case_count, declared_case_count) if declared_case_count else None,
        "pytest_summary_detected": False,
        "pytest_selected_count": 0,
        "pytest_deselected_count": 0,
        "pytest_collected_count": 0,
        "source": "legacy_inferred",
    }


def _legacy_pytest_counts_summary(summary: dict[str, object]) -> dict[str, object]:
    passed = _as_int(summary.get("passed")) or 0
    failed = _as_int(summary.get("failed")) or 0
    selected = passed + failed
    return {
        "passed": passed,
        "failed": failed,
        "deselected": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "error": 0,
        "errors": 0,
        "selected": selected,
        "collected": selected,
        "source": "legacy_unavailable",
    }
