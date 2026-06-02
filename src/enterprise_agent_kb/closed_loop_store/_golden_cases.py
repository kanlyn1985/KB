"""Golden case persistence, listing, activation, and failure-driven drafting.

Extracted from `closed_loop_store._impl` to isolate the golden_cases table
logic from the eval-run / repair-task / failure-type concerns. Cross-module
callers inside this package must import via `from ._golden_cases import ...`.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from ._helpers import (
    _json_list,
    _optional_text,
    _safe_json,
    _stable_id,
    _text_values,
    re_sub_whitespace,
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sync_golden_cases(
    connection,
    doc_id: str,
    cases: list[dict[str, object]],
    *,
    source: str | None = None,
    now: str | None = None,
) -> int:
    timestamp = now or utc_now()
    _ensure_golden_cases_columns(connection)
    seen_case_ids: set[str] = set()
    for index, case in enumerate(cases, start=1):
        case_id = str(case.get("case_id") or _golden_case_id(doc_id, index, case))
        seen_case_ids.add(case_id)
        connection.execute(
            """
            INSERT INTO golden_cases (
                case_id, doc_id, assert_mode, query, must_hit_json,
                negative_expected_json, expected_pages_json, expected_sections_json,
                expected_evidence_shape, status, source, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
                doc_id = excluded.doc_id,
                assert_mode = excluded.assert_mode,
                query = excluded.query,
                must_hit_json = excluded.must_hit_json,
                negative_expected_json = excluded.negative_expected_json,
                expected_pages_json = excluded.expected_pages_json,
                expected_sections_json = excluded.expected_sections_json,
                expected_evidence_shape = excluded.expected_evidence_shape,
                status = excluded.status,
                source = excluded.source,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                case_id,
                doc_id,
                str(case.get("assert_mode") or "rich_answer"),
                str(case.get("query") or ""),
                _json_list(case.get("must_hit") or case.get("must_include")),
                _json_list(case.get("negative_expected")),
                _json_list(case.get("expected_pages") or ([case.get("page_no")] if case.get("page_no") else [])),
                _json_list(case.get("expected_sections")),
                _optional_text(case.get("expected_evidence_shape") or case.get("evidence_shape")),
                str(case.get("status") or "active"),
                str(source or case.get("source") or "generated"),
                json.dumps(
                    {
                        key: value
                        for key, value in case.items()
                        if key not in {
                            "case_id",
                            "doc_id",
                            "assert_mode",
                            "query",
                            "must_hit",
                            "must_include",
                            "expected_evidence_shape",
                            "evidence_shape",
                        }
                    },
                    ensure_ascii=False,
                ),
                timestamp,
                timestamp,
            ),
        )
    if seen_case_ids:
        placeholders = ",".join("?" for _ in seen_case_ids)
        connection.execute(
            f"""
            UPDATE golden_cases
            SET status = 'deprecated', updated_at = ?
            WHERE doc_id = ? AND case_id NOT IN ({placeholders})
            """,
            [timestamp, doc_id, *sorted(seen_case_ids)],
        )
    return len(seen_case_ids)


def _ensure_golden_cases_columns(connection) -> None:
    rows = connection.execute("PRAGMA table_info(golden_cases)").fetchall()
    columns = {str(row["name"]) for row in rows}
    additions = {
        "expected_evidence_shape": "ALTER TABLE golden_cases ADD COLUMN expected_evidence_shape TEXT",
    }
    for column, statement in additions.items():
        if column not in columns:
            connection.execute(statement)


