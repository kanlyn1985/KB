from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from sqlite3 import Connection

from .closed_loop_store import utc_now
from .config import AppPaths
from .coverage import build_coverage_for_document
from .db import connect
from .derived_state import DerivedStateCheck, check_derived_state
from .graph import build_graph_for_document
from .retrieval import refresh_fts_index
from .wiki_compiler import build_wiki_for_document
from .workspace_doctor import WorkspaceDoctorReport, run_workspace_doctor


REBUILD_SCOPES = ("all", "fts", "graph", "wiki", "coverage")
REBUILD_MODES = ("reconcile", "full")
_STRUCTURAL_SCOPES = ("graph", "wiki", "coverage")
_FULL_REBUILD_SCOPES = ("wiki", "graph", "coverage")


@dataclass(frozen=True)
class DerivedStateRebuildItem:
    scope: str
    state_id: str
    action: str
    status: str
    dry_run: bool
    started_at: str
    finished_at: str
    before: dict[str, object]
    after: dict[str, object]
    changed_counts: dict[str, int]
    message: str
    recommended_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DerivedStateRebuildReport:
    scope: str
    dry_run: bool
    status: str
    started_at: str
    finished_at: str
    summary: dict[str, int]
    items: tuple[DerivedStateRebuildItem, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "dry_run": self.dry_run,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": self.summary,
            "items": [item.to_dict() for item in self.items],
        }


def rebuild_derived_state(
    workspace_root: Path,
    *,
    scope: str = "fts",
    dry_run: bool = False,
    mode: str = "reconcile",
    doc_id: str | None = None,
) -> DerivedStateRebuildReport:
    if scope not in REBUILD_SCOPES:
        raise ValueError(f"Unknown derived state rebuild scope: {scope}")
    if mode not in REBUILD_MODES:
        raise ValueError(f"Unknown derived state rebuild mode: {mode}")
    if doc_id and (mode != "full" or scope == "fts"):
        raise ValueError("--doc-id is only supported for graph/wiki/coverage/all full rebuild")

    started_at = utc_now()
    items: list[DerivedStateRebuildItem] = []
    if mode == "full":
        full_scopes = _FULL_REBUILD_SCOPES if scope == "all" else (scope,) if scope in _FULL_REBUILD_SCOPES else ()
        for full_scope in full_scopes:
            items.append(_full_rebuild_scope(workspace_root, full_scope, dry_run=dry_run, doc_id=doc_id))
    else:
        structural_scopes = _STRUCTURAL_SCOPES if scope == "all" else (scope,) if scope in _STRUCTURAL_SCOPES else ()
        for structural_scope in structural_scopes:
            items.append(_rebuild_structural_scope(workspace_root, structural_scope, dry_run=dry_run))
    if scope in {"all", "fts"}:
        items.append(_rebuild_fts(workspace_root, dry_run=dry_run))

    finished_at = utc_now()
    summary = _summary(items)
    status = "fail" if summary["failed"] else "warn" if summary["unsupported"] else "ok"
    return DerivedStateRebuildReport(
        scope=scope,
        dry_run=dry_run,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        summary=summary,
        items=tuple(items),
    )


