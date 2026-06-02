"""Failure diagnostics: type inference, signal detection, repair suggestions.

Extracted from `closed_loop_store._impl` to isolate the per-case
failure analysis (inferred type, diagnostics, suggested actions)
and the failure-driven `build_failure_analysis` orchestrator that
composes them with repair tasks and eval-run comparison.
"""
from __future__ import annotations

from ._golden_cases import _existing_failure_draft, utc_now
from ._helpers import (
    _safe_json,
    _suggested_actions,
    re_sub_whitespace,
)
from ._retrieval_eval_runs import (
    compare_eval_runs,
    get_eval_run_detail,
)
from ._repair_tasks import (
    _ensure_repair_tasks_table,
    _repair_task_coverage,
    _repair_tasks_for_failures,
    _resolve_repair_tasks_for_fixed_failures,
    _sync_repair_tasks,
)

from ..evidence_shapes import contract_reason_actions

def build_failure_analysis(connection, eval_run_id: str, case_id: str | None = None) -> dict[str, object] | None:
    _ensure_repair_tasks_table(connection)
    detail = get_eval_run_detail(connection, eval_run_id)
    if detail is None:
        return None
    comparison = compare_eval_runs(connection, eval_run_id)
    requested_case_id = str(case_id or "").strip()
    failures = [
        _failure_analysis_item(connection, result, eval_run_id=eval_run_id)
        for result in detail.get("results", [])
        if isinstance(result, dict) and not result.get("passed")
        and (not requested_case_id or str(result.get("case_id") or "") == requested_case_id)
    ]
    failure_type_counts: dict[str, int] = {}
    shape_contract_reason_counts: dict[str, int] = {}
    contract_repair_actions: dict[str, list[str]] = {}
    for item in failures:
        failure_type = str(item.get("failure_type") or "unknown")
        failure_type_counts[failure_type] = failure_type_counts.get(failure_type, 0) + 1
        diagnostics = item.get("diagnostics") if isinstance(item.get("diagnostics"), dict) else {}
        contract_diagnosis = diagnostics.get("shape_contract_diagnosis") if isinstance(diagnostics.get("shape_contract_diagnosis"), dict) else {}
        reason = str(contract_diagnosis.get("reason") or "").strip()
        if reason:
            shape_contract_reason_counts[reason] = shape_contract_reason_counts.get(reason, 0) + 1
            contract_repair_actions.setdefault(reason, contract_reason_actions(reason))
    repair_tasks = _repair_tasks_for_failures(failures)
    if not requested_case_id:
        repair_tasks = _sync_repair_tasks(connection, eval_run_id, repair_tasks)
        resolved_repair_tasks = _resolve_repair_tasks_for_fixed_failures(
            connection,
            eval_run_id=eval_run_id,
            comparison=comparison,
            current_failures=failures,
        )
    else:
        resolved_repair_tasks = []
    repair_coverage = _repair_task_coverage(failures, repair_tasks)
    return {
        "eval_run": {key: value for key, value in detail.items() if key != "results"},
        "failure_count": len(failures),
        "failure_type_counts": dict(sorted(failure_type_counts.items())),
        "shape_contract_reason_counts": dict(sorted(shape_contract_reason_counts.items())),
        "contract_repair_actions": dict(sorted(contract_repair_actions.items())),
        "repair_tasks": repair_tasks,
        "resolved_repair_tasks": resolved_repair_tasks,
        "repair_task_coverage": repair_coverage,
        "comparison": comparison,
        "case_filter": requested_case_id or None,
        "failures": failures,
    }




def _failure_analysis_item(connection, result: dict[str, object], *, eval_run_id: str) -> dict[str, object]:
    case = result.get("case") if isinstance(result.get("case"), dict) else {}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    retrieved_items = result.get("retrieved_items") if isinstance(result.get("retrieved_items"), list) else []
    failure_reason = str(result.get("failure_reason") or "")
    failure_type = _infer_failure_type(
        failure_reason=failure_reason,
        assert_mode=str(case.get("assert_mode") or ""),
        retrieved_items=retrieved_items,
        metrics=metrics,
        answer=str(result.get("answer") or ""),
    )
    diagnostics = _failure_diagnostics(retrieved_items=retrieved_items, metrics=metrics, answer=str(result.get("answer") or ""))
    draft_case = _existing_failure_draft(connection, eval_run_id, str(result.get("case_id") or ""))
    return {
        "case_id": result.get("case_id"),
        "query": case.get("query"),
        "assert_mode": case.get("assert_mode"),
        "expected": {
            "must_hit": case.get("must_hit") or [],
            "negative_expected": case.get("negative_expected") or [],
            "expected_pages": case.get("expected_pages") or [],
            "expected_sections": case.get("expected_sections") or [],
            "expected_evidence_shape": case.get("expected_evidence_shape"),
        },
        "actual": {
            "retrieved_items": retrieved_items[:10],
            "answer": result.get("answer"),
            "metrics": metrics,
        },
        "failure_reason": failure_reason,
        "failure_type": failure_type,
        "diagnostics": diagnostics,
        "suggested_actions": _suggested_actions(failure_type),
        "golden_draft": draft_case,
    }





