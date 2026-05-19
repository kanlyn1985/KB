from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .config import AppPaths
from .corpus_eval import _case_fingerprint, _case_from_source_unit, _load_source_unit_rows, _selected_case_types, _skip_reason
from .closed_loop_store import utc_now
from .db import connect


GoldenOrigin = Literal["source_unit", "coverage_gap", "eval_failure", "manual_query", "ontology_gap"]
ConfidenceTier = Literal["corpus_eval", "draft", "review_required", "golden_active", "blocked"]

ASSERTION_SIGNAL_FIELDS = (
    "must_hit",
    "negative_expected",
    "expected_doc_id",
    "expected_query_type",
    "expected_evidence_shape",
    "expected_answer_mode",
    "clarification_options",
)


@dataclass(frozen=True)
class AssertionContract:
    must_hit: tuple[str, ...] = ()
    negative_expected: tuple[str, ...] = ()
    expected_doc_id: str | None = None
    expected_query_type: str | None = None
    expected_evidence_shape: str | None = None
    expected_answer_mode: str | None = None
    clarification_options: tuple[str, ...] = ()

    def has_signal(self) -> bool:
        return any(
            (
                self.must_hit,
                self.negative_expected,
                self.expected_doc_id,
                self.expected_query_type,
                self.expected_evidence_shape,
                self.expected_answer_mode,
                self.clarification_options,
            )
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value not in (None, (), [])}


@dataclass(frozen=True)
class ActivationReadiness:
    can_activate: bool
    readiness_status: str
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "can_activate": self.can_activate,
            "readiness_status": self.readiness_status,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class GoldenCandidate:
    case_id: str
    query: str
    origin: GoldenOrigin
    confidence_tier: ConfidenceTier
    assertion_contract: AssertionContract
    trace: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)

    def readiness(self) -> ActivationReadiness:
        return evaluate_activation_readiness(self)

    def to_dict(self) -> dict[str, object]:
        readiness = self.readiness()
        return {
            "case_id": self.case_id,
            "query": self.query,
            "origin": self.origin,
            "confidence_tier": self.confidence_tier,
            "assertion_contract": self.assertion_contract.to_dict(),
            "trace": self.trace,
            "metadata": self.metadata,
            "readiness": readiness.to_dict(),
        }

    def to_golden_case(self, *, status: str | None = None, source: str | None = None) -> dict[str, object]:
        contract = self.assertion_contract
        readiness = self.readiness()
        return {
            "case_id": self.case_id,
            "query": self.query,
            "assert_mode": _assert_mode_for_candidate(self),
            "must_hit": list(contract.must_hit),
            "negative_expected": list(contract.negative_expected),
            "expected_evidence_shape": contract.expected_evidence_shape,
            "status": status or _golden_status_for_tier(self.confidence_tier),
            "source": source or f"golden_generation:{self.origin}",
            "metadata": {
                **self.metadata,
                "origin": self.origin,
                "confidence_tier": self.confidence_tier,
                "assertion_contract": contract.to_dict(),
                "trace": self.trace,
                "readiness": readiness.to_dict(),
            },
        }


@dataclass(frozen=True)
class GoldenGenerationResult:
    candidates: tuple[GoldenCandidate, ...]
    summary: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


@dataclass(frozen=True)
class GoldenGenerationRunResult:
    candidates: tuple[GoldenCandidate, ...]
    summary: dict[str, object]
    json_path: Path
    report_path: Path

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "candidate_count": len(self.candidates),
            "json_path": str(self.json_path),
            "report_path": str(self.report_path),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def make_assertion_contract(payload: dict[str, object] | None = None, **overrides: object) -> AssertionContract:
    data = {**(payload or {}), **{key: value for key, value in overrides.items() if value is not None}}
    return AssertionContract(
        must_hit=tuple(_string_list(data.get("must_hit") or data.get("must_include"))),
        negative_expected=tuple(_string_list(data.get("negative_expected"))),
        expected_doc_id=_optional_text(data.get("expected_doc_id")),
        expected_query_type=_optional_text(data.get("expected_query_type")),
        expected_evidence_shape=_optional_text(data.get("expected_evidence_shape") or data.get("evidence_shape")),
        expected_answer_mode=_optional_text(data.get("expected_answer_mode")),
        clarification_options=tuple(_string_list(data.get("clarification_options"))),
    )


