from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from .evidence_shapes import contract_reason_actions


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sync_source_units_from_matrix(
    connection,
    doc_id: str,
    matrix_rows: list[dict[str, object]],
    *,
    generated_at: str | None = None,
) -> int:
    now = generated_at or utc_now()
    _ensure_source_units_columns(connection)
    ensure_source_unit_mapping_tables(connection)
    connection.execute("DELETE FROM source_unit_fact_map WHERE doc_id = ?", (doc_id,))
    connection.execute("DELETE FROM source_unit_evidence_map WHERE doc_id = ?", (doc_id,))
    connection.execute("DELETE FROM source_units WHERE doc_id = ?", (doc_id,))
    for row in matrix_rows:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        locator = row.get("source_locator") if isinstance(row.get("source_locator"), dict) else {}
        source_text = str(row.get("source_text") or "")
        unit_id = str(row.get("unit_id") or _stable_id("UNIT", doc_id, row))
        canonical_title = _optional_text(row.get("canonical_title") or metadata.get("canonical_title"))
        canonical_key = _optional_text(row.get("canonical_key") or row.get("semantic_key"))
        content_role = _optional_text(row.get("content_role") or metadata.get("content_role"))
        quality_flags = row.get("quality_flags") if isinstance(row.get("quality_flags"), list) else metadata.get("quality_flags")
        connection.execute(
            """
            INSERT INTO source_units (
                unit_id, doc_id, page_no, block_id, unit_type, text,
                normalized_text, canonical_title, canonical_key, content_role,
                quality_flags_json, importance, expected_knowledge_type,
                status, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unit_id,
                doc_id,
                _as_int(row.get("page_no")),
                _optional_text(locator.get("block_id")),
                str(row.get("unit_type") or "unknown"),
                source_text,
                _normalize_text(source_text),
                canonical_title,
                canonical_key,
                content_role,
                json.dumps(quality_flags if isinstance(quality_flags, list) else [], ensure_ascii=False),
                _optional_text(row.get("importance")),
                _optional_text(metadata.get("knowledge_unit_type") or row.get("unit_type")),
                str(row.get("coverage_status") or "unknown"),
                json.dumps(
                    {
                        "semantic_key": row.get("semantic_key"),
                        "aliases": row.get("aliases") or [],
                        "source_locator": locator,
                        "metadata": metadata,
                        "covered_by": row.get("covered_by") or {},
                        "coverage_flags": row.get("coverage_flags") or {},
                        "semantic_misaligned": row.get("semantic_misaligned"),
                    },
                    ensure_ascii=False,
                ),
                now,
                now,
            ),
        )
        _persist_source_unit_links(connection, unit_id, doc_id, row, now)
    return len(matrix_rows)


def _ensure_source_units_columns(connection) -> None:
    rows = connection.execute("PRAGMA table_info(source_units)").fetchall()
    columns = {str(row["name"]) for row in rows}
    additions = {
        "canonical_title": "ALTER TABLE source_units ADD COLUMN canonical_title TEXT",
        "canonical_key": "ALTER TABLE source_units ADD COLUMN canonical_key TEXT",
        "content_role": "ALTER TABLE source_units ADD COLUMN content_role TEXT",
        "quality_flags_json": "ALTER TABLE source_units ADD COLUMN quality_flags_json TEXT NOT NULL DEFAULT '[]'",
    }
    for column, statement in additions.items():
        if column not in columns:
            connection.execute(statement)


def ensure_source_unit_mapping_tables(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS source_unit_fact_map (
            unit_id TEXT NOT NULL,
            fact_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            support_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (unit_id, fact_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS source_unit_evidence_map (
            unit_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            support_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (unit_id, evidence_id)
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_source_unit_fact_map_doc_id ON source_unit_fact_map(doc_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_source_unit_fact_map_fact_id ON source_unit_fact_map(fact_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_source_unit_evidence_map_doc_id ON source_unit_evidence_map(doc_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_source_unit_evidence_map_evidence_id ON source_unit_evidence_map(evidence_id)")


def backfill_source_unit_mappings_from_metadata(
    connection,
    *,
    doc_id: str | None = None,
    generated_at: str | None = None,
    only_missing: bool = False,
) -> dict[str, int]:
    ensure_source_unit_mapping_tables(connection)
    now = generated_at or utc_now()
    missing_filter = """
        AND (
            NOT EXISTS (
                SELECT 1
                FROM source_unit_fact_map sfm
                WHERE sfm.unit_id = su.unit_id
            )
            OR NOT EXISTS (
                SELECT 1
                FROM source_unit_evidence_map sem
                WHERE sem.unit_id = su.unit_id
            )
        )
    """
    if doc_id:
        rows = connection.execute(
            f"""
            SELECT su.unit_id, su.doc_id, su.metadata_json
            FROM source_units su
            WHERE su.doc_id = ?
            {missing_filter if only_missing else ""}
            ORDER BY unit_id
            """,
            (doc_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            f"""
            SELECT su.unit_id, su.doc_id, su.metadata_json
            FROM source_units su
            WHERE 1 = 1
            {missing_filter if only_missing else ""}
            ORDER BY doc_id, unit_id
            """
        ).fetchall()

    fact_link_count = 0
    evidence_link_count = 0
    for row in rows:
        metadata = _json_object(row["metadata_json"])
        covered_by = metadata.get("covered_by") if isinstance(metadata.get("covered_by"), dict) else {}
        fact_ids = _string_ids(covered_by.get("fact_ids"))
        evidence_ids = _string_ids(covered_by.get("evidence_ids"))
        if not evidence_ids and fact_ids:
            evidence_ids = _linked_evidence_ids_for_facts(connection, fact_ids)
        fact_link_count += _insert_source_unit_fact_links(
            connection,
            unit_id=str(row["unit_id"]),
            doc_id=str(row["doc_id"]),
            fact_ids=fact_ids,
            support_type="coverage_metadata",
            now=now,
        )
        evidence_link_count += _insert_source_unit_evidence_links(
            connection,
            unit_id=str(row["unit_id"]),
            doc_id=str(row["doc_id"]),
            evidence_ids=evidence_ids,
            support_type="coverage_metadata",
            now=now,
        )
    return {
        "source_unit_count": len(rows),
        "fact_link_count": fact_link_count,
        "evidence_link_count": evidence_link_count,
    }


def _persist_source_unit_links(connection, unit_id: str, doc_id: str, row: dict[str, object], now: str) -> None:
    covered_by = row.get("covered_by") if isinstance(row.get("covered_by"), dict) else {}
    fact_ids = _string_ids(covered_by.get("fact_ids"))
    evidence_ids = _string_ids(covered_by.get("evidence_ids"))
    if not evidence_ids and fact_ids:
        evidence_ids = _linked_evidence_ids_for_facts(connection, fact_ids)
    _insert_source_unit_fact_links(
        connection,
        unit_id=unit_id,
        doc_id=doc_id,
        fact_ids=fact_ids,
        support_type="coverage_matrix",
        now=now,
    )
    _insert_source_unit_evidence_links(
        connection,
        unit_id=unit_id,
        doc_id=doc_id,
        evidence_ids=evidence_ids,
        support_type="coverage_matrix",
        now=now,
    )


def _insert_source_unit_fact_links(
    connection,
    *,
    unit_id: str,
    doc_id: str,
    fact_ids: list[str],
    support_type: str,
    now: str,
) -> int:
    inserted = 0
    for fact_id in fact_ids:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO source_unit_fact_map (
                unit_id, fact_id, doc_id, support_type, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (unit_id, fact_id, doc_id, support_type, now),
        )
        inserted += max(int(cursor.rowcount or 0), 0)
    return inserted


def _insert_source_unit_evidence_links(
    connection,
    *,
    unit_id: str,
    doc_id: str,
    evidence_ids: list[str],
    support_type: str,
    now: str,
) -> int:
    inserted = 0
    for evidence_id in evidence_ids:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO source_unit_evidence_map (
                unit_id, evidence_id, doc_id, support_type, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (unit_id, evidence_id, doc_id, support_type, now),
        )
        inserted += max(int(cursor.rowcount or 0), 0)
    return inserted


def _linked_evidence_ids_for_facts(connection, fact_ids: list[str]) -> list[str]:
    evidence_ids: set[str] = set()
    for fact_id in fact_ids:
        rows = connection.execute(
            """
            SELECT evidence_id
            FROM fact_evidence_map
            WHERE fact_id = ?
            ORDER BY evidence_id
            """,
            (fact_id,),
        ).fetchall()
        evidence_ids.update(str(row["evidence_id"]) for row in rows if row["evidence_id"])
    return sorted(evidence_ids)


def _json_object(value: object) -> dict[str, object]:
    if not value:
        return {}
    try:
        payload = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _string_ids(value: object) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = [str(item) for item in value]
    else:
        values = []
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        item = item.strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


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


@lru_cache(maxsize=1)
def _runtime_code_version() -> str:
    explicit = os.environ.get("EAKB_CODE_VERSION")
    if explicit:
        return explicit.strip()
    try:
        digest = hashlib.sha1()
        root = Path(__file__).resolve().parents[2]
        for path in sorted((root / "src" / "enterprise_agent_kb").glob("*.py")):
            stat = path.stat()
            digest.update(path.name.encode("utf-8"))
            digest.update(str(int(stat.st_mtime)).encode("ascii"))
            digest.update(str(stat.st_size).encode("ascii"))
        return f"src-{digest.hexdigest()[:12]}"
    except Exception:
        return "runtime-unavailable"


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


def draft_golden_case_from_failure(connection, eval_run_id: str, case_id: str) -> dict[str, object] | None:
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


def _golden_case_id(doc_id: str, index: int, case: dict[str, object]) -> str:
    return _stable_id("CASE", doc_id, index, case.get("query"), case.get("must_include"), case.get("assert_mode"))


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


def _stable_id(prefix: str, *parts: object) -> str:
    return f"{prefix}-{_short_hash(parts)}"


def _short_hash(value: object) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16].upper()


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
        quality = metrics.get("answer_quality") if isinstance(metrics.get("answer_quality"), dict) else {}
        match = quality.get("evidence_shape_match")
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


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _mean_metric(items: list[dict[str, object]], key: str) -> float:
    values: list[float] = []
    for item in items:
        try:
            values.append(float(item.get(key)))
        except (TypeError, ValueError):
            continue
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


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


def re_sub_whitespace(value: str) -> str:
    return " ".join(str(value or "").split())


def _pytest_output_counts(output: str) -> dict[str, int]:
    text = str(output or "")
    keys = (
        "passed",
        "failed",
        "deselected",
        "skipped",
        "xfailed",
        "xpassed",
        "error",
        "errors",
    )
    counts = {key: 0 for key in keys}
    for key in keys:
        matches = re.findall(rf"(\d+)\s+{re.escape(key)}\b", text, flags=re.IGNORECASE)
        if matches:
            counts[key] = int(matches[-1])
    counts["selected"] = counts["passed"] + counts["failed"] + counts["skipped"] + counts["xfailed"] + counts["xpassed"] + counts["error"] + counts["errors"]
    counts["collected"] = counts["selected"] + counts["deselected"]
    return counts


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


def _text_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item or "").strip()]
    return []


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


def _suggested_actions(failure_type: str) -> list[str]:
    mapping = {
        "parse_missing": ["重新解析文档", "检查 OCR/版面解析风险页", "补充 parse quality 回归"],
        "evidence_missing": ["检查 source unit 是否生成 evidence", "修 evidence 抽取规则", "查看 page/block 链路"],
        "source_unit_missing": ["重建 coverage source units", "检查 unit 抽取规则", "调整 source unit 噪声过滤"],
        "retrieval_miss": ["补 metadata / synonym", "检查 query rewrite 和 expansion", "增加 retrieval_quality case"],
        "rerank_wrong": ["检查 rerank explanation", "调整 query_type/type bonus", "补 negative_expected 回归"],
        "graph_path_missing": ["检查 topic resolution entity", "修 graph relation 或 edge_evidence_map", "降低 weak relation 权重"],
        "graph_not_engaged": ["检查 topic_resolution 是否命中 ready entity", "检查 graph_edges 是否存在强关系", "补 process/entity alias 或 relation 构建规则"],
        "topic_resolution_wrong": ["检查 target_topic 与候选实体", "修 generic term 过滤和 alias 归一化", "补 topic_resolution 回归"],
        "entity_quality_pollution": ["清理低质量 entity/status", "修实体构建噪声过滤", "重建 wiki/graph/FTS 并补 entity hygiene 回归"],
        "stale_entity_exposed": ["检查检索 SQL 是否过滤 stale entity", "刷新 FTS/wiki 索引", "补 stale entity 暴露回归"],
        "evidence_judge_wrong": ["检查 matched/missing anchors", "增加 relation/evidence shape 规则", "补 judge 单测"],
        "evidence_shape_wrong": ["检查 expected_evidence_shape 与实际 evidence_shape", "修 evidence shape 适用条件或候选打分", "补 shape mismatch 回归"],
        "answer_policy_wrong": ["检查 answer_mode", "修 answer policy 选择", "增加 answer_quality case"],
        "answer_render_artifact": ["检查 answer_policy 渲染模板", "修通用答案清洗/去重规则", "补 render artifact 回归"],
        "llm_generation_wrong": ["收紧 LLM 输出约束", "增加 forbidden_contains", "优先规则模板修复"],
        "unknown_pytest_failure": ["查看 pytest output", "补结构化 eval result", "将失败 case 转为可归因结果"],
        "unknown": ["查看 eval output", "补 failure_reason", "补 Failure Analysis 归因规则"],
    }
    return mapping.get(failure_type, mapping["unknown"])


def _safe_json(value: object, fallback: object) -> object:
    if not isinstance(value, str) or not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _json_list(value: object) -> str:
    if value is None:
        items: list[object] = []
    elif isinstance(value, list):
        items = value
    elif isinstance(value, tuple):
        items = list(value)
    else:
        items = [value]
    return json.dumps([item for item in items if item is not None and item != ""], ensure_ascii=False)


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _as_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _clip(value: str, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[-limit:]
