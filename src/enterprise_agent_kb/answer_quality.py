from __future__ import annotations

import re
from typing import Any

from .evidence_shapes import allowed_evidence_shapes, evidence_gate_applies_for_contract


def evaluate_answer_quality(
    *,
    case: dict[str, object],
    answer_text: str,
    retrieved_items: list[dict[str, object]],
    expected_present: bool,
    target_doc_present: bool,
    negative_hits: list[str],
    answer_mode: str,
    trace_metrics: dict[str, object],
) -> dict[str, object]:
    """Evaluate answer usability with deterministic signals.

    LLM output is treated as a candidate answer. This layer only checks whether
    the candidate satisfies anchors, mode constraints, evidence/citation signals,
    and forbidden content constraints from the golden case.
    """

    expected_mode = _first_text(
        case.get("expected_answer_mode"),
        case.get("answer_mode"),
    )
    mode_match = None if not expected_mode else _normalize(answer_mode) == _normalize(expected_mode)
    query_type = str(trace_metrics.get("query_type") or "").strip()
    expected_evidence_shape = _first_text(
        case.get("expected_evidence_shape"),
        case.get("evidence_shape"),
    ) or _contract_expected_shape(query_type)
    actual_evidence_shape = str(trace_metrics.get("evidence_shape") or "").strip()
    evidence_shape_match = (
        None
        if not expected_evidence_shape
        else _normalize(actual_evidence_shape) == _normalize(expected_evidence_shape)
    )
    render_artifact_hits = _render_artifact_hits(answer_text)
    forbidden_hits = _forbidden_hits(case, answer_text, negative_hits)
    evidence_sufficient = _bool_or_none(trace_metrics.get("evidence_judge_sufficient"))
    evidence_gate_applied = _evidence_gate_applies(case=case, trace_metrics=trace_metrics)
    citation_present = _citation_present(answer_text=answer_text, retrieved_items=retrieved_items, trace_metrics=trace_metrics)
    citation_correct_signal = bool(citation_present and target_doc_present)
    confidence_signal = _confidence_signal(
        expected_present=expected_present,
        target_doc_present=target_doc_present,
        forbidden_hits=forbidden_hits,
        render_artifact_hits=render_artifact_hits,
        mode_match=mode_match,
        evidence_shape_match=evidence_shape_match,
        evidence_sufficient=evidence_sufficient,
        evidence_gate_applied=evidence_gate_applied,
        citation_correct_signal=citation_correct_signal,
    )
    failure_attribution = _failure_attribution(
        expected_present=expected_present,
        target_doc_present=target_doc_present,
        forbidden_hits=forbidden_hits,
        render_artifact_hits=render_artifact_hits,
        mode_match=mode_match,
        evidence_shape_match=evidence_shape_match,
        evidence_sufficient=evidence_sufficient,
        evidence_gate_applied=evidence_gate_applied,
        citation_present=citation_present,
        fallback_reason=str(trace_metrics.get("fallback_reason") or ""),
    )
    answer_pass = failure_attribution == "ok"
    return {
        "answer_pass": answer_pass,
        "expected_present": bool(expected_present),
        "target_doc_present": bool(target_doc_present),
        "answer_mode": answer_mode,
        "expected_answer_mode": expected_mode or None,
        "answer_mode_match": mode_match,
        "evidence_shape": actual_evidence_shape or None,
        "expected_evidence_shape": expected_evidence_shape or None,
        "evidence_shape_match": evidence_shape_match,
        "citation_present": citation_present,
        "citation_correct_signal": citation_correct_signal,
        "forbidden_hit_count": len(forbidden_hits),
        "forbidden_hits": forbidden_hits,
        "render_artifact_hit_count": len(render_artifact_hits),
        "render_artifact_hits": render_artifact_hits,
        "evidence_sufficient": evidence_sufficient,
        "evidence_gate_applied": evidence_gate_applied,
        "confidence_signal": confidence_signal,
        "failure_attribution": failure_attribution,
    }


