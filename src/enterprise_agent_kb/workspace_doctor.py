from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from sqlite3 import Connection
from typing import Iterable

from .closed_loop_store import _runtime_code_version, utc_now
from .config import AppPaths
from .corpus_eval import analyze_source_unit_candidate_quality
from .db import connect
from .derived_state import DerivedStateCheck, check_derived_state


DOCTOR_SCOPES = ("all", "fts", "graph", "wiki", "coverage", "runs")


@dataclass(frozen=True)
class WorkspaceDoctorIssue:
    issue_id: str
    scope: str
    severity: str
    message: str
    details: dict[str, object]
    recommended_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceDoctorReport:
    scope: str
    status: str
    workspace_root: str
    database_path: str
    generated_at: str
    current_code_version: str
    summary: dict[str, int]
    derived_state_checks: tuple[DerivedStateCheck, ...]
    issues: tuple[WorkspaceDoctorIssue, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "status": self.status,
            "workspace_root": self.workspace_root,
            "database_path": self.database_path,
            "generated_at": self.generated_at,
            "current_code_version": self.current_code_version,
            "summary": self.summary,
            "derived_state_checks": [check.to_dict() for check in self.derived_state_checks],
            "issues": [issue.to_dict() for issue in self.issues],
        }


def run_workspace_doctor(workspace_root: Path, *, scope: str = "all") -> WorkspaceDoctorReport:
    if scope not in DOCTOR_SCOPES:
        raise ValueError(f"Unknown workspace doctor scope: {scope}")

    paths = AppPaths.from_root(workspace_root)
    issues: list[WorkspaceDoctorIssue] = []
    derived_checks: list[DerivedStateCheck] = []

    issues.extend(_database_issues(paths, include_extra_files=scope == "all"))

    if not paths.db_file.exists() or paths.db_file.stat().st_size == 0:
        return _build_report(paths, scope, derived_checks, issues)

    connection = connect(paths.db_file)
    try:
        if _includes(scope, "fts"):
            derived_checks.extend(check_derived_state(paths.root, connection=connection))
            issues.extend(_issues_from_derived_state(derived_checks))
        if _includes(scope, "graph"):
            issues.extend(_graph_issues(connection))
        if _includes(scope, "wiki"):
            issues.extend(_wiki_issues(connection))
        if _includes(scope, "coverage"):
            issues.extend(_coverage_issues(connection))
        if _includes(scope, "runs"):
            issues.extend(_run_issues(connection))
    finally:
        connection.close()

    return _build_report(paths, scope, derived_checks, issues)


def format_workspace_doctor_report(report: WorkspaceDoctorReport) -> str:
    lines = [
        f"Workspace doctor: {report.status}",
        f"Scope: {report.scope}",
        f"Root: {report.workspace_root}",
        f"Database: {report.database_path}",
        (
            "Summary: "
            f"ok={report.summary.get('ok', 0)}, "
            f"warn={report.summary.get('warn', 0)}, "
            f"fail={report.summary.get('fail', 0)}"
        ),
    ]
    if report.derived_state_checks:
        lines.append("")
        lines.append("Derived state:")
        for check in report.derived_state_checks:
            lines.append(
                f"- [{check.severity.upper()}] {check.state_id}: {check.status} "
                f"(source={check.source_count}, artifact={check.artifact_count}, "
                f"missing={check.missing_count}, orphan={check.orphan_count})"
            )
    if report.issues:
        lines.append("")
        lines.append("Issues:")
        for issue in report.issues:
            actions = ", ".join(issue.recommended_actions) if issue.recommended_actions else "none"
            lines.append(f"- [{issue.severity.upper()}] {issue.scope}/{issue.issue_id}: {issue.message}")
            lines.append(f"  action: {actions}")
    else:
        lines.append("")
        lines.append("No issues found.")
    return "\n".join(lines)


def _includes(scope: str, target: str) -> bool:
    return scope == "all" or scope == target


def _build_report(
    paths: AppPaths,
    scope: str,
    derived_checks: list[DerivedStateCheck],
    issues: list[WorkspaceDoctorIssue],
) -> WorkspaceDoctorReport:
    summary = _summary(derived_checks, issues)
    status = "fail" if summary["fail"] else "warn" if summary["warn"] else "ok"
    return WorkspaceDoctorReport(
        scope=scope,
        status=status,
        workspace_root=str(paths.root),
        database_path=str(paths.db_file),
        generated_at=utc_now(),
        current_code_version=_runtime_code_version(),
        summary=summary,
        derived_state_checks=tuple(derived_checks),
        issues=tuple(issues),
    )