def _full_rebuild_scope(
    workspace_root: Path,
    scope: str,
    *,
    dry_run: bool,
    doc_id: str | None,
) -> DerivedStateRebuildItem:
    started_at = utc_now()
    paths = AppPaths.from_root(workspace_root)
    before_report = run_workspace_doctor(workspace_root, scope=scope)
    before = _doctor_summary(before_report)
    if not paths.db_file.exists() or paths.db_file.stat().st_size == 0:
        finished_at = utc_now()
        return DerivedStateRebuildItem(
            scope=scope,
            state_id=scope,
            action="full_rebuild",
            status="failed",
            dry_run=dry_run,
            started_at=started_at,
            finished_at=finished_at,
            before=before,
            after=before,
            changed_counts={},
            message=f"{scope} full rebuild cannot run because the workspace database is missing or empty",
            recommended_actions=("init",),
        )

    target_doc_ids = _target_doc_ids(paths, doc_id=doc_id)
    if dry_run:
        connection = connect(paths.db_file)
        try:
            changed_counts = _full_rebuild_plan_counts(connection, scope, target_doc_ids)
        finally:
            connection.close()
        after_report = before_report
        status = "planned"
        message = f"{scope} derived artifacts would be fully rebuilt for {len(target_doc_ids)} document(s)"
        recommended_actions = (f"rebuild-derived-state --scope {scope} --mode full",)
    else:
        changed_counts, errors = _execute_full_rebuild(workspace_root, scope, target_doc_ids)
        after_report = run_workspace_doctor(workspace_root, scope=scope)
        doc_scoped_issues = _full_rebuild_doc_scoped_issues(paths, scope, target_doc_ids) if doc_id else {}
        status = "done" if not errors and not doc_scoped_issues and (doc_id or after_report.status == "ok") else "failed"
        message = (
            f"{scope} derived artifacts fully rebuilt for {len(target_doc_ids)} document(s)"
            if status == "done"
            else f"{scope} full rebuild finished with {len(errors)} error(s) or remaining doctor issues"
        )
        recommended_actions = () if status == "done" else (f"workspace-doctor --scope {scope} --json",)

    after = _doctor_summary(after_report)
    if not dry_run:
        after["target_doc_ids"] = list(target_doc_ids)
        if "errors" not in after:
            after["errors"] = errors
        if doc_id:
            after["doc_scoped_issues"] = doc_scoped_issues
    else:
        after["target_doc_ids"] = list(target_doc_ids)
    finished_at = utc_now()
    return DerivedStateRebuildItem(
        scope=scope,
        state_id=scope,
        action="full_rebuild",
        status=status,
        dry_run=dry_run,
        started_at=started_at,
        finished_at=finished_at,
        before=before,
        after=after,
        changed_counts=changed_counts,
        message=message,
        recommended_actions=recommended_actions,
    )


def _rebuild_fts(workspace_root: Path, *, dry_run: bool) -> DerivedStateRebuildItem:
    started_at = utc_now()
    before_checks = check_derived_state(workspace_root)
    before = _checks_summary(before_checks)
    changed_counts: dict[str, int] = {}
    if dry_run:
        status = "planned"
        after_checks = before_checks
        message = "FTS indexes would be refreshed"
        recommended_actions = ("rebuild-derived-state --scope fts",)
    else:
        changed_counts = refresh_fts_index(workspace_root)
        after_checks = check_derived_state(workspace_root)
        after_status = _aggregate_check_status(after_checks)
        status = "done" if after_status == "ok" else "failed"
        message = "FTS indexes refreshed" if status == "done" else "FTS rebuild finished but checks are not fresh"
        recommended_actions = () if status == "done" else ("workspace-doctor --scope fts --json",)
    finished_at = utc_now()
    return DerivedStateRebuildItem(
        scope="fts",
        state_id="fts",
        action="refresh",
        status=status,
        dry_run=dry_run,
        started_at=started_at,
        finished_at=finished_at,
        before=before,
        after=_checks_summary(after_checks),
        changed_counts=changed_counts,
        message=message,
        recommended_actions=recommended_actions,
    )