def _failure_attribution(
    *,
    expected_present: bool,
    target_doc_present: bool,
    forbidden_hits: list[str],
    render_artifact_hits: list[str],
    mode_match: bool | None,
    evidence_shape_match: bool | None,
    evidence_sufficient: bool | None,
    evidence_gate_applied: bool,
    citation_present: bool,
    fallback_reason: str,
) -> str:
    if not target_doc_present:
        return "target_doc_missing"
    if render_artifact_hits:
        return "answer_render_artifact"
    if forbidden_hits:
        return "forbidden_content"
    if not expected_present:
        return "expected_answer_missing"
    if mode_match is False:
        return "answer_mode_wrong"
    if evidence_shape_match is False:
        return "evidence_shape_wrong"
    if fallback_reason:
        return "fallback_answer"
    if evidence_gate_applied and evidence_sufficient is False:
        return "evidence_not_sufficient"
    if not citation_present:
        return "citation_missing"
    return "ok"


def _confidence_signal(
    *,
    expected_present: bool,
    target_doc_present: bool,
    forbidden_hits: list[str],
    render_artifact_hits: list[str],
    mode_match: bool | None,
    evidence_shape_match: bool | None,
    evidence_sufficient: bool | None,
    evidence_gate_applied: bool,
    citation_correct_signal: bool,
) -> str:
    if not expected_present or not target_doc_present or forbidden_hits or render_artifact_hits or mode_match is False or evidence_shape_match is False:
        return "low"
    if (evidence_gate_applied and evidence_sufficient is False) or not citation_correct_signal:
        return "medium"
    return "high"


def _evidence_gate_applies(*, case: dict[str, object], trace_metrics: dict[str, object]) -> bool:
    query_type = str(trace_metrics.get("query_type") or "").strip()
    evidence_shape = str(trace_metrics.get("evidence_shape") or "").strip()
    return evidence_gate_applies_for_contract(
        query_type=query_type,
        evidence_shape=evidence_shape,
        evidence_judge_reason=str(trace_metrics.get("evidence_judge_reason") or ""),
        require_evidence_judge=_bool_or_none(case.get("require_evidence_judge")),
    )


def _contract_expected_shape(query_type: str) -> str:
    allowed = allowed_evidence_shapes(query_type)
    return allowed[0] if len(allowed) == 1 else ""


def _citation_present(
    *,
    answer_text: str,
    retrieved_items: list[dict[str, object]],
    trace_metrics: dict[str, object],
) -> bool:
    if retrieved_items:
        return True
    top_hit_ids = trace_metrics.get("top_hit_ids")
    if isinstance(top_hit_ids, list) and top_hit_ids:
        return True
    return bool(re.search(r"\b(?:FACT|EVID|DOC|PAGE|WPAGE)-[A-Z0-9_-]+\b", str(answer_text or ""), flags=re.IGNORECASE))


_DEFAULT_FORBIDDEN = [
    "没有找到足够的结构化结果",
    "GB：代替",
]


def _forbidden_hits(case: dict[str, object], answer_text: str, existing_negative_hits: list[str]) -> list[str]:
    candidates: list[str] = []
    candidates.extend(_DEFAULT_FORBIDDEN)
    candidates.extend(_text_list(case.get("forbidden_contains")))
    candidates.extend(_text_list(case.get("negative_expected")))
    candidates.extend(str(item) for item in existing_negative_hits if str(item or "").strip())
    normalized_answer = _normalize(answer_text)
    hits: list[str] = []
    for item in candidates:
        normalized_item = _normalize(item)
        if normalized_item and normalized_item in normalized_answer and item not in hits:
            hits.append(item)
    return hits


def _render_artifact_hits(answer_text: str) -> list[str]:
    text = str(answer_text or "")
    checks = [
        ("html_entity_nbsp", r"&nbsp;|&#160;|&ensp;|&emsp;"),
        ("raw_html_tag", r"<br\s*/?>|</?(?:p|div|span|table|tr|td|th)\b[^>]*>"),
        ("latex_math_delimiter", r"\$[^$]{1,120}\$"),
        ("latex_escape_percent", r"\\%"),
        ("markdown_bold_marker", r"\*\*[^*]{1,120}\*\*"),
        ("duplicate_semicolon", r"；；|;;"),
        ("duplicate_period", r"。。"),
    ]
    hits: list[str] = []
    for name, pattern in checks:
        if re.search(pattern, text, flags=re.IGNORECASE):
            hits.append(name)
    if _has_hard_wrapped_cjk_line(text):
        hits.append("hard_wrapped_cjk_line")
    return hits


def _has_hard_wrapped_cjk_line(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]\s*\r?\n\s*[\u4e00-\u9fff]", str(text or "")))


def _text_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    return []


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def _normalize(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()