def _summary(
    derived_checks: Iterable[DerivedStateCheck],
    issues: Iterable[WorkspaceDoctorIssue],
) -> dict[str, int]:
    summary = {"ok": 0, "warn": 0, "fail": 0}
    for check in derived_checks:
        if check.severity in summary:
            summary[check.severity] += 1
    for issue in issues:
        if issue.severity in summary:
            summary[issue.severity] += 1
    return summary


def _database_issues(paths: AppPaths, *, include_extra_files: bool) -> list[WorkspaceDoctorIssue]:
    issues: list[WorkspaceDoctorIssue] = []
    if not paths.root.exists():
        issues.append(
            WorkspaceDoctorIssue(
                issue_id="workspace_root_missing",
                scope="database",
                severity="fail",
                message="workspace root directory does not exist",
                details={"workspace_root": str(paths.root)},
                recommended_actions=("init",),
            )
        )
        return issues
    if not paths.db_file.exists():
        issues.append(
            WorkspaceDoctorIssue(
                issue_id="workspace_database_missing",
                scope="database",
                severity="fail",
                message="workspace database does not exist",
                details={"database_path": str(paths.db_file)},
                recommended_actions=("init",),
            )
        )
    elif paths.db_file.stat().st_size == 0:
        issues.append(
            WorkspaceDoctorIssue(
                issue_id="workspace_database_empty",
                scope="database",
                severity="fail",
                message="workspace database file is empty",
                details={"database_path": str(paths.db_file)},
                recommended_actions=("init",),
            )
        )
    workspace_db = paths.db_file.resolve()
    if include_extra_files:
        for db_file in _candidate_db_files(paths):
            if db_file == workspace_db:
                continue
            issue = _suspicious_db_issue(paths, db_file)
            if issue is not None:
                issues.append(issue)
    return issues


def _candidate_db_files(paths: AppPaths) -> tuple[Path, ...]:
    if not paths.root.exists():
        return ()
    candidates = {path.resolve() for path in paths.root.glob("*.db")}
    if paths.db_dir.exists():
        candidates.update(path.resolve() for path in paths.db_dir.glob("*.db"))
    return tuple(sorted(candidates))