def activate_golden_case_draft(connection, case_id: str) -> dict[str, object] | None:
    _ensure_golden_cases_columns(connection)
    row = connection.execute(
        """
        SELECT case_id, doc_id, assert_mode, query, must_hit_json,
               negative_expected_json, expected_pages_json, expected_sections_json,
               expected_evidence_shape, status, source, metadata_json,
               created_at, updated_at
        FROM golden_cases
        WHERE case_id = ?
        """,
        (case_id,),
    ).fetchone()
    if row is None:
        return None
    metadata = _safe_json(row["metadata_json"], {})
    if not isinstance(metadata, dict):
        metadata = {}
    readiness_metadata = dict(metadata)
    readiness_metadata["negative_expected"] = _safe_json(row["negative_expected_json"], [])
    readiness = _evaluate_golden_draft_readiness(
        query=str(row["query"] or ""),
        must_hit=_safe_json(row["must_hit_json"], []),
        expected_shape=str(row["expected_evidence_shape"] or ""),
        metadata=readiness_metadata,
        current_case_id=str(row["case_id"] or ""),
        connection=connection,
    )
    if not readiness["can_activate"]:
        metadata["last_readiness"] = readiness
        metadata["last_activation_attempt_at"] = utc_now()
        connection.execute(
            """
            UPDATE golden_cases
            SET metadata_json = ?,
                updated_at = ?
            WHERE case_id = ?
            """,
            (json.dumps(metadata, ensure_ascii=False), metadata["last_activation_attempt_at"], case_id),
        )
        return {
            **_golden_case_row_to_dict(row, metadata=metadata, updated_at=metadata["last_activation_attempt_at"]),
            "activation_blocked": True,
            "readiness": readiness,
        }
    metadata["last_readiness"] = readiness
    metadata["activated_from_status"] = row["status"]
    metadata["activated_at"] = utc_now()
    connection.execute(
        """
        UPDATE golden_cases
        SET status = 'active',
            metadata_json = ?,
            updated_at = ?
        WHERE case_id = ?
        """,
        (json.dumps(metadata, ensure_ascii=False), metadata["activated_at"], case_id),
    )
    return {
        **_golden_case_row_to_dict(row, status="active", metadata=metadata, updated_at=metadata["activated_at"]),
        "activation_blocked": False,
        "readiness": readiness,
    }


def _golden_case_id(doc_id: str, index: int, case: dict[str, object]) -> str:
    return _stable_id("CASE", doc_id, index, case.get("query"), case.get("must_include"), case.get("assert_mode"))


def _draft_case_from_failure(failure: dict[str, object], *, eval_run_id: str) -> dict[str, object]:
    expected = failure.get("expected") if isinstance(failure.get("expected"), dict) else {}
    actual = failure.get("actual") if isinstance(failure.get("actual"), dict) else {}
    metrics = actual.get("metrics") if isinstance(actual.get("metrics"), dict) else {}
    retrieved_items = actual.get("retrieved_items") if isinstance(actual.get("retrieved_items"), list) else []
    query = str(failure.get("query") or "").strip()
    source_case_id = str(failure.get("case_id") or "").strip()
    doc_id = _failure_target_doc_id(failure)
    must_hit = _text_values(expected.get("must_hit"))
    negative_expected = _text_values(expected.get("negative_expected"))
    answer_quality = metrics.get("answer_quality") if isinstance(metrics.get("answer_quality"), dict) else {}
    if not negative_expected:
        negative_expected = _text_values(answer_quality.get("forbidden_hits"))
    diagnostics = failure.get("diagnostics") if isinstance(failure.get("diagnostics"), dict) else {}
    shape_contract = diagnostics.get("shape_contract") if isinstance(diagnostics.get("shape_contract"), dict) else {}
    contract_shapes = _text_values(shape_contract.get("allowed_shapes"))
    contract_expected_shape = contract_shapes[0] if contract_shapes else ""
    expected_shape = str(
        expected.get("expected_evidence_shape")
        or answer_quality.get("expected_evidence_shape")
        or contract_expected_shape
        or metrics.get("evidence_shape")
        or ""
    ).strip()
    actual_shape = str(metrics.get("evidence_shape") or answer_quality.get("evidence_shape") or diagnostics.get("evidence_shape") or "").strip()
    shape_metadata = {
        "shape_contract_query_type": shape_contract.get("query_type"),
        "shape_contract_allowed_shapes": contract_shapes,
        "shape_contract_required": shape_contract.get("required"),
        "shape_contract_matched": shape_contract.get("matched"),
        "shape_contract_actual_shape": actual_shape,
        "shape_contract_expected_shape": expected_shape,
    }
    readiness = _evaluate_golden_draft_readiness(
        query=query,
        must_hit=must_hit,
        expected_shape=expected_shape,
        metadata={
            "failure_type": failure.get("failure_type"),
            "source_eval_run_id": eval_run_id,
            "source_case_id": source_case_id,
            "negative_expected": negative_expected,
            **shape_metadata,
        },
        connection=None,
    )
    draft_case = {
        "case_id": _stable_id("CASE-DRAFT", eval_run_id, source_case_id, query),
        "doc_id": doc_id,
        "assert_mode": str(failure.get("assert_mode") or "rich_answer") or "rich_answer",
        "query": query,
        "must_hit": must_hit,
        "negative_expected": negative_expected,
        "expected_pages": _text_values(expected.get("expected_pages")),
        "expected_sections": _text_values(expected.get("expected_sections")),
        "expected_evidence_shape": expected_shape,
        "status": "draft",
        "source": "failure_analysis",
        "failure_type": failure.get("failure_type"),
        "source_eval_run_id": eval_run_id,
        "source_case_id": source_case_id,
        **shape_metadata,
        "readiness_status": readiness["status"],
        "readiness_score": readiness["score"],
        "readiness_reasons": readiness["reasons"],
        "readiness_blockers": readiness["blockers"],
        "can_activate": readiness["can_activate"],
    }
    return draft_case