def generate_source_unit_candidates(
    workspace_root: Path,
    *,
    doc_ids: list[str] | None = None,
    limit_per_type: int = 20,
    case_types: list[str] | None = None,
) -> GoldenGenerationResult:
    paths = AppPaths.from_root(workspace_root)
    selected_types = _selected_case_types(case_types)
    rows = _load_source_unit_rows(paths.db_file, doc_ids=doc_ids)
    candidates: list[GoldenCandidate] = []
    case_type_counts: dict[str, int] = {}
    skipped_counts: dict[str, int] = {}
    seen_fingerprints: set[str] = set()
    for row in rows:
        case = _case_from_source_unit(row, selected_types=selected_types)
        if not case:
            reason = _skip_reason(row, selected_types)
            skipped_counts[reason] = skipped_counts.get(reason, 0) + 1
            continue
        fingerprint = _case_fingerprint(case)
        if fingerprint in seen_fingerprints:
            skipped_counts["duplicate_candidate"] = skipped_counts.get("duplicate_candidate", 0) + 1
            continue
        seen_fingerprints.add(fingerprint)
        case_type = str(case.get("case_type") or "")
        if case_type_counts.get(case_type, 0) >= limit_per_type:
            skipped_counts["limit_per_type"] = skipped_counts.get("limit_per_type", 0) + 1
            continue
        case_type_counts[case_type] = case_type_counts.get(case_type, 0) + 1
        candidates.append(_candidate_from_corpus_case(case))
    summary = {
        **summarize_candidates(candidates),
        "source": "source_units",
        "selected_case_types": sorted(selected_types),
        "input_source_unit_count": len(rows),
        "generated_by_case_type": dict(sorted(case_type_counts.items())),
        "skipped_counts": dict(sorted(skipped_counts.items())),
        "doc_ids": list(doc_ids or []),
    }
    return GoldenGenerationResult(candidates=tuple(candidates), summary=summary)


def generate_eval_failure_candidates(
    connection,
    eval_run_id: str,
    *,
    case_ids: list[str] | None = None,
    failure_types: list[str] | None = None,
    limit: int | None = None,
) -> GoldenGenerationResult | None:
    from .closed_loop_store import _draft_case_from_failure, _failure_analysis_item, get_eval_run_detail

    detail = get_eval_run_detail(connection, eval_run_id)
    if detail is None:
        return None
    requested_case_ids = {str(case_id or "").strip() for case_id in (case_ids or []) if str(case_id or "").strip()}
    requested_failure_types = {
        str(failure_type or "").strip()
        for failure_type in (failure_types or [])
        if str(failure_type or "").strip()
    }
    candidates: list[GoldenCandidate] = []
    skipped_counts: dict[str, int] = {}
    for result in detail.get("results", []):
        if not isinstance(result, dict):
            continue
        if result.get("passed"):
            skipped_counts["passed_case"] = skipped_counts.get("passed_case", 0) + 1
            continue
        source_case_id = str(result.get("case_id") or "").strip()
        if requested_case_ids and source_case_id not in requested_case_ids:
            skipped_counts["case_id_not_selected"] = skipped_counts.get("case_id_not_selected", 0) + 1
            continue
        failure = _failure_analysis_item(connection, result, eval_run_id=eval_run_id)
        failure_type = str(failure.get("failure_type") or "").strip()
        if requested_failure_types and failure_type not in requested_failure_types:
            skipped_counts["failure_type_not_selected"] = skipped_counts.get("failure_type_not_selected", 0) + 1
            continue
        draft_case = _draft_case_from_failure(failure, eval_run_id=eval_run_id)
        candidates.append(_candidate_from_failure_draft(draft_case, failure=failure))
        if limit is not None and limit > 0 and len(candidates) >= limit:
            break
    summary = {
        **summarize_candidates(candidates),
        "source": "eval_failures",
        "eval_run_id": eval_run_id,
        "selected_case_ids": sorted(requested_case_ids),
        "selected_failure_types": sorted(requested_failure_types),
        "skipped_counts": dict(sorted(skipped_counts.items())),
    }
    return GoldenGenerationResult(candidates=tuple(candidates), summary=summary)


