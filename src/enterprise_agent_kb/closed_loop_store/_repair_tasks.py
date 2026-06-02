"""Repair-task persistence and aggregation.

Extracted from `closed_loop_store._impl` to isolate the repair_tasks
table logic (sync, list, status update, priority, repair modules)
from the failure-diagnostic and eval-run concerns. Cross-module
callers inside this package must import via
`from ._repair_tasks import ...`.
"""
from __future__ import annotations

import json

from ._golden_cases import utc_now
from ._helpers import (
    _as_int,
    _json_list,
    _optional_text,
    _ratio,
    _safe_json,
    _stable_id,
    _suggested_actions,
    _text_values,
)

def _repair_tasks_for_failures(failures: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    _add_failure_type_repair_tasks(grouped, failures)
    _add_contract_repair_tasks(grouped, failures)
    return _sorted_repair_tasks(grouped)


def _add_failure_type_repair_tasks(grouped: dict[tuple[str, str], dict[str, object]], failures: list[dict[str, object]]) -> None:
    for failure in failures:
        failure_type = str(failure.get("failure_type") or "unknown").strip() or "unknown"
        actions = _suggested_actions(failure_type)
        if not actions:
            continue
        case_id = str(failure.get("case_id") or "").strip()
        diagnostics = failure.get("diagnostics") if isinstance(failure.get("diagnostics"), dict) else {}
        query_type = str(diagnostics.get("query_type") or "").strip()
        for action in actions:
            _add_repair_task(
                grouped,
                reason=failure_type,
                action=action,
                case_id=case_id,
                query_type=query_type,
                module=_failure_type_module(failure_type, action),
                priority=_repair_task_priority(failure_type),
            )


def _add_contract_repair_tasks(grouped: dict[tuple[str, str], dict[str, object]], failures: list[dict[str, object]]) -> None:
    for failure in failures:
        diagnostics = failure.get("diagnostics") if isinstance(failure.get("diagnostics"), dict) else {}
        diagnosis = diagnostics.get("shape_contract_diagnosis") if isinstance(diagnostics.get("shape_contract_diagnosis"), dict) else {}
        reason = str(diagnosis.get("reason") or "").strip()
        if not reason or reason == "contract_matched":
            continue
        actions = diagnosis.get("repair_actions")
        action_values = _text_values(actions) or contract_reason_actions(reason)
        if not action_values:
            continue
        case_id = str(failure.get("case_id") or "").strip()
        query_type = str(diagnostics.get("query_type") or "").strip()
        for action in action_values:
            _add_repair_task(
                grouped,
                reason=reason,
                action=action,
                case_id=case_id,
                query_type=query_type,
                module=_repair_action_module(action),
                priority=_repair_task_priority(reason),
            )


def _add_repair_task(
    grouped: dict[tuple[str, str], dict[str, object]],
    *,
    reason: str,
    action: str,
    case_id: str,
    query_type: str,
    module: str,
    priority: int,
) -> None:
    reason_text = str(reason or "unknown").strip() or "unknown"
    action_text = str(action or "").strip()
    if not action_text:
        return
    key = (reason_text, action_text)
    task = grouped.setdefault(
        key,
        {
            "task_id": _stable_id("REPAIR", reason_text, action_text),
            "reason": reason_text,
            "module": str(module or "system"),
            "action": action_text,
            "case_ids": [],
            "query_types": [],
            "priority": int(priority or 50),
            "status": "proposed",
        },
    )
    if case_id and case_id not in task["case_ids"]:
        task["case_ids"].append(case_id)
    if query_type and query_type not in task["query_types"]:
        task["query_types"].append(query_type)


def _sorted_repair_tasks(grouped: dict[tuple[str, str], dict[str, object]]) -> list[dict[str, object]]:
    for task in grouped.values():
        task["impact_count"] = len(task["case_ids"])
    return sorted(
        grouped.values(),
        key=lambda item: (-int(item.get("priority") or 0), -int(item.get("impact_count") or 0), str(item.get("reason") or ""), str(item.get("action") or "")),
    )


def _repair_task_coverage(failures: list[dict[str, object]], tasks: list[dict[str, object]]) -> dict[str, object]:
    failed_case_ids = {
        str(failure.get("case_id") or "").strip()
        for failure in failures
        if str(failure.get("case_id") or "").strip()
    }
    covered_case_ids: set[str] = set()
    for task in tasks:
        for case_id in task.get("case_ids") or []:
            case_text = str(case_id or "").strip()
            if case_text:
                covered_case_ids.add(case_text)
    uncovered = sorted(failed_case_ids - covered_case_ids)
    total = len(failed_case_ids)
    covered = total - len(uncovered)
    return {
        "failure_case_count": total,
        "covered_failure_case_count": covered,
        "uncovered_failure_case_count": len(uncovered),
        "coverage_rate": _ratio(covered, total) if total else None,
        "uncovered_case_ids": uncovered,
    }


def _sync_repair_tasks(connection, eval_run_id: str, tasks: list[dict[str, object]]) -> list[dict[str, object]]:
    if not tasks:
        return []
    _ensure_repair_tasks_table(connection)
    timestamp = utc_now()
    persisted: list[dict[str, object]] = []
    for task in tasks:
        task_id = str(task.get("task_id") or "").strip()
        if not task_id:
            continue
        existing = connection.execute(
            """
            SELECT task_id, reason, module, action, priority, status,
                   case_ids_json, query_types_json, impact_count,
                   source_eval_run_id, metadata_json, first_seen_at, last_seen_at
            FROM repair_tasks
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        existing_status = str(existing["status"] or "") if existing is not None else ""
        existing_metadata = _safe_json(existing["metadata_json"], {}) if existing is not None else {}
        if not isinstance(existing_metadata, dict):
            existing_metadata = {}
        status = "reopened" if existing_status == "done" else str(task.get("status") or "proposed")
        metadata = {
            **existing_metadata,
            "source": "failure_analysis",
            "source_eval_run_id": eval_run_id,
            "latest_case_ids": task.get("case_ids") or [],
            "latest_query_types": task.get("query_types") or [],
        }
        if existing_status == "done":
            history = metadata.get("status_history")
            if not isinstance(history, list):
                history = []
            history.append(
                {
                    "from": "done",
                    "to": "reopened",
                    "note": f"repair task reappeared in eval run {eval_run_id}",
                    "changed_at": timestamp,
                }
            )
            metadata["status_history"] = history[-50:]
            metadata["last_status_note"] = f"reappeared in eval run {eval_run_id}"
            metadata["last_status_changed_at"] = timestamp
        connection.execute(
            """
            INSERT INTO repair_tasks (
                task_id, reason, module, action, priority, status,
                case_ids_json, query_types_json, impact_count,
                source_eval_run_id, metadata_json, first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                reason = excluded.reason,
                module = excluded.module,
                action = excluded.action,
                priority = excluded.priority,
                status = CASE
                    WHEN repair_tasks.status = 'done' THEN excluded.status
                    ELSE repair_tasks.status
                END,
                case_ids_json = excluded.case_ids_json,
                query_types_json = excluded.query_types_json,
                impact_count = excluded.impact_count,
                source_eval_run_id = excluded.source_eval_run_id,
                metadata_json = excluded.metadata_json,
                last_seen_at = excluded.last_seen_at
            """,
            (
                task_id,
                str(task.get("reason") or "unknown"),
                str(task.get("module") or "system"),
                str(task.get("action") or ""),
                int(task.get("priority") or 50),
                status,
                _json_list(task.get("case_ids")),
                _json_list(task.get("query_types")),
                int(task.get("impact_count") or 0),
                eval_run_id,
                json.dumps(metadata, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
        row = connection.execute(
            """
            SELECT task_id, reason, module, action, priority, status,
                   case_ids_json, query_types_json, impact_count,
                   source_eval_run_id, metadata_json, first_seen_at, last_seen_at
            FROM repair_tasks
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        if row is not None:
            persisted.append(_repair_task_row_to_dict(row))
    return sorted(
        persisted,
        key=lambda item: (-int(item.get("priority") or 0), -int(item.get("impact_count") or 0), str(item.get("reason") or ""), str(item.get("action") or "")),
    )


def _resolve_repair_tasks_for_fixed_failures(
    connection,
    *,
    eval_run_id: str,
    comparison: dict[str, object] | None,
    current_failures: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not comparison:
        return []
    fixed_case_ids = {
        str(item.get("case_id") or "").strip()
        for item in comparison.get("fixed_failures") or []
        if isinstance(item, dict) and str(item.get("case_id") or "").strip()
    }
    if not fixed_case_ids:
        return []
    current_failed_case_ids = {
        str(item.get("case_id") or "").strip()
        for item in current_failures
        if str(item.get("case_id") or "").strip()
    }
    timestamp = utc_now()
    resolved: list[dict[str, object]] = []
    rows = connection.execute(
        """
        SELECT task_id, reason, module, action, priority, status,
               case_ids_json, query_types_json, impact_count,
               source_eval_run_id, metadata_json, first_seen_at, last_seen_at
        FROM repair_tasks
        WHERE status NOT IN ('done', 'dismissed')
        ORDER BY priority DESC, impact_count DESC, last_seen_at DESC
        """
    ).fetchall()
    for row in rows:
        task_case_ids = {
            str(case_id or "").strip()
            for case_id in _safe_json(row["case_ids_json"], [])
            if str(case_id or "").strip()
        }
        if not task_case_ids:
            continue
        if task_case_ids & current_failed_case_ids:
            continue
        if not task_case_ids.issubset(fixed_case_ids):
            continue
        metadata = _safe_json(row["metadata_json"], {})
        if not isinstance(metadata, dict):
            metadata = {}
        history = metadata.get("status_history")
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "from": row["status"],
                "to": "done",
                "note": f"all linked failure cases fixed in eval run {eval_run_id}",
                "changed_at": timestamp,
            }
        )
        metadata["status_history"] = history[-50:]
        metadata["last_status_note"] = f"all linked failure cases fixed in eval run {eval_run_id}"
        metadata["last_status_changed_at"] = timestamp
        metadata["resolved_by_eval_run_id"] = eval_run_id
        metadata["resolved_case_ids"] = sorted(task_case_ids)
        connection.execute(
            """
            UPDATE repair_tasks
            SET status = 'done',
                metadata_json = ?,
                last_seen_at = ?
            WHERE task_id = ?
            """,
            (json.dumps(metadata, ensure_ascii=False), timestamp, row["task_id"]),
        )
        updated = connection.execute(
            """
            SELECT task_id, reason, module, action, priority, status,
                   case_ids_json, query_types_json, impact_count,
                   source_eval_run_id, metadata_json, first_seen_at, last_seen_at
            FROM repair_tasks
            WHERE task_id = ?
            """,
            (row["task_id"],),
        ).fetchone()
        if updated is not None:
            resolved.append(_repair_task_row_to_dict(updated))
    return resolved


def list_repair_tasks(connection, *, status: str | None = None, limit: int = 50) -> list[dict[str, object]]:
    _ensure_repair_tasks_table(connection)
    params: list[object] = []
    where = ""
    if status:
        where = "WHERE status = ?"
        params.append(status)
    params.append(max(1, min(int(limit), 200)))
    rows = connection.execute(
        f"""
        SELECT task_id, reason, module, action, priority, status,
               case_ids_json, query_types_json, impact_count,
               source_eval_run_id, metadata_json, first_seen_at, last_seen_at
        FROM repair_tasks
        {where}
        ORDER BY priority DESC, impact_count DESC, last_seen_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [_repair_task_row_to_dict(row) for row in rows]


def update_repair_task_status(
    connection,
    task_id: str,
    status: str,
    *,
    note: str | None = None,
) -> dict[str, object] | None:
    _ensure_repair_tasks_table(connection)
    task_key = str(task_id or "").strip()
    next_status = str(status or "").strip()
    allowed_statuses = {"proposed", "in_progress", "blocked", "done", "dismissed", "reopened"}
    if next_status not in allowed_statuses:
        raise ValueError(f"invalid_repair_task_status:{next_status}")
    row = connection.execute(
        """
        SELECT task_id, reason, module, action, priority, status,
               case_ids_json, query_types_json, impact_count,
               source_eval_run_id, metadata_json, first_seen_at, last_seen_at
        FROM repair_tasks
        WHERE task_id = ?
        """,
        (task_key,),
    ).fetchone()
    if row is None:
        return None
    metadata = _safe_json(row["metadata_json"], {})
    if not isinstance(metadata, dict):
        metadata = {}
    history = metadata.get("status_history")
    if not isinstance(history, list):
        history = []
    timestamp = utc_now()
    history.append(
        {
            "from": row["status"],
            "to": next_status,
            "note": str(note or "").strip(),
            "changed_at": timestamp,
        }
    )
    metadata["status_history"] = history[-50:]
    metadata["last_status_note"] = str(note or "").strip()
    metadata["last_status_changed_at"] = timestamp
    connection.execute(
        """
        UPDATE repair_tasks
        SET status = ?,
            metadata_json = ?,
            last_seen_at = ?
        WHERE task_id = ?
        """,
        (next_status, json.dumps(metadata, ensure_ascii=False), timestamp, task_key),
    )
    updated = connection.execute(
        """
        SELECT task_id, reason, module, action, priority, status,
               case_ids_json, query_types_json, impact_count,
               source_eval_run_id, metadata_json, first_seen_at, last_seen_at
        FROM repair_tasks
        WHERE task_id = ?
        """,
        (task_key,),
    ).fetchone()
    return _repair_task_row_to_dict(updated) if updated is not None else None


def _repair_task_row_to_dict(row) -> dict[str, object]:
    return {
        "task_id": row["task_id"],
        "reason": row["reason"],
        "module": row["module"],
        "action": row["action"],
        "priority": int(row["priority"] or 0),
        "status": row["status"],
        "case_ids": _safe_json(row["case_ids_json"], []),
        "query_types": _safe_json(row["query_types_json"], []),
        "impact_count": int(row["impact_count"] or 0),
        "source_eval_run_id": row["source_eval_run_id"],
        "metadata": _safe_json(row["metadata_json"], {}),
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
    }


def _ensure_repair_tasks_table(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS repair_tasks (
            task_id TEXT PRIMARY KEY,
            reason TEXT NOT NULL,
            module TEXT NOT NULL,
            action TEXT NOT NULL,
            priority INTEGER NOT NULL,
            status TEXT NOT NULL,
            case_ids_json TEXT NOT NULL DEFAULT '[]',
            query_types_json TEXT NOT NULL DEFAULT '[]',
            impact_count INTEGER NOT NULL DEFAULT 0,
            source_eval_run_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_repair_tasks_status ON repair_tasks(status)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_repair_tasks_reason ON repair_tasks(reason)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_repair_tasks_last_seen_at ON repair_tasks(last_seen_at)")


def _repair_task_priority(reason: str) -> int:
    return {
        "contract_query_type_wrong": 90,
        "contract_parse_gap": 85,
        "contract_candidate_missing": 80,
        "contract_rerank_suppressed_shape": 75,
        "contract_wrong_shape": 70,
        "contract_not_defined": 60,
        "parse_missing": 86,
        "source_unit_missing": 84,
        "evidence_missing": 82,
        "retrieval_miss": 80,
        "graph_not_engaged": 78,
        "graph_path_missing": 76,
        "topic_resolution_wrong": 74,
        "entity_quality_pollution": 72,
        "stale_entity_exposed": 72,
        "rerank_wrong": 70,
        "evidence_shape_wrong": 68,
        "evidence_judge_wrong": 66,
        "answer_render_artifact": 64,
        "answer_policy_wrong": 62,
        "llm_generation_wrong": 60,
        "unknown_pytest_failure": 45,
        "unknown": 40,
    }.get(str(reason or ""), 50)


def _failure_type_module(failure_type: str, action: str) -> str:
    mapped = {
        "parse_missing": "parse.py",
        "source_unit_missing": "coverage",
        "evidence_missing": "evidence/facts",
        "retrieval_miss": "retrieval",
        "rerank_wrong": "reranker.py",
        "graph_path_missing": "graph.py",
        "graph_not_engaged": "topic_resolution.py",
        "topic_resolution_wrong": "topic_resolution.py",
        "entity_quality_pollution": "entities.py",
        "stale_entity_exposed": "retrieval",
        "evidence_judge_wrong": "evidence_judge.py",
        "evidence_shape_wrong": "evidence_shapes.py",
        "answer_policy_wrong": "answer_policy.py",
        "answer_render_artifact": "answer_policy.py",
        "llm_generation_wrong": "answer_api.py",
        "unknown_pytest_failure": "generated_tests.py",
        "unknown": "closed_loop_store.py",
    }.get(str(failure_type or ""))
    return mapped or _repair_action_module(action)


def _repair_action_module(action: str) -> str:
    text = str(action or "")
    for module in (
        "query_rewrite.py",
        "advanced_query_planner.py",
        "query_ambiguity.py",
        "retrieval_router.py",
        "graph.py",
        "topic_resolution.py",
        "query_expansion.py",
        "reranker.py",
        "evidence_judge.py",
        "evidence_shapes.py",
        "answer_policy.py",
        "answer_api.py",
        "entities.py",
        "generated_tests.py",
        "source_units",
        "evidence/facts",
        "coverage",
    ):
        if module in text:
            return module
    if "PDF" in text or "table" in text or "解析" in text:
        return "parse.py"
    if "graph" in text.lower():
        return "graph"
    if "retrieval" in text.lower():
        return "retrieval"
    return "system"