def _rebuild_structural_scope(
    workspace_root: Path,
    scope: str,
    *,
    dry_run: bool,
) -> DerivedStateRebuildItem:
    started_at = utc_now()
    paths = AppPaths.from_root(workspace_root)
    before_report = run_workspace_doctor(workspace_root, scope=scope)
    before = _doctor_summary(before_report)
    if not paths.db_file.exists() or paths.db_file.stat().st_size == 0:
        finished_at = utc_now()
        return DerivedStateRebuildItem(
            scope=scope,
            state_id=scope,
            action="reconcile_orphans",
            status="failed",
            dry_run=dry_run,
            started_at=started_at,
            finished_at=finished_at,
            before=before,
            after=before,
            changed_counts={},
            message=f"{scope} structural reconcile cannot run because the workspace database is missing or empty",
            recommended_actions=("init",),
        )

    if dry_run:
        connection = connect(paths.db_file)
        try:
            changed_counts = _structural_plan_counts(connection, scope)
        finally:
            connection.close()
        after_report = before_report
        status = "planned"
        message = f"{scope} orphan artifact rows would be reconciled"
        recommended_actions = (f"rebuild-derived-state --scope {scope}",)
    else:
        changed_counts = _execute_structural_reconcile(paths, scope)
        after_report = run_workspace_doctor(workspace_root, scope=scope)
        status = "done" if after_report.status == "ok" else "failed"
        message = (
            f"{scope} orphan artifact rows reconciled"
            if status == "done"
            else f"{scope} structural reconcile finished but doctor still reports issues"
        )
        recommended_actions = () if status == "done" else (f"workspace-doctor --scope {scope} --json",)

    finished_at = utc_now()
    return DerivedStateRebuildItem(
        scope=scope,
        state_id=scope,
        action="reconcile_orphans",
        status=status,
        dry_run=dry_run,
        started_at=started_at,
        finished_at=finished_at,
        before=before,
        after=_doctor_summary(after_report),
        changed_counts=changed_counts,
        message=message,
        recommended_actions=recommended_actions,
    )


def _checks_summary(checks: list[DerivedStateCheck]) -> dict[str, object]:
    return {
        "status": _aggregate_check_status(checks),
        "checks": [check.to_dict() for check in checks],
    }


def _aggregate_check_status(checks: list[DerivedStateCheck]) -> str:
    if any(check.severity == "fail" for check in checks):
        return "fail"
    if any(check.severity == "warn" for check in checks):
        return "warn"
    return "ok"


def _summary(items: list[DerivedStateRebuildItem]) -> dict[str, int]:
    summary = {"done": 0, "planned": 0, "unsupported": 0, "failed": 0}
    for item in items:
        if item.status in summary:
            summary[item.status] += 1
    return summary


def _doctor_summary(report: WorkspaceDoctorReport) -> dict[str, object]:
    return {
        "status": report.status,
        "summary": report.summary,
        "issue_ids": [issue.issue_id for issue in report.issues],
        "issues": [issue.to_dict() for issue in report.issues],
    }


def _structural_plan_counts(connection: Connection, scope: str) -> dict[str, int]:
    if scope == "graph":
        return {
            "graph_edges": _count_sql(connection, _GRAPH_ORPHAN_EDGE_SQL),
            "edge_evidence_map": _count_sql(connection, _GRAPH_ORPHAN_EDGE_EVIDENCE_SQL),
        }
    if scope == "wiki":
        return {"wiki_pages": len(_invalid_wiki_page_ids(connection))}
    if scope == "coverage":
        return {
            "source_unit_fact_map": _count_sql(connection, _COVERAGE_ORPHAN_FACT_MAP_SQL),
            "source_unit_evidence_map": _count_sql(connection, _COVERAGE_ORPHAN_EVIDENCE_MAP_SQL),
        }
    raise ValueError(f"Unsupported structural rebuild scope: {scope}")


def _execute_structural_reconcile(paths: AppPaths, scope: str) -> dict[str, int]:
    connection = connect(paths.db_file)
    try:
        if scope == "graph":
            changed_counts = _execute_graph_reconcile(connection)
        elif scope == "wiki":
            changed_counts = _execute_wiki_reconcile(connection)
        elif scope == "coverage":
            changed_counts = _execute_coverage_reconcile(connection)
        else:
            raise ValueError(f"Unsupported structural rebuild scope: {scope}")
        connection.commit()
        return changed_counts
    finally:
        connection.close()