def _infer_failure_type(
    *,
    failure_reason: str,
    assert_mode: str,
    retrieved_items: list[object],
    metrics: dict[str, object],
    answer: str,
) -> str:
    reason = failure_reason.lower()
    answer_quality = metrics.get("answer_quality") if isinstance(metrics.get("answer_quality"), dict) else {}
    answer_attribution = str(answer_quality.get("failure_attribution") or "")
    if answer_attribution in {
        "answer_render_artifact",
        "forbidden_content",
        "answer_mode_wrong",
        "evidence_shape_wrong",
        "evidence_not_sufficient",
        "fallback_answer",
        "citation_missing",
    }:
        if answer_attribution == "forbidden_content":
            return "llm_generation_wrong"
        if answer_attribution == "answer_mode_wrong":
            return "answer_policy_wrong"
        if answer_attribution == "evidence_not_sufficient":
            return "evidence_judge_wrong"
        if answer_attribution == "fallback_answer":
            return "answer_policy_wrong"
        return answer_attribution
    if _evidence_shape_mismatched(metrics) or "evidence_shape" in reason or "shape" in reason:
        return "evidence_shape_wrong"
    if _has_noisy_entity_signal(retrieved_items, metrics, answer):
        return "entity_quality_pollution"
    if metrics.get("graph_candidate_count") == 0 and _expects_graph_for_query(metrics, assert_mode):
        return "graph_not_engaged"
    if _topic_resolution_missing_or_drifted(metrics):
        return "topic_resolution_wrong"
    if _has_stale_entity_signal(retrieved_items, metrics, answer):
        return "stale_entity_exposed"
    if "parse" in reason:
        return "parse_missing"
    if "evidence" in reason:
        return "evidence_missing"
    if "source_unit" in reason or "unit" in reason:
        return "source_unit_missing"
    if "graph" in reason:
        return "graph_path_missing"
    if "judge" in reason:
        return "evidence_judge_wrong"
    if "policy" in reason or "answer_mode" in reason:
        return "answer_policy_wrong"
    if "llm" in reason or "generation" in reason:
        return "llm_generation_wrong"
    if "rerank" in reason:
        return "rerank_wrong"
    if "retrieval" in reason or "miss" in reason:
        return "retrieval_miss"
    if metrics.get("coarse_result_from_pytest"):
        return "unknown_pytest_failure"
    if assert_mode == "context_contains" and not retrieved_items:
        return "retrieval_miss"
    if assert_mode != "context_contains" and answer:
        return "answer_policy_wrong"
    return "unknown"