def _upsert_golden_case(connection, case: dict[str, object]) -> None:
    timestamp = utc_now()
    _ensure_golden_cases_columns(connection)
    metadata = {
        key: value
        for key, value in case.items()
        if key not in {
            "case_id",
            "doc_id",
            "assert_mode",
            "query",
            "must_hit",
            "negative_expected",
            "expected_pages",
            "expected_sections",
            "expected_evidence_shape",
            "status",
            "source",
        }
    }
    connection.execute(
        """
        INSERT INTO golden_cases (
            case_id, doc_id, assert_mode, query, must_hit_json,
            negative_expected_json, expected_pages_json, expected_sections_json,
            expected_evidence_shape, status, source, metadata_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(case_id) DO UPDATE SET
            doc_id = excluded.doc_id,
            assert_mode = excluded.assert_mode,
            query = excluded.query,
            must_hit_json = excluded.must_hit_json,
            negative_expected_json = excluded.negative_expected_json,
            expected_pages_json = excluded.expected_pages_json,
            expected_sections_json = excluded.expected_sections_json,
            expected_evidence_shape = excluded.expected_evidence_shape,
            status = excluded.status,
            source = excluded.source,
            metadata_json = excluded.metadata_json,
            updated_at = excluded.updated_at
        """,
        (
            str(case.get("case_id") or ""),
            str(case.get("doc_id") or "FAILURE-ANALYSIS"),
            str(case.get("assert_mode") or "rich_answer"),
            str(case.get("query") or ""),
            _json_list(case.get("must_hit")),
            _json_list(case.get("negative_expected")),
            _json_list(case.get("expected_pages")),
            _json_list(case.get("expected_sections")),
            _optional_text(case.get("expected_evidence_shape")),
            str(case.get("status") or "draft"),
            str(case.get("source") or "failure_analysis"),
            json.dumps(metadata, ensure_ascii=False),
            timestamp,
            timestamp,
        ),
    )


def _existing_failure_draft(connection, eval_run_id: str, source_case_id: str) -> dict[str, object] | None:
    _ensure_golden_cases_columns(connection)
    rows = connection.execute(
        """
        SELECT case_id, doc_id, assert_mode, query, must_hit_json,
               negative_expected_json, expected_pages_json, expected_sections_json,
               expected_evidence_shape, status, source, metadata_json,
               created_at, updated_at
        FROM golden_cases
        WHERE source = 'failure_analysis'
        ORDER BY updated_at DESC
        """
    ).fetchall()
    for row in rows:
        metadata = _safe_json(row["metadata_json"], {})
        if not isinstance(metadata, dict):
            continue
        if str(metadata.get("source_eval_run_id") or "") == eval_run_id and str(metadata.get("source_case_id") or "") == source_case_id:
            return _golden_case_row_to_dict(row, metadata=metadata)
    return None


def _golden_case_row_to_dict(row, *, status: str | None = None, metadata: dict[str, object] | None = None, updated_at: str | None = None) -> dict[str, object]:
    payload = metadata if metadata is not None else _safe_json(row["metadata_json"], {})
    if not isinstance(payload, dict):
        payload = {}
    return {
        "case_id": row["case_id"],
        "doc_id": row["doc_id"],
        "assert_mode": row["assert_mode"],
        "query": row["query"],
        "must_hit": _safe_json(row["must_hit_json"], []),
        "negative_expected": _safe_json(row["negative_expected_json"], []),
        "expected_pages": _safe_json(row["expected_pages_json"], []),
        "expected_sections": _safe_json(row["expected_sections_json"], []),
        "expected_evidence_shape": row["expected_evidence_shape"],
        "status": status or row["status"],
        "source": row["source"],
        "metadata": payload,
        "created_at": row["created_at"],
        "updated_at": updated_at or row["updated_at"],
    }