def _target_doc_ids(paths: AppPaths, *, doc_id: str | None) -> tuple[str, ...]:
    connection = connect(paths.db_file)
    try:
        if doc_id:
            row = connection.execute(
                "SELECT doc_id FROM documents WHERE doc_id = ? AND is_active = 1",
                (doc_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"active document not found: {doc_id}")
            return (str(row["doc_id"]),)
        rows = connection.execute(
            """
            SELECT doc_id
            FROM documents
            WHERE is_active = 1
            ORDER BY doc_id
            """
        ).fetchall()
        return tuple(str(row["doc_id"]) for row in rows)
    finally:
        connection.close()


def _full_rebuild_plan_counts(
    connection: Connection,
    scope: str,
    doc_ids: tuple[str, ...],
) -> dict[str, int]:
    counts = {"documents": len(doc_ids)}
    if scope == "graph":
        counts["graph_edges"] = _count_doc_graph_edges(connection, doc_ids)
        counts["edge_evidence_map"] = _count_doc_edge_evidence_links(connection, doc_ids)
        return counts
    if scope == "wiki":
        counts["wiki_pages"] = _count_doc_wiki_pages(connection, doc_ids)
        return counts
    if scope == "coverage":
        counts["source_units"] = _count_doc_rows(connection, "source_units", doc_ids)
        counts["source_unit_fact_map"] = _count_doc_rows(connection, "source_unit_fact_map", doc_ids)
        counts["source_unit_evidence_map"] = _count_doc_rows(connection, "source_unit_evidence_map", doc_ids)
        return counts
    raise ValueError(f"Unsupported full rebuild scope: {scope}")


def _execute_full_rebuild(
    workspace_root: Path,
    scope: str,
    doc_ids: tuple[str, ...],
) -> tuple[dict[str, int], list[str]]:
    changed_counts = {"documents": len(doc_ids)}
    errors: list[str] = []
    if scope == "graph":
        changed_counts.update({"graph_edges": 0})
    elif scope == "wiki":
        changed_counts.update({"wiki_pages": 0})
    elif scope == "coverage":
        changed_counts.update({"source_units": 0})
    else:
        raise ValueError(f"Unsupported full rebuild scope: {scope}")

    for current_doc_id in doc_ids:
        try:
            if scope == "wiki":
                result = build_wiki_for_document(workspace_root, current_doc_id)
                changed_counts["wiki_pages"] += int(result.page_count)
            elif scope == "graph":
                result = build_graph_for_document(workspace_root, current_doc_id)
                changed_counts["graph_edges"] += int(result.edge_count)
            elif scope == "coverage":
                result = build_coverage_for_document(workspace_root, current_doc_id)
                changed_counts["source_units"] += int(result.source_unit_count)
        except Exception as exc:  # pragma: no cover - exercised by integration failures.
            errors.append(f"{current_doc_id}: {exc}")
    return changed_counts, errors


def _full_rebuild_doc_scoped_issues(
    paths: AppPaths,
    scope: str,
    doc_ids: tuple[str, ...],
) -> dict[str, int]:
    connection = connect(paths.db_file)
    try:
        if scope == "wiki":
            issue_count = len(_invalid_wiki_page_ids_for_docs(connection, doc_ids))
            return {"wiki_pages": issue_count} if issue_count else {}
        if scope == "graph":
            issues = {
                "graph_edges": _count_doc_graph_edge_issues(connection, doc_ids),
                "edge_evidence_map": _count_doc_edge_evidence_issues(connection, doc_ids),
            }
            return {key: value for key, value in issues.items() if value}
        if scope == "coverage":
            issues = {
                "source_unit_fact_map": _count_doc_coverage_fact_issues(connection, doc_ids),
                "source_unit_evidence_map": _count_doc_coverage_evidence_issues(connection, doc_ids),
            }
            return {key: value for key, value in issues.items() if value}
        raise ValueError(f"Unsupported full rebuild scope: {scope}")
    finally:
        connection.close()


def _invalid_wiki_page_ids_for_docs(connection: Connection, doc_ids: tuple[str, ...]) -> tuple[str, ...]:
    if not doc_ids:
        return ()
    target_doc_ids = set(doc_ids)
    invalid_all = set(_invalid_wiki_page_ids(connection))
    if not invalid_all:
        return ()
    rows = connection.execute(
        """
        SELECT page_id, source_doc_ids_json
        FROM wiki_pages
        ORDER BY page_id
        """
    ).fetchall()
    scoped: list[str] = []
    for row in rows:
        page_id = str(row["page_id"])
        if page_id not in invalid_all:
            continue
        page_doc_ids, valid = _json_text_list(row["source_doc_ids_json"])
        if valid and target_doc_ids.intersection(page_doc_ids):
            scoped.append(page_id)
    return tuple(scoped)


def _count_doc_graph_edge_issues(connection: Connection, doc_ids: tuple[str, ...]) -> int:
    if not doc_ids:
        return 0
    placeholders = ",".join("?" for _ in doc_ids)
    return int(
        connection.execute(
            f"""
            SELECT count(*)
            FROM graph_edges g
            LEFT JOIN entities src ON src.entity_id = g.src_entity_id
            LEFT JOIN entities dst ON dst.entity_id = g.dst_entity_id
            WHERE g.version_scope IN ({placeholders})
              AND (src.entity_id IS NULL OR dst.entity_id IS NULL)
            """,
            doc_ids,
        ).fetchone()[0]
    )


def _count_doc_edge_evidence_issues(connection: Connection, doc_ids: tuple[str, ...]) -> int:
    if not doc_ids:
        return 0
    placeholders = ",".join("?" for _ in doc_ids)
    return int(
        connection.execute(
            f"""
            SELECT count(*)
            FROM edge_evidence_map m
            JOIN graph_edges g ON g.edge_id = m.edge_id
            LEFT JOIN evidence e ON e.evidence_id = m.evidence_id
            WHERE g.version_scope IN ({placeholders})
              AND e.evidence_id IS NULL
            """,
            doc_ids,
        ).fetchone()[0]
    )


def _count_doc_coverage_fact_issues(connection: Connection, doc_ids: tuple[str, ...]) -> int:
    if not doc_ids:
        return 0
    placeholders = ",".join("?" for _ in doc_ids)
    return int(
        connection.execute(
            f"""
            SELECT count(*)
            FROM source_unit_fact_map m
            LEFT JOIN source_units su ON su.unit_id = m.unit_id
            LEFT JOIN facts f ON f.fact_id = m.fact_id
            WHERE m.doc_id IN ({placeholders})
              AND (su.unit_id IS NULL OR f.fact_id IS NULL)
            """,
            doc_ids,
        ).fetchone()[0]
    )


def _count_doc_coverage_evidence_issues(connection: Connection, doc_ids: tuple[str, ...]) -> int:
    if not doc_ids:
        return 0
    placeholders = ",".join("?" for _ in doc_ids)
    return int(
        connection.execute(
            f"""
            SELECT count(*)
            FROM source_unit_evidence_map m
            LEFT JOIN source_units su ON su.unit_id = m.unit_id
            LEFT JOIN evidence e ON e.evidence_id = m.evidence_id
            WHERE m.doc_id IN ({placeholders})
              AND (su.unit_id IS NULL OR e.evidence_id IS NULL)
            """,
            doc_ids,
        ).fetchone()[0]
    )


def _count_doc_graph_edges(connection: Connection, doc_ids: tuple[str, ...]) -> int:
    if not doc_ids:
        return 0
    placeholders = ",".join("?" for _ in doc_ids)
    return int(
        connection.execute(
            f"SELECT count(*) FROM graph_edges WHERE version_scope IN ({placeholders})",
            doc_ids,
        ).fetchone()[0]
    )


def _count_doc_edge_evidence_links(connection: Connection, doc_ids: tuple[str, ...]) -> int:
    if not doc_ids:
        return 0
    placeholders = ",".join("?" for _ in doc_ids)
    return int(
        connection.execute(
            f"""
            SELECT count(*)
            FROM edge_evidence_map m
            JOIN graph_edges g ON g.edge_id = m.edge_id
            WHERE g.version_scope IN ({placeholders})
            """,
            doc_ids,
        ).fetchone()[0]
    )


def _count_doc_wiki_pages(connection: Connection, doc_ids: tuple[str, ...]) -> int:
    total = 0
    for doc_id in doc_ids:
        total += int(
            connection.execute(
                """
                SELECT count(*)
                FROM wiki_pages
                WHERE source_doc_ids_json LIKE ?
                """,
                (f'%"{doc_id}"%',),
            ).fetchone()[0]
        )
    return total


def _count_doc_rows(connection: Connection, table_name: str, doc_ids: tuple[str, ...]) -> int:
    if not doc_ids:
        return 0
    placeholders = ",".join("?" for _ in doc_ids)
    return int(
        connection.execute(
            f"SELECT count(*) FROM {table_name} WHERE doc_id IN ({placeholders})",
            doc_ids,
        ).fetchone()[0]
    )


def _execute_graph_reconcile(connection: Connection) -> dict[str, int]:
    deleted_edges = _delete_sql(connection, _GRAPH_ORPHAN_EDGE_DELETE_SQL)
    deleted_edge_evidence = _delete_sql(connection, _GRAPH_ORPHAN_EDGE_EVIDENCE_DELETE_SQL)
    return {
        "graph_edges": deleted_edges,
        "edge_evidence_map": deleted_edge_evidence,
    }


def _execute_wiki_reconcile(connection: Connection) -> dict[str, int]:
    page_ids = _invalid_wiki_page_ids(connection)
    if not page_ids:
        return {"wiki_pages": 0}
    placeholders = ",".join("?" for _ in page_ids)
    cursor = connection.execute(
        f"DELETE FROM wiki_pages WHERE page_id IN ({placeholders})",
        page_ids,
    )
    return {"wiki_pages": max(int(cursor.rowcount or 0), 0)}


def _execute_coverage_reconcile(connection: Connection) -> dict[str, int]:
    deleted_fact_links = _delete_sql(connection, _COVERAGE_ORPHAN_FACT_MAP_DELETE_SQL)
    deleted_evidence_links = _delete_sql(connection, _COVERAGE_ORPHAN_EVIDENCE_MAP_DELETE_SQL)
    return {
        "source_unit_fact_map": deleted_fact_links,
        "source_unit_evidence_map": deleted_evidence_links,
    }


def _invalid_wiki_page_ids(connection: Connection) -> tuple[str, ...]:
    entity_ids = _id_set(connection, "entities", "entity_id")
    fact_ids = _id_set(connection, "facts", "fact_id")
    doc_ids = _id_set(connection, "documents", "doc_id")
    rows = connection.execute(
        """
        SELECT page_id, entity_id, source_fact_ids_json, source_doc_ids_json
        FROM wiki_pages
        ORDER BY page_id
        """
    ).fetchall()
    invalid: list[str] = []
    for row in rows:
        page_id = str(row["page_id"])
        entity_id = row["entity_id"]
        if entity_id is not None and str(entity_id) not in entity_ids:
            invalid.append(page_id)
            continue
        source_fact_ids, fact_json_valid = _json_text_list(row["source_fact_ids_json"])
        source_doc_ids, doc_json_valid = _json_text_list(row["source_doc_ids_json"])
        if not fact_json_valid or not doc_json_valid:
            invalid.append(page_id)
            continue
        if any(fact_id not in fact_ids for fact_id in source_fact_ids):
            invalid.append(page_id)
            continue
        if any(doc_id not in doc_ids for doc_id in source_doc_ids):
            invalid.append(page_id)
    return tuple(invalid)


def _id_set(connection: Connection, table_name: str, column_name: str) -> set[str]:
    rows = connection.execute(f"SELECT {column_name} FROM {table_name}").fetchall()
    return {str(row[column_name]) for row in rows if row[column_name] is not None}


def _json_text_list(value: object) -> tuple[tuple[str, ...], bool]:
    if value is None:
        return (), True
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return (), False
    if not isinstance(parsed, list):
        return (), False
    return tuple(str(item) for item in parsed if item is not None), True


def _count_sql(connection: Connection, sql: str) -> int:
    return int(connection.execute(sql).fetchone()[0])


def _delete_sql(connection: Connection, sql: str) -> int:
    cursor = connection.execute(sql)
    return max(int(cursor.rowcount or 0), 0)


_GRAPH_ORPHAN_EDGE_SQL = """
    SELECT count(*)
    FROM graph_edges g
    LEFT JOIN entities src ON src.entity_id = g.src_entity_id
    LEFT JOIN entities dst ON dst.entity_id = g.dst_entity_id
    WHERE src.entity_id IS NULL OR dst.entity_id IS NULL
"""

_GRAPH_ORPHAN_EDGE_EVIDENCE_SQL = """
    SELECT count(*)
    FROM edge_evidence_map m
    LEFT JOIN graph_edges g ON g.edge_id = m.edge_id
    LEFT JOIN evidence e ON e.evidence_id = m.evidence_id
    LEFT JOIN entities src ON src.entity_id = g.src_entity_id
    LEFT JOIN entities dst ON dst.entity_id = g.dst_entity_id
    WHERE g.edge_id IS NULL
       OR e.evidence_id IS NULL
       OR src.entity_id IS NULL
       OR dst.entity_id IS NULL
"""

_GRAPH_ORPHAN_EDGE_DELETE_SQL = """
    DELETE FROM graph_edges
    WHERE NOT EXISTS (
        SELECT 1 FROM entities src WHERE src.entity_id = graph_edges.src_entity_id
    )
       OR NOT EXISTS (
        SELECT 1 FROM entities dst WHERE dst.entity_id = graph_edges.dst_entity_id
    )
"""

_GRAPH_ORPHAN_EDGE_EVIDENCE_DELETE_SQL = """
    DELETE FROM edge_evidence_map
    WHERE NOT EXISTS (
        SELECT 1 FROM graph_edges g WHERE g.edge_id = edge_evidence_map.edge_id
    )
       OR NOT EXISTS (
        SELECT 1 FROM evidence e WHERE e.evidence_id = edge_evidence_map.evidence_id
    )
"""

_COVERAGE_ORPHAN_FACT_MAP_SQL = """
    SELECT count(*)
    FROM source_unit_fact_map m
    LEFT JOIN source_units su ON su.unit_id = m.unit_id
    LEFT JOIN facts f ON f.fact_id = m.fact_id
    WHERE su.unit_id IS NULL OR f.fact_id IS NULL
"""

_COVERAGE_ORPHAN_EVIDENCE_MAP_SQL = """
    SELECT count(*)
    FROM source_unit_evidence_map m
    LEFT JOIN source_units su ON su.unit_id = m.unit_id
    LEFT JOIN evidence e ON e.evidence_id = m.evidence_id
    WHERE su.unit_id IS NULL OR e.evidence_id IS NULL
"""

_COVERAGE_ORPHAN_FACT_MAP_DELETE_SQL = """
    DELETE FROM source_unit_fact_map
    WHERE NOT EXISTS (
        SELECT 1 FROM source_units su WHERE su.unit_id = source_unit_fact_map.unit_id
    )
       OR NOT EXISTS (
        SELECT 1 FROM facts f WHERE f.fact_id = source_unit_fact_map.fact_id
    )
"""

_COVERAGE_ORPHAN_EVIDENCE_MAP_DELETE_SQL = """
    DELETE FROM source_unit_evidence_map
    WHERE NOT EXISTS (
        SELECT 1 FROM source_units su WHERE su.unit_id = source_unit_evidence_map.unit_id
    )
       OR NOT EXISTS (
        SELECT 1 FROM evidence e WHERE e.evidence_id = source_unit_evidence_map.evidence_id
    )
"""