def _failure_diagnostics(
    *,
    retrieved_items: list[object],
    metrics: dict[str, object],
    answer: str,
) -> dict[str, object]:
    snippets = [
        str(item.get("snippet") or "")
        for item in retrieved_items
        if isinstance(item, dict)
    ]
    evidence_shape_diagnostics = metrics.get("evidence_shape_diagnostics") if isinstance(metrics.get("evidence_shape_diagnostics"), dict) else {}
    shape_contract = evidence_shape_diagnostics.get("shape_contract") if isinstance(evidence_shape_diagnostics.get("shape_contract"), dict) else {}
    shape_contract_diagnosis = evidence_shape_diagnostics.get("shape_contract_diagnosis") if isinstance(evidence_shape_diagnostics.get("shape_contract_diagnosis"), dict) else {}
    return {
        "query_type": metrics.get("query_type"),
        "retrieval_channels": metrics.get("retrieval_channels") or [],
        "graph_candidate_count": metrics.get("graph_candidate_count", 0),
        "top_hit_graph_source_count": metrics.get("top_hit_graph_source_count", 0),
        "topic_resolution_confidence": metrics.get("topic_resolution_confidence", 0),
        "topic_candidate_names": metrics.get("topic_candidate_names") or [],
        "top_hit_doc_ids": metrics.get("top_hit_doc_ids") or [],
        "top_hit_ids": metrics.get("top_hit_ids") or [],
        "noise_signals": _noise_signals([answer, *snippets, *[str(item) for item in metrics.get("topic_candidate_names") or []]]),
        "evidence_judge_sufficient": metrics.get("evidence_judge_sufficient"),
        "evidence_judge_reason": metrics.get("evidence_judge_reason"),
        "expected_evidence_shape": metrics.get("expected_evidence_shape"),
        "evidence_shape": metrics.get("evidence_shape"),
        "evidence_shape_diagnostics": evidence_shape_diagnostics,
        "shape_contract": shape_contract,
        "shape_contract_diagnosis": shape_contract_diagnosis,
        "retrieval_quality": metrics.get("retrieval_quality") if isinstance(metrics.get("retrieval_quality"), dict) else {},
        "answer_quality": metrics.get("answer_quality") if isinstance(metrics.get("answer_quality"), dict) else {},
    }


def _evidence_shape_mismatched(metrics: dict[str, object]) -> bool:
    answer_quality = metrics.get("answer_quality") if isinstance(metrics.get("answer_quality"), dict) else {}
    if answer_quality.get("evidence_shape_match") is False:
        return True
    expected = str(metrics.get("expected_evidence_shape") or answer_quality.get("expected_evidence_shape") or "").strip()
    actual = str(metrics.get("evidence_shape") or answer_quality.get("evidence_shape") or "").strip()
    return bool(expected and actual and expected != actual)


def _expects_graph_for_query(metrics: dict[str, object], assert_mode: str) -> bool:
    query_type = str(metrics.get("query_type") or "")
    channels = metrics.get("retrieval_channels") if isinstance(metrics.get("retrieval_channels"), list) else []
    if "graph" not in [str(item) for item in channels]:
        return False
    return query_type in {"lifecycle_lookup", "timing_lookup", "parameter_lookup", "definition"} or assert_mode == "context_contains"


def _topic_resolution_missing_or_drifted(metrics: dict[str, object]) -> bool:
    confidence = float(metrics.get("topic_resolution_confidence") or 0.0)
    query_type = str(metrics.get("query_type") or "")
    candidate_names = [str(item) for item in metrics.get("topic_candidate_names") or []]
    if query_type in {"lifecycle_lookup", "timing_lookup", "parameter_lookup"} and confidence <= 0:
        return True
    return bool(candidate_names and _noise_signals(candidate_names))


def _has_stale_entity_signal(retrieved_items: list[object], metrics: dict[str, object], answer: str) -> bool:
    texts = [answer, *[str(item) for item in metrics.get("topic_candidate_names") or []]]
    for item in retrieved_items:
        if isinstance(item, dict):
            texts.append(str(item.get("snippet") or ""))
            texts.append(str(item.get("result_id") or ""))
    return any("stale" in text.lower() for text in texts)


def _has_noisy_entity_signal(retrieved_items: list[object], metrics: dict[str, object], answer: str) -> bool:
    texts = [answer, *[str(item) for item in metrics.get("topic_candidate_names") or []]]
    for item in retrieved_items:
        if isinstance(item, dict):
            texts.append(str(item.get("snippet") or ""))
    return bool(_noise_signals(texts))


def _noise_signals(texts: list[str]) -> list[str]:
    signals: list[str] = []
    for text in texts:
        compact = " ".join(str(text or "").split())
        upper = compact.upper().replace(" ", "")
        if not compact:
            continue
        if "PUBLIC" in upper and len(compact) <= 120:
            signals.append("page_header_public")
        if "BASEPRACTICES" in upper or compact == "基本实践":
            signals.append("table_header_base_practices")
        if "VDAQMC" in upper and len(compact) <= 120:
            signals.append("publisher_header_vda_qmc")
        if "过程参考模型" in compact or "Process reference model" in compact:
            signals.append("reference_model_entity")
        if compact.startswith("--- Page"):
            signals.append("raw_page_text_entity")
        if len(compact) > 180 and ("表" in compact or "图" in compact or "--- Page" in compact):
            signals.append("oversized_table_or_page_title")
    return sorted(set(signals))