def generate_golden_candidates(
    workspace_root: Path,
    *,
    origins: list[str] | None = None,
    doc_ids: list[str] | None = None,
    eval_run_id: str | None = None,
    limit_per_type: int = 20,
    case_types: list[str] | None = None,
    output_dir: Path | None = None,
) -> GoldenGenerationRunResult:
    selected_origins = _selected_origins(origins)
    all_candidates: list[GoldenCandidate] = []
    source_summaries: dict[str, object] = {}
    if "source_unit" in selected_origins:
        result = generate_source_unit_candidates(
            workspace_root,
            doc_ids=doc_ids,
            limit_per_type=limit_per_type,
            case_types=case_types,
        )
        all_candidates.extend(result.candidates)
        source_summaries["source_unit"] = result.summary
    if "eval_failure" in selected_origins:
        if not eval_run_id:
            raise ValueError("--eval-run-id is required when origin includes eval_failure")
        paths = AppPaths.from_root(workspace_root)
        connection = connect(paths.db_file)
        try:
            result = generate_eval_failure_candidates(connection, eval_run_id)
        finally:
            connection.close()
        if result is None:
            raise ValueError(f"eval run not found: {eval_run_id}")
        all_candidates.extend(result.candidates)
        source_summaries["eval_failure"] = result.summary
    timestamp = utc_now()
    summary = {
        **summarize_candidates(all_candidates),
        "generated_at": timestamp,
        "origins": selected_origins,
        "doc_ids": list(doc_ids or []),
        "eval_run_id": eval_run_id,
        "dry_run": True,
        "auto_activation": False,
        "source_summaries": source_summaries,
    }
    report_dir = output_dir or AppPaths.from_root(workspace_root).root.parent / "output" / "golden-generation"
    report_dir.mkdir(parents=True, exist_ok=True)
    date_token = timestamp[:10]
    json_path = report_dir / f"golden_candidates_{date_token}.json"
    report_path = report_dir / f"golden_candidates_{date_token}.md"
    payload = {"summary": summary, "candidates": [candidate.to_dict() for candidate in all_candidates]}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(_render_generation_report(payload), encoding="utf-8")
    return GoldenGenerationRunResult(
        candidates=tuple(all_candidates),
        summary=summary,
        json_path=json_path,
        report_path=report_path,
    )


def make_golden_candidate(
    *,
    query: str,
    origin: GoldenOrigin,
    confidence_tier: ConfidenceTier,
    assertion_contract: AssertionContract | dict[str, object],
    trace: dict[str, object] | None = None,
    metadata: dict[str, object] | None = None,
    case_id: str | None = None,
) -> GoldenCandidate:
    contract = assertion_contract if isinstance(assertion_contract, AssertionContract) else make_assertion_contract(assertion_contract)
    stable_id = case_id or _candidate_id(query, origin, confidence_tier, contract.to_dict(), trace or {})
    return GoldenCandidate(
        case_id=stable_id,
        query=str(query or "").strip(),
        origin=origin,
        confidence_tier=confidence_tier,
        assertion_contract=contract,
        trace=dict(trace or {}),
        metadata=dict(metadata or {}),
    )


def evaluate_activation_readiness(candidate: GoldenCandidate | dict[str, object]) -> ActivationReadiness:
    if isinstance(candidate, dict):
        candidate = _candidate_from_dict(candidate)
    reasons: list[str] = []
    query = candidate.query.strip()
    contract = candidate.assertion_contract
    if not query:
        reasons.append("missing_query")
    if not contract.has_signal():
        reasons.append("missing_assertion_signal")
    if candidate.confidence_tier == "blocked":
        reasons.append("candidate_tier_blocked")
    if candidate.confidence_tier == "corpus_eval":
        reasons.append("corpus_eval_requires_review")
    if candidate.origin == "eval_failure" and not (contract.must_hit or contract.expected_evidence_shape or contract.expected_answer_mode):
        reasons.append("eval_failure_missing_stable_expected_contract")
    if candidate.origin == "ontology_gap":
        reasons.append("ontology_gap_generation_not_implemented")

    blocking = {
        "missing_query",
        "missing_assertion_signal",
        "candidate_tier_blocked",
        "eval_failure_missing_stable_expected_contract",
        "ontology_gap_generation_not_implemented",
    }
    if any(reason in blocking for reason in reasons):
        return ActivationReadiness(False, "blocked", tuple(reasons))
    if reasons:
        return ActivationReadiness(False, "review_required", tuple(reasons))
    if candidate.confidence_tier == "golden_active":
        return ActivationReadiness(True, "active", ())
    return ActivationReadiness(True, "ready", ())