def _failure_target_doc_id(failure: dict[str, object]) -> str:
    actual = failure.get("actual") if isinstance(failure.get("actual"), dict) else {}
    metrics = actual.get("metrics") if isinstance(actual.get("metrics"), dict) else {}
    doc_ids = metrics.get("top_hit_doc_ids")
    if isinstance(doc_ids, list):
        for doc_id in doc_ids:
            text = str(doc_id or "").strip()
            if text:
                return text
    for item in actual.get("retrieved_items") or []:
        if isinstance(item, dict):
            text = str(item.get("doc_id") or item.get("source_doc_id") or "").strip()
            if text:
                return text
    return "FAILURE-ANALYSIS"


def _evaluate_golden_draft_readiness(
    *,
    query: str,
    must_hit: object,
    expected_shape: str,
    metadata: dict[str, object],
    connection=None,
    current_case_id: str = "",
) -> dict[str, object]:
    query_text = str(query or "").strip()
    must_hit_values = _text_values(must_hit)
    expected_shape_text = str(expected_shape or "").strip()
    failure_type = str(metadata.get("failure_type") or "").strip()
    source_eval_run_id = str(metadata.get("source_eval_run_id") or "").strip()
    source_case_id = str(metadata.get("source_case_id") or "").strip()
    negative_expected = _text_values(metadata.get("negative_expected"))
    actual_shape = str(metadata.get("shape_contract_actual_shape") or "").strip()
    contract_expected_shape = str(metadata.get("shape_contract_expected_shape") or "").strip()
    contract_matched = metadata.get("shape_contract_matched")

    score = 100
    reasons: list[str] = []
    blockers: list[str] = []

    if not query_text:
        blockers.append("missing_query")
        score -= 60
    if not must_hit_values and not expected_shape_text:
        blockers.append("missing_assertion_signal")
        score -= 45
    if not source_eval_run_id or not source_case_id:
        blockers.append("missing_failure_trace")
        score -= 30
    if not failure_type:
        reasons.append("missing_failure_type")
        score -= 15
    elif failure_type not in {
        "retrieval_miss",
        "rerank_wrong",
        "graph_not_engaged",
        "topic_resolution_wrong",
        "evidence_judge_wrong",
        "evidence_shape_wrong",
        "answer_policy_wrong",
        "answer_render_artifact",
        "llm_generation_wrong",
        "entity_quality_pollution",
        "stale_entity_exposed",
    }:
        reasons.append("failure_type_needs_review")
        score -= 10
    if not negative_expected and failure_type in {"llm_generation_wrong", "answer_render_artifact"}:
        reasons.append("no_negative_expected_for_answer_failure")
        score -= 10
    if failure_type == "evidence_shape_wrong":
        if not expected_shape_text and not contract_expected_shape:
            blockers.append("missing_shape_contract_expected")
            score -= 35
        if not actual_shape:
            blockers.append("missing_shape_contract_actual")
            score -= 25
        if contract_matched is not False:
            reasons.append("shape_contract_not_marked_mismatch")
            score -= 10
    if _looks_like_noisy_draft_query(query_text):
        blockers.append("noisy_query")
        score -= 50
    ignored_case_ids = {value for value in (current_case_id, source_case_id) if value}
    if connection is not None and _has_duplicate_active_golden_case(connection, query_text, ignored_case_ids):
        blockers.append("duplicate_active_case")
        score -= 50

    score = max(0, min(100, score))
    if blockers:
        status = "blocked"
    elif score >= 80:
        status = "ready"
    elif score >= 55:
        status = "needs_anchor_review"
    else:
        status = "blocked"
    return {
        "status": status,
        "score": score,
        "can_activate": status == "ready",
        "blockers": blockers,
        "reasons": reasons,
    }


def _looks_like_noisy_draft_query(query: str) -> bool:
    compact = re_sub_whitespace(query)
    return bool(
        not compact
        or len(compact) > 120
        or compact.upper() in {"PUBLIC", "BASE PRACTICES", "AUTOMOTIVE SPICE"}
        or "目次" in compact
        or "前言" in compact
    )


def _has_duplicate_active_golden_case(connection, query: str, ignored_case_ids: set[str]) -> bool:
    rows = connection.execute(
        """
        SELECT case_id, query
        FROM golden_cases
        WHERE status = 'active'
        """
    ).fetchall()
    normalized_query = re_sub_whitespace(query).lower()
    return any(
        str(row["case_id"] or "") not in ignored_case_ids
        and re_sub_whitespace(str(row["query"] or "")).lower() == normalized_query
        for row in rows
    )