def _suspicious_db_issue(paths: AppPaths, db_file: Path) -> WorkspaceDoctorIssue | None:
    relative_path = str(_relative_to_root(paths.root, db_file))
    if db_file.stat().st_size == 0:
        return WorkspaceDoctorIssue(
            issue_id="empty_db_file",
            scope="database",
            severity="warn",
            message="workspace contains an extra empty database file",
            details={"path": relative_path},
            recommended_actions=("quarantine-suspicious-db-files --dry-run",),
        )
    try:
        connection = sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True)
        try:
            table_count = connection.execute(
                """
                SELECT count(*)
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            ).fetchone()[0]
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        return WorkspaceDoctorIssue(
            issue_id="unreadable_db_file",
            scope="database",
            severity="warn",
            message="workspace contains an unreadable database file",
            details={"path": relative_path},
            recommended_actions=("quarantine-suspicious-db-files --dry-run",),
        )
    if int(table_count) == 0:
        return WorkspaceDoctorIssue(
            issue_id="empty_schema_db_file",
            scope="database",
            severity="warn",
            message="workspace contains an extra database file with no user tables",
            details={"path": relative_path},
            recommended_actions=("quarantine-suspicious-db-files --dry-run",),
        )
    return None


def _relative_to_root(root: Path, path: Path) -> Path:
    try:
        return path.relative_to(root.resolve())
    except ValueError:
        return path


def _issues_from_derived_state(checks: Iterable[DerivedStateCheck]) -> list[WorkspaceDoctorIssue]:
    issues: list[WorkspaceDoctorIssue] = []
    for check in checks:
        if check.status == "fresh":
            continue
        issues.append(
            WorkspaceDoctorIssue(
                issue_id=f"derived_state_{check.state_id}_{check.status}",
                scope="fts",
                severity=check.severity,
                message=check.message,
                details={
                    "state_id": check.state_id,
                    "source_count": check.source_count,
                    "artifact_count": check.artifact_count,
                    "missing_count": check.missing_count,
                    "orphan_count": check.orphan_count,
                    "source_version": check.source_version,
                    "artifact_version": check.artifact_version,
                },
                recommended_actions=check.recommended_actions,
            )
        )
    return issues


def _graph_issues(connection: Connection) -> list[WorkspaceDoctorIssue]:
    issues: list[WorkspaceDoctorIssue] = []
    issues.extend(
        _sql_count_issue(
            connection,
            scope="graph",
            issue_id="graph_missing_src_entity",
            message="graph_edges contains src_entity_id values missing from entities",
            sql="""
                SELECT count(*)
                FROM graph_edges g
                LEFT JOIN entities e ON e.entity_id = g.src_entity_id
                WHERE e.entity_id IS NULL
            """,
            action="rebuild-derived-state --scope graph",
        )
    )
    issues.extend(
        _sql_count_issue(
            connection,
            scope="graph",
            issue_id="graph_missing_dst_entity",
            message="graph_edges contains dst_entity_id values missing from entities",
            sql="""
                SELECT count(*)
                FROM graph_edges g
                LEFT JOIN entities e ON e.entity_id = g.dst_entity_id
                WHERE e.entity_id IS NULL
            """,
            action="rebuild-derived-state --scope graph",
        )
    )
    issues.extend(
        _sql_count_issue(
            connection,
            scope="graph",
            issue_id="edge_evidence_missing_edge",
            message="edge_evidence_map contains edge_id values missing from graph_edges",
            sql="""
                SELECT count(*)
                FROM edge_evidence_map m
                LEFT JOIN graph_edges g ON g.edge_id = m.edge_id
                WHERE g.edge_id IS NULL
            """,
            action="rebuild-derived-state --scope graph",
        )
    )
    issues.extend(
        _sql_count_issue(
            connection,
            scope="graph",
            issue_id="edge_evidence_missing_evidence",
            message="edge_evidence_map contains evidence_id values missing from evidence",
            sql="""
                SELECT count(*)
                FROM edge_evidence_map m
                LEFT JOIN evidence e ON e.evidence_id = m.evidence_id
                WHERE e.evidence_id IS NULL
            """,
            action="rebuild-derived-state --scope graph",
        )
    )
    return issues


def _wiki_issues(connection: Connection) -> list[WorkspaceDoctorIssue]:
    issues: list[WorkspaceDoctorIssue] = []
    issues.extend(
        _sql_count_issue(
            connection,
            scope="wiki",
            issue_id="wiki_missing_entity",
            message="wiki_pages contains entity_id values missing from entities",
            sql="""
                SELECT count(*)
                FROM wiki_pages w
                LEFT JOIN entities e ON e.entity_id = w.entity_id
                WHERE w.entity_id IS NOT NULL AND e.entity_id IS NULL
            """,
            action="rebuild-derived-state --scope wiki",
        )
    )
    existing_facts = _id_set(connection, "facts", "fact_id")
    existing_docs = _id_set(connection, "documents", "doc_id")
    rows = connection.execute(
        """
        SELECT page_id, source_fact_ids_json, source_doc_ids_json
        FROM wiki_pages
        """
    ).fetchall()
    missing_facts = 0
    missing_docs = 0
    invalid_json = 0
    for row in rows:
        fact_ids, fact_json_valid = _json_text_list(row["source_fact_ids_json"])
        doc_ids, doc_json_valid = _json_text_list(row["source_doc_ids_json"])
        if not fact_json_valid or not doc_json_valid:
            invalid_json += 1
        missing_facts += sum(1 for fact_id in fact_ids if fact_id not in existing_facts)
        missing_docs += sum(1 for doc_id in doc_ids if doc_id not in existing_docs)
    if missing_facts:
        issues.append(
            WorkspaceDoctorIssue(
                issue_id="wiki_missing_source_fact",
                scope="wiki",
                severity="warn",
                message="wiki source_fact_ids_json contains fact ids missing from facts",
                details={"missing_count": missing_facts},
                recommended_actions=("rebuild-derived-state --scope wiki",),
            )
        )
    if missing_docs:
        issues.append(
            WorkspaceDoctorIssue(
                issue_id="wiki_missing_source_doc",
                scope="wiki",
                severity="warn",
                message="wiki source_doc_ids_json contains doc ids missing from documents",
                details={"missing_count": missing_docs},
                recommended_actions=("rebuild-derived-state --scope wiki",),
            )
        )
    if invalid_json:
        issues.append(
            WorkspaceDoctorIssue(
                issue_id="wiki_invalid_source_json",
                scope="wiki",
                severity="warn",
                message="wiki_pages contains invalid source id JSON",
                details={"page_count": invalid_json},
                recommended_actions=("rebuild-derived-state --scope wiki",),
            )
        )
    return issues


def _coverage_issues(connection: Connection) -> list[WorkspaceDoctorIssue]:
    """Detect workspace coverage issues: documents that should have a
    source-unit matrix but lack one, and any other coverage gaps visible
    from the DB state.
    """
    issues: list[WorkspaceDoctorIssue] = []
    missing_source_unit_docs = [
        dict(row)
        for row in connection.execute(
            """
            WITH page_counts AS (
                SELECT doc_id, count(*) AS page_count
                FROM pages
                GROUP BY doc_id
            ),
            evidence_counts AS (
                SELECT doc_id, count(*) AS evidence_count
                FROM evidence
                GROUP BY doc_id
            ),
            fact_counts AS (
                SELECT source_doc_id AS doc_id, count(*) AS fact_count
                FROM facts
                GROUP BY source_doc_id
            ),
            source_unit_counts AS (
                SELECT doc_id, count(*) AS source_unit_count
                FROM source_units
                GROUP BY doc_id
            )
            SELECT
                d.doc_id,
                d.source_filename,
                d.parse_status,
                coalesce(pc.page_count, 0) AS page_count,
                coalesce(ec.evidence_count, 0) AS evidence_count,
                coalesce(fc.fact_count, 0) AS fact_count,
                coalesce(suc.source_unit_count, 0) AS source_unit_count
            FROM documents d
            LEFT JOIN page_counts pc ON pc.doc_id = d.doc_id
            LEFT JOIN evidence_counts ec ON ec.doc_id = d.doc_id
            LEFT JOIN fact_counts fc ON fc.doc_id = d.doc_id
            LEFT JOIN source_unit_counts suc ON suc.doc_id = d.doc_id
            WHERE coalesce(d.parse_status, '') = 'parsed'
              AND coalesce(pc.page_count, 0) > 0
              AND coalesce(ec.evidence_count, 0) > 0
              AND coalesce(fc.fact_count, 0) > 0
              AND coalesce(suc.source_unit_count, 0) = 0
            ORDER BY d.doc_id
            """
        ).fetchall()
    ]
    if missing_source_unit_docs:
        issues.append(
            WorkspaceDoctorIssue(
                issue_id="document_source_units_missing",
                scope="coverage",
                severity="fail",
                message="parsed documents have pages/evidence/facts but no source_units",
                details={
                    "doc_count": len(missing_source_unit_docs),
                    "documents": missing_source_unit_docs[:20],
                    "documents_truncated": len(missing_source_unit_docs) > 20,
                },
                recommended_actions=(
                    "rebuild-derived-state --scope coverage --mode full --doc-id <doc_id>",
                    "rerun document pipeline only after staging/rollback protection is enabled",
                ),
            )
        )
    issues.extend(
        _sql_count_issue(
            connection,
            scope="coverage",
            issue_id="source_unit_fact_missing_unit",
            message="source_unit_fact_map contains unit_id values missing from source_units",
            sql="""
                SELECT count(*)
                FROM source_unit_fact_map m
                LEFT JOIN source_units su ON su.unit_id = m.unit_id
                WHERE su.unit_id IS NULL
            """,
            action="rebuild-derived-state --scope coverage",
        )
    )
    issues.extend(
        _sql_count_issue(
            connection,
            scope="coverage",
            issue_id="source_unit_fact_missing_fact",
            message="source_unit_fact_map contains fact_id values missing from facts",
            sql="""
                SELECT count(*)
                FROM source_unit_fact_map m
                LEFT JOIN facts f ON f.fact_id = m.fact_id
                WHERE f.fact_id IS NULL
            """,
            action="rebuild-derived-state --scope coverage",
        )
    )
    issues.extend(
        _sql_count_issue(
            connection,
            scope="coverage",
            issue_id="source_unit_evidence_missing_unit",
            message="source_unit_evidence_map contains unit_id values missing from source_units",
            sql="""
                SELECT count(*)
                FROM source_unit_evidence_map m
                LEFT JOIN source_units su ON su.unit_id = m.unit_id
                WHERE su.unit_id IS NULL
            """,
            action="rebuild-derived-state --scope coverage",
        )
    )
    issues.extend(
        _sql_count_issue(
            connection,
            scope="coverage",
            issue_id="source_unit_evidence_missing_evidence",
            message="source_unit_evidence_map contains evidence_id values missing from evidence",
            sql="""
                SELECT count(*)
                FROM source_unit_evidence_map m
                LEFT JOIN evidence e ON e.evidence_id = m.evidence_id
                WHERE e.evidence_id IS NULL
            """,
            action="rebuild-derived-state --scope coverage",
        )
    )
    quality = analyze_source_unit_candidate_quality(_database_path(connection))
    weak_count = int(quality.get("reason_counts", {}).get("weak_definition_shape", 0)) if isinstance(quality.get("reason_counts"), dict) else 0
    if weak_count:
        issues.append(
            WorkspaceDoctorIssue(
                issue_id="source_unit_weak_definition_shape",
                scope="coverage",
                severity="warn",
                message="source_units contains definition units that lack a verifiable definition evidence shape",
                details={
                    "unit_count": weak_count,
                    "quality_summary": quality,
                },
                recommended_actions=(
                    "inspect source_units where reason=weak_definition_shape",
                    "fix source-unit extraction or rebuild coverage from corrected units",
                ),
            )
        )
    return issues


def _run_issues(connection: Connection) -> list[WorkspaceDoctorIssue]:
    issues: list[WorkspaceDoctorIssue] = []
    current = _runtime_code_version()
    for table_name, id_column in (("retrieval_runs", "run_id"), ("eval_runs", "eval_run_id")):
        if not _column_exists(connection, table_name, "code_version"):
            issues.append(
                WorkspaceDoctorIssue(
                    issue_id=f"{table_name}_missing_code_version_column",
                    scope="runs",
                    severity="warn",
                    message=f"{table_name} has no code_version column",
                    details={"table": table_name},
                    recommended_actions=("apply-schema-migration",),
                )
            )
            continue
        unknown_count = connection.execute(
            f"""
            SELECT count(*)
            FROM {table_name}
            WHERE code_version IS NULL OR code_version = ''
            """
        ).fetchone()[0]
        stale_count = connection.execute(
            f"""
            SELECT count(*)
            FROM {table_name}
            WHERE code_version IS NOT NULL
              AND code_version != ''
              AND code_version != ?
            """,
            (current,),
        ).fetchone()[0]
        current_count = connection.execute(
            f"""
            SELECT count(*)
            FROM {table_name}
            WHERE code_version = ?
            """,
            (current,),
        ).fetchone()[0]
        total_count = connection.execute(f"SELECT count({id_column}) FROM {table_name}").fetchone()[0]
        if int(unknown_count):
            issues.append(
                WorkspaceDoctorIssue(
                    issue_id=f"{table_name}_unknown_code_version",
                    scope="runs",
                    severity="warn",
                    message=f"{table_name} contains runs without code_version",
                    details={
                        "table": table_name,
                        "current_code_version": current,
                        "current_count": int(current_count),
                        "unknown_count": int(unknown_count),
                        "stale_count": int(stale_count),
                        "total_count": int(total_count),
                    },
                    recommended_actions=(
                        "prune-stale-runs --keep-current-code-version --keep-latest-code-versions 3 --dry-run",
                    ),
                )
            )
        if int(stale_count):
            issues.append(
                WorkspaceDoctorIssue(
                    issue_id=f"{table_name}_stale_code_version",
                    scope="runs",
                    severity="warn",
                    message=f"{table_name} contains runs from older code versions",
                    details={
                        "table": table_name,
                        "current_code_version": current,
                        "current_count": int(current_count),
                        "stale_count": int(stale_count),
                        "unknown_count": int(unknown_count),
                        "total_count": int(total_count),
                    },
                    recommended_actions=(
                        "prune-stale-runs --keep-current-code-version --keep-latest-code-versions 3 --dry-run",
                    ),
                )
            )
    return issues


def _sql_count_issue(
    connection: Connection,
    *,
    scope: str,
    issue_id: str,
    message: str,
    sql: str,
    action: str,
) -> list[WorkspaceDoctorIssue]:
    count = int(connection.execute(sql).fetchone()[0])
    if count <= 0:
        return []
    return [
        WorkspaceDoctorIssue(
            issue_id=issue_id,
            scope=scope,
            severity="warn",
            message=message,
            details={"count": count},
            recommended_actions=(action,),
        )
    ]


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


def _column_exists(connection: Connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return column_name in {str(row["name"]) for row in rows}


def _database_path(connection: Connection) -> Path:
    row = connection.execute("PRAGMA database_list").fetchone()
    if row is None:
        raise ValueError("connection has no attached database")
    return Path(str(row["file"]))