def summarize_candidates(candidates: list[GoldenCandidate | dict[str, object]]) -> dict[str, object]:
    normalized = [_candidate_from_dict(item) if isinstance(item, dict) else item for item in candidates]
    by_origin: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    readiness_counts: dict[str, int] = {}
    blocked_reasons: dict[str, int] = {}
    for candidate in normalized:
        by_origin[candidate.origin] = by_origin.get(candidate.origin, 0) + 1
        by_tier[candidate.confidence_tier] = by_tier.get(candidate.confidence_tier, 0) + 1
        readiness = candidate.readiness()
        readiness_counts[readiness.readiness_status] = readiness_counts.get(readiness.readiness_status, 0) + 1
        for reason in readiness.reasons:
            blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
    return {
        "candidate_count": len(normalized),
        "by_origin": dict(sorted(by_origin.items())),
        "by_confidence_tier": dict(sorted(by_tier.items())),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "blocked_reasons": dict(sorted(blocked_reasons.items())),
    }


def _selected_origins(origins: list[str] | None) -> list[str]:
    selected = [str(origin or "").strip() for origin in (origins or ["source_unit"]) if str(origin or "").strip()]
    allowed = {"source_unit", "eval_failure"}
    unknown = sorted(set(selected) - allowed)
    if unknown:
        raise ValueError(f"unsupported golden candidate origin(s): {', '.join(unknown)}")
    result: list[str] = []
    for origin in selected:
        if origin not in result:
            result.append(origin)
    return result or ["source_unit"]