def list_golden_cases(
    connection,
    *,
    doc_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, object]]:
    """List golden cases from the DB, optionally filtered by doc_id and status."""
    _ensure_golden_cases_columns(connection)
    conditions: list[str] = []
    params: list[object] = []
    if doc_id:
        conditions.append("doc_id = ?")
        params.append(doc_id)
    if status:
        conditions.append("status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(max(1, min(int(limit), 500)))
    rows = connection.execute(
        f"""
        SELECT case_id, doc_id, assert_mode, query, must_hit_json,
               negative_expected_json, expected_evidence_shape, status, source
        FROM golden_cases
        {where}
        ORDER BY case_id
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [
        {
            "case_id": row["case_id"],
            "doc_id": row["doc_id"],
            "assert_mode": row["assert_mode"],
            "query": row["query"],
            "must_hit": _safe_json(row["must_hit_json"], []),
            "negative_expected": _safe_json(row["negative_expected_json"], []),
            "expected_evidence_shape": row["expected_evidence_shape"],
            "status": row["status"],
            "source": row["source"],
        }
        for row in rows
    ]


def draft_golden_case_from_failure(connection, eval_run_id: str, case_id: str) -> dict[str, object] | None:
    from ._failure_diagnostics import _failure_analysis_item  # local import: avoids import cycle
    from ._retrieval_eval_runs import get_eval_run_detail  # local import: avoids import cycle
    detail = get_eval_run_detail(connection, eval_run_id)
    if detail is None:
        return None
    target = next(
        (
            result for result in detail.get("results", [])
            if isinstance(result, dict) and str(result.get("case_id") or "") == str(case_id or "")
        ),
        None,
    )
    if target is None:
        return None
    failure = _failure_analysis_item(connection, target, eval_run_id=eval_run_id)
    draft = _draft_case_from_failure(failure, eval_run_id=eval_run_id)
    _upsert_golden_case(connection, draft)
    return {
        "draft_case": draft,
        "failure": failure,
        "status": "drafted",
    }


def draft_golden_cases_from_eval_failures(
    connection,
    eval_run_id: str,
    *,
    case_ids: list[str] | None = None,
    failure_types: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, object] | None:
    from ._failure_diagnostics import _failure_analysis_item  # local import: avoids import cycle
    from ._retrieval_eval_runs import get_eval_run_detail  # local import: avoids import cycle
    detail = get_eval_run_detail(connection, eval_run_id)
    if detail is None:
        return None
    requested_case_ids = {
        str(case_id or "").strip()
        for case_id in (case_ids or [])
        if str(case_id or "").strip()
    }
    requested_failure_types = {
        str(failure_type or "").strip()
        for failure_type in (failure_types or [])
        if str(failure_type or "").strip()
    }
    drafted: list[dict[str, object]] = []
    existing: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for result in detail.get("results", []):
        if not isinstance(result, dict) or result.get("passed"):
            continue
        source_case_id = str(result.get("case_id") or "").strip()
        if requested_case_ids and source_case_id not in requested_case_ids:
            continue
        failure = _failure_analysis_item(connection, result, eval_run_id=eval_run_id)
        failure_type = str(failure.get("failure_type") or "").strip()
        if requested_failure_types and failure_type not in requested_failure_types:
            continue
        draft_case = failure.get("golden_draft") if isinstance(failure.get("golden_draft"), dict) else None
        if draft_case:
            existing.append(draft_case)
        else:
            draft_case = _draft_case_from_failure(failure, eval_run_id=eval_run_id)
            _upsert_golden_case(connection, draft_case)
            drafted.append(draft_case)
        if limit is not None and limit > 0 and len(drafted) + len(existing) >= limit:
            break

    for case_id in sorted(requested_case_ids):
        if not any(str(item.get("source_case_id") or item.get("metadata", {}).get("source_case_id") or "") == case_id for item in [*drafted, *existing]):
            skipped.append({"case_id": case_id, "reason": "failure_case_not_found_or_passed"})

    all_cases = [*drafted, *existing]
    readiness_counts: dict[str, int] = {}
    for item in all_cases:
        status = str(item.get("readiness_status") or item.get("metadata", {}).get("readiness_status") or item.get("status") or "unknown")
        readiness_counts[status] = readiness_counts.get(status, 0) + 1
    return {
        "eval_run_id": eval_run_id,
        "status": "drafted",
        "drafted_count": len(drafted),
        "existing_count": len(existing),
        "skipped_count": len(skipped),
        "total_failure_draft_count": len(all_cases),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "draft_cases": all_cases,
        "skipped": skipped,
    }
