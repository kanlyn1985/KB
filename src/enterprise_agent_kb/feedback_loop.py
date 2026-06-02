from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import AppPaths
from .db import connect
from .generated_tests import auto_activate_golden_cases
from .coverage import build_coverage_for_document


@dataclass(frozen=True)
class EvalFailure:
    case_query: str
    case_must_include: str
    failure_type: str   # "retrieval_miss" | "answer_mismatch" | "context_miss"
    root_cause: str
    suggested_action: str


@dataclass(frozen=True)
class FeedbackAction:
    action_type: str    # "auto_activate_golden" | "rebuild_coverage"
    doc_id: str
    details: dict[str, object]


def record_low_confidence_query(
    workspace_root: Path,
    query: str,
    doc_id: str | None,
    confidence: float,
    answer_mode: str | None = None,
    answer_preview: str | None = None,
) -> int:
    """Record a low-confidence query to the feedback queue. Returns the row id."""
    from .closed_loop_store import utc_now

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        # Ensure the table exists (idempotent for existing DBs)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS low_confidence_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                doc_id TEXT,
                confidence REAL NOT NULL,
                answer_mode TEXT,
                answer_preview TEXT,
                created_at TEXT NOT NULL,
                processed INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor = connection.execute(
            """INSERT INTO low_confidence_queries
               (query, doc_id, confidence, answer_mode, answer_preview, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (query, doc_id, confidence, answer_mode, answer_preview, utc_now()),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def drain_low_confidence_queries(
    workspace_root: Path,
    limit: int = 100,
) -> list[dict[str, object]]:
    """Read and mark unprocessed low-confidence queries. Returns list of query dicts."""
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        rows = connection.execute(
            """SELECT id, query, doc_id, confidence, answer_mode, answer_preview, created_at
               FROM low_confidence_queries
               WHERE processed = 0
               ORDER BY created_at ASC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        ids = [row["id"] for row in rows]
        if ids:
            connection.execute(
                f"UPDATE low_confidence_queries SET processed = 1 WHERE id IN ({','.join('?' * len(ids))})",
                ids,
            )
            connection.commit()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def schedule_quality_improvement(
    workspace_root: Path,
    low_confidence_threshold: float = 0.3,
    doc_hotspot_threshold: int = 5,
) -> list[FeedbackAction]:
    """Check low-confidence query frequency and schedule improvements if needed.

    A doc_id with >= doc_hotspot_threshold recent low-confidence queries
    triggers a rebuild_coverage action. Returns the actions scheduled.
    """
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        # Count unprocessed low-confidence queries by doc_id
        rows = connection.execute(
            """SELECT doc_id, COUNT(*) as cnt
               FROM low_confidence_queries
               WHERE processed = 0 AND confidence < ?
               GROUP BY doc_id
               HAVING cnt >= ?""",
            (low_confidence_threshold, doc_hotspot_threshold),
        ).fetchall()
    finally:
        connection.close()

    actions: list[FeedbackAction] = []
    for row in rows:
        doc_id = row["doc_id"]
        if doc_id:
            actions.append(FeedbackAction(
                action_type="rebuild_coverage",
                doc_id=doc_id,
                details={"low_confidence_count": row["cnt"]},
            ))
    return actions


def analyze_eval_failures(eval_report_path: Path) -> list[EvalFailure]:
    """Parse an eval report JSON and extract failure cases with attribution."""
    if not eval_report_path.exists():
        return []

    try:
        payload = json.loads(eval_report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    cases = payload.get("cases") or payload.get("results") or []
    if not isinstance(cases, list):
        return []

    failures: list[EvalFailure] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        status = str(case.get("status") or case.get("outcome") or "")
        if status not in ("failed", "FAIL", "miss", "mismatch"):
            continue

        query = str(case.get("query") or "")
        must_include = str(case.get("must_include") or "")
        target_doc_id = str(case.get("target_doc_id") or "")

        # Deterministic attribution based on failure signals
        retrieval_hits = case.get("retrieval_hits") or case.get("hit_count") or 0
        answer_match = case.get("answer_match") or case.get("must_include_found") or False
        context_match = case.get("context_match") or False

        if int(retrieval_hits) == 0:
            failure_type = "retrieval_miss"
            root_cause = "retrieval_blank"
            suggested_action = "check_fact_extraction_coverage"
        elif not answer_match:
            failure_type = "answer_mismatch"
            root_cause = "answer_construction_failed"
            suggested_action = "check_fact_linkage"
        else:
            failure_type = "context_miss"
            root_cause = "context_gap"
            suggested_action = "check_evidence_shape_coverage"

        failures.append(EvalFailure(
            case_query=query,
            case_must_include=must_include,
            failure_type=failure_type,
            root_cause=root_cause,
            suggested_action=suggested_action,
        ))

    return failures


def generate_feedback_actions(
    workspace_root: Path,
    failures: list[EvalFailure],
) -> list[FeedbackAction]:
    """Convert eval failures into concrete repair actions."""
    actions: list[FeedbackAction] = []
    paths = AppPaths.from_root(workspace_root)

    # Group failures by doc_id and type
    doc_ids_with_misses: set[str] = set()
    doc_ids_with_mismatches: set[str] = set()

    for failure in failures:
        # Try to infer doc_id from must_include or query
        doc_id = _infer_doc_id(paths, failure)
        if not doc_id:
            continue
        if failure.failure_type == "retrieval_miss":
            doc_ids_with_misses.add(doc_id)
        elif failure.failure_type in ("answer_mismatch", "context_miss"):
            doc_ids_with_mismatches.add(doc_id)

    # For retrieval misses: auto-activate golden cases to improve coverage
    for doc_id in doc_ids_with_misses:
        actions.append(FeedbackAction(
            action_type="auto_activate_golden",
            doc_id=doc_id,
            details={"reason": "retrieval_miss", "failure_count": sum(
                1 for f in failures if _infer_doc_id(paths, f) == doc_id and f.failure_type == "retrieval_miss"
            )},
        ))

    # For answer mismatches: rebuild coverage to refresh links
    for doc_id in doc_ids_with_mismatches:
        actions.append(FeedbackAction(
            action_type="rebuild_coverage",
            doc_id=doc_id,
            details={"reason": "answer_mismatch", "failure_count": sum(
                1 for f in failures if _infer_doc_id(paths, f) == doc_id and f.failure_type in ("answer_mismatch", "context_miss")
            )},
        ))

    return actions


def execute_feedback_actions(
    workspace_root: Path,
    actions: list[FeedbackAction],
    *,
    dry_run: bool = False,
) -> list[dict[str, object]]:
    """Execute feedback repair actions."""
    results: list[dict[str, object]] = []

    for action in actions:
        if dry_run:
            results.append({
                "action_type": action.action_type,
                "doc_id": action.doc_id,
                "status": "dry_run",
                "details": action.details,
            })
            continue

        if action.action_type == "auto_activate_golden":
            result = auto_activate_golden_cases(workspace_root, action.doc_id)
            results.append({
                "action_type": action.action_type,
                "doc_id": action.doc_id,
                "status": "executed",
                "promoted_count": result.get("promoted_case_count"),
                "test_coverage_rate": result.get("test_coverage_rate"),
            })

        elif action.action_type == "rebuild_coverage":
            result = build_coverage_for_document(workspace_root, action.doc_id)
            results.append({
                "action_type": action.action_type,
                "doc_id": action.doc_id,
                "status": "executed",
                "test_coverage_rate": result.test_coverage_rate,
                "source_unit_count": result.source_unit_count,
            })

        else:
            results.append({
                "action_type": action.action_type,
                "doc_id": action.doc_id,
                "status": "unknown_action",
            })

    return results


def _infer_doc_id(paths: AppPaths, failure: EvalFailure) -> str:
    """Try to infer the doc_id from the failure's query or must_include."""
    # Check if target_doc_id is embedded in the must_include
    must = failure.case_must_include
    # Common pattern: DOC-XXXXXX in must_include
    import re
    match = re.search(r"DOC-\d+", must)
    if match:
        return match.group(0)
    return ""