def _render_generation_report(payload: dict[str, object]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    lines = [
        "# Golden Generation Candidates",
        "",
        f"- generated_at: {summary.get('generated_at')}",
        f"- candidate_count: {summary.get('candidate_count', 0)}",
        f"- origins: {', '.join(str(item) for item in summary.get('origins', []) or [])}",
        f"- dry_run: {summary.get('dry_run')}",
        f"- auto_activation: {summary.get('auto_activation')}",
        "",
        "## Summary",
        "",
        f"- by_origin: {json.dumps(summary.get('by_origin', {}), ensure_ascii=False)}",
        f"- by_confidence_tier: {json.dumps(summary.get('by_confidence_tier', {}), ensure_ascii=False)}",
        f"- readiness_counts: {json.dumps(summary.get('readiness_counts', {}), ensure_ascii=False)}",
        f"- blocked_reasons: {json.dumps(summary.get('blocked_reasons', {}), ensure_ascii=False)}",
        "",
        "## Candidates",
        "",
    ]
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    for candidate in candidates[:100]:
        if not isinstance(candidate, dict):
            continue
        readiness = candidate.get("readiness") if isinstance(candidate.get("readiness"), dict) else {}
        lines.extend(
            [
                f"### {candidate.get('case_id')}",
                "",
                f"- query: {candidate.get('query')}",
                f"- origin: {candidate.get('origin')}",
                f"- confidence_tier: {candidate.get('confidence_tier')}",
                f"- readiness: {readiness.get('readiness_status')}",
                f"- reasons: {', '.join(str(item) for item in readiness.get('reasons', []) or [])}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _candidate_from_corpus_case(case: dict[str, object]) -> GoldenCandidate:
    trace = {
        "coverage_unit_id": case.get("coverage_unit_id"),
        "coverage_semantic_key": case.get("coverage_semantic_key"),
        "expected_pages": case.get("expected_pages") or [],
        "source_unit_type": case.get("source_unit_type"),
        "source_unit_role": case.get("source_unit_role"),
    }
    metadata = {
        "source": "corpus_eval",
        "case_type": case.get("case_type"),
        "original_case_id": case.get("case_id"),
        "expected_min_graph_candidates": case.get("expected_min_graph_candidates"),
        "corpus_metadata": case.get("metadata") if isinstance(case.get("metadata"), dict) else {},
    }
    contract = {
        "must_hit": case.get("retrieval_must_hit") or case.get("must_hit") or [],
        "negative_expected": case.get("negative_expected") or [],
        "expected_doc_id": case.get("expected_doc_id"),
        "expected_query_type": case.get("expected_query_type"),
        "expected_evidence_shape": case.get("expected_evidence_shape"),
    }
    return make_golden_candidate(
        case_id=str(case.get("case_id") or "") or None,
        query=str(case.get("query") or ""),
        origin="source_unit",
        confidence_tier="corpus_eval",
        assertion_contract=contract,
        trace={key: value for key, value in trace.items() if value not in (None, "", [])},
        metadata={key: value for key, value in metadata.items() if value not in (None, "", [])},
    )


def _candidate_from_failure_draft(draft_case: dict[str, object], *, failure: dict[str, object]) -> GoldenCandidate:
    trace = {
        "source_eval_run_id": draft_case.get("source_eval_run_id"),
        "source_case_id": draft_case.get("source_case_id"),
        "failure_type": draft_case.get("failure_type"),
        "actual_top_items": _failure_top_item_ids(failure),
    }
    metadata = {
        "source": "failure_analysis",
        "failure_reason": failure.get("failure_reason"),
        "legacy_draft_case_id": draft_case.get("case_id"),
        "legacy_readiness_status": draft_case.get("readiness_status"),
        "legacy_readiness_reasons": draft_case.get("readiness_reasons") or [],
        "legacy_readiness_blockers": draft_case.get("readiness_blockers") or [],
        "legacy_can_activate": draft_case.get("can_activate"),
    }
    contract = {
        "must_hit": draft_case.get("must_hit") or [],
        "negative_expected": draft_case.get("negative_expected") or [],
        "expected_evidence_shape": draft_case.get("expected_evidence_shape"),
    }
    tier: ConfidenceTier = "draft"
    if not make_assertion_contract(contract).has_signal():
        tier = "blocked"
    return make_golden_candidate(
        case_id=str(draft_case.get("case_id") or "") or None,
        query=str(draft_case.get("query") or ""),
        origin="eval_failure",
        confidence_tier=tier,
        assertion_contract=contract,
        trace={key: value for key, value in trace.items() if value not in (None, "", [])},
        metadata={key: value for key, value in metadata.items() if value not in (None, "", [])},
    )


def _failure_top_item_ids(failure: dict[str, object]) -> list[str]:
    actual = failure.get("actual") if isinstance(failure.get("actual"), dict) else {}
    items = actual.get("retrieved_items") if isinstance(actual.get("retrieved_items"), list) else []
    result: list[str] = []
    for item in items[:5]:
        if not isinstance(item, dict):
            continue
        value = item.get("result_id") or item.get("fact_id") or item.get("evidence_id") or item.get("id")
        text = str(value or "").strip()
        if text:
            result.append(text)
    return result


def _candidate_from_dict(payload: dict[str, object]) -> GoldenCandidate:
    return make_golden_candidate(
        case_id=_optional_text(payload.get("case_id")),
        query=str(payload.get("query") or ""),
        origin=_origin(payload.get("origin")),
        confidence_tier=_tier(payload.get("confidence_tier")),
        assertion_contract=make_assertion_contract(
            payload.get("assertion_contract") if isinstance(payload.get("assertion_contract"), dict) else payload
        ),
        trace=payload.get("trace") if isinstance(payload.get("trace"), dict) else {},
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    )


def _assert_mode_for_candidate(candidate: GoldenCandidate) -> str:
    contract = candidate.assertion_contract
    if contract.clarification_options:
        return "clarification"
    if contract.expected_answer_mode:
        return "answer_mode"
    if contract.must_hit or contract.expected_evidence_shape:
        return "context_contains"
    return "rich_answer"


def _golden_status_for_tier(tier: ConfidenceTier) -> str:
    if tier == "golden_active":
        return "active"
    if tier == "blocked":
        return "blocked"
    return "draft"


def _candidate_id(
    query: str,
    origin: str,
    confidence_tier: str,
    assertion_contract: dict[str, object],
    trace: dict[str, object],
) -> str:
    digest = hashlib.sha1(
        json.dumps(
            {
                "query": query,
                "origin": origin,
                "confidence_tier": confidence_tier,
                "assertion_contract": assertion_contract,
                "trace": trace,
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()[:16].upper()
    return f"GGV1-{digest}"


def _origin(value: object) -> GoldenOrigin:
    text = str(value or "").strip()
    if text in {"source_unit", "coverage_gap", "eval_failure", "manual_query", "ontology_gap"}:
        return text  # type: ignore[return-value]
    return "manual_query"


def _tier(value: object) -> ConfidenceTier:
    text = str(value or "").strip()
    if text in {"corpus_eval", "draft", "review_required", "golden_active", "blocked"}:
        return text  # type: ignore[return-value]
    return "draft"


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, (list, tuple, set)):
        raw_items = [str(item) for item in value]
    else:
        raw_items = [str(value)]
    seen: set[str] = set()
    result: list[str] = []
    for item in raw_items:
        text = item.strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
