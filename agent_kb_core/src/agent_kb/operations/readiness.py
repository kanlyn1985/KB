from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReadinessCheck:
    check_id: str
    passed: bool
    severity: str
    detail: str
    observed: Any = None
    expected: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReadinessReport:
    database_path: str
    generated_at: str
    ready: bool
    schema_version: int
    checks: list[ReadinessCheck]
    counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_path": self.database_path,
            "generated_at": self.generated_at,
            "ready": self.ready,
            "schema_version": self.schema_version,
            "checks": [item.to_dict() for item in self.checks],
            "counts": dict(self.counts),
        }


DEFAULT_REQUIRED_TABLES: tuple[str, ...] = (
    "schema_migrations",
    "documents",
    "document_versions",
    "evidence",
    "facts",
    "object_projections",
    "retrieval_cards",
    "embedding_vectors",
    "graph_edges",
    "background_jobs",
    "audit_events",
    "backup_history",
    "legal_holds",
    "retention_runs",
)

COUNTED_TABLES: tuple[str, ...] = (
    "documents",
    "document_versions",
    "evidence",
    "facts",
    "object_projections",
    "retrieval_cards",
    "embedding_vectors",
    "graph_edges",
    "background_jobs",
    "audit_events",
    "backup_history",
    "legal_holds",
    "retention_runs",
)


def evaluate_readiness(
    db_path: str | Path,
    *,
    min_schema_version: int = 8,
    require_documents: bool = False,
    require_backup: bool = False,
    max_failed_jobs: int = 0,
    max_stale_running_jobs: int = 0,
    stale_job_age_seconds: int = 900,
    required_tables: tuple[str, ...] = DEFAULT_REQUIRED_TABLES,
    now: datetime | None = None,
) -> ReadinessReport:
    """Evaluate deployment readiness without mutating the database.

    The database is opened in SQLite read-only mode. Failed error-severity
    checks make the report not ready; warning checks are retained in the
    report without blocking release.
    """

    path = Path(db_path)
    generated = (now or datetime.now(UTC)).replace(microsecond=0)
    checks: list[ReadinessCheck] = []
    counts: dict[str, int] = {}

    exists = path.exists() and path.is_file() and path.stat().st_size > 0
    checks.append(
        ReadinessCheck(
            check_id="database_exists",
            passed=exists,
            severity="error",
            detail="database file exists and is non-empty" if exists else "database file is missing or empty",
            observed=path.stat().st_size if path.exists() and path.is_file() else 0,
            expected="> 0 bytes",
        )
    )
    if not exists:
        return ReadinessReport(
            database_path=str(path),
            generated_at=_iso(generated),
            ready=False,
            schema_version=0,
            checks=checks,
            counts=counts,
        )

    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        integrity_row = connection.execute("PRAGMA integrity_check").fetchone()
        integrity_ok = bool(integrity_row and str(integrity_row[0]).lower() == "ok")
        checks.append(
            ReadinessCheck(
                check_id="sqlite_integrity",
                passed=integrity_ok,
                severity="error",
                detail="SQLite integrity check passed" if integrity_ok else "SQLite integrity check failed",
                observed=str(integrity_row[0]) if integrity_row else None,
                expected="ok",
            )
        )

        available_tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
        }
        missing_tables = sorted(table for table in required_tables if table not in available_tables)
        checks.append(
            ReadinessCheck(
                check_id="required_tables",
                passed=not missing_tables,
                severity="error",
                detail="all required tables are present" if not missing_tables else "required tables are missing",
                observed=missing_tables,
                expected=list(required_tables),
            )
        )

        schema_version = _schema_version(connection, available_tables)
        checks.append(
            ReadinessCheck(
                check_id="schema_version",
                passed=schema_version >= min_schema_version,
                severity="error",
                detail=f"schema version is {schema_version}",
                observed=schema_version,
                expected=f">= {min_schema_version}",
            )
        )

        for table in COUNTED_TABLES:
            if table in available_tables:
                counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] or 0)

        active_documents = _scalar(
            connection,
            "SELECT COUNT(*) FROM documents WHERE status = 'active'",
            available_tables,
            "documents",
        )
        checks.append(
            ReadinessCheck(
                check_id="active_documents",
                passed=(active_documents > 0) if require_documents else True,
                severity="error" if require_documents else "info",
                detail=f"{active_documents} active logical documents",
                observed=active_documents,
                expected="> 0" if require_documents else ">= 0",
            )
        )

        if require_documents:
            for table in ("evidence", "facts", "retrieval_cards"):
                value = counts.get(table, 0)
                checks.append(
                    ReadinessCheck(
                        check_id=f"populated_{table}",
                        passed=value > 0,
                        severity="error",
                        detail=f"{table} contains {value} rows",
                        observed=value,
                        expected="> 0",
                    )
                )

        failed_jobs = _scalar(
            connection,
            "SELECT COUNT(*) FROM background_jobs WHERE status = 'failed'",
            available_tables,
            "background_jobs",
        )
        checks.append(
            ReadinessCheck(
                check_id="failed_jobs",
                passed=failed_jobs <= max_failed_jobs,
                severity="error",
                detail=f"{failed_jobs} failed background jobs",
                observed=failed_jobs,
                expected=f"<= {max_failed_jobs}",
            )
        )

        stale_before = _iso(generated - timedelta(seconds=max(1, stale_job_age_seconds)))
        stale_running = _scalar(
            connection,
            """
            SELECT COUNT(*) FROM background_jobs
            WHERE status = 'running' AND (locked_at IS NULL OR locked_at < ?)
            """,
            available_tables,
            "background_jobs",
            (stale_before,),
        )
        checks.append(
            ReadinessCheck(
                check_id="stale_running_jobs",
                passed=stale_running <= max_stale_running_jobs,
                severity="error",
                detail=f"{stale_running} stale running jobs",
                observed=stale_running,
                expected=f"<= {max_stale_running_jobs}",
            )
        )

        latest_backup = None
        if "backup_history" in available_tables:
            latest_backup = connection.execute(
                "SELECT path, status, created_at FROM backup_history ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        backup_ok = bool(
            latest_backup
            and str(latest_backup["status"]) == "verified"
            and Path(str(latest_backup["path"])).exists()
        )
        checks.append(
            ReadinessCheck(
                check_id="verified_backup",
                passed=backup_ok if require_backup else True,
                severity="error" if require_backup else "info",
                detail=(
                    f"latest verified backup: {latest_backup['created_at']}"
                    if backup_ok and latest_backup
                    else "no accessible verified backup found"
                ),
                observed=dict(latest_backup) if latest_backup else None,
                expected="accessible verified backup" if require_backup else "optional",
            )
        )

        active_holds = _scalar(
            connection,
            "SELECT COUNT(*) FROM legal_holds WHERE status = 'active'",
            available_tables,
            "legal_holds",
        )
        checks.append(
            ReadinessCheck(
                check_id="active_legal_holds",
                passed=True,
                severity="info",
                detail=f"{active_holds} active legal holds",
                observed=active_holds,
                expected="informational",
            )
        )
    finally:
        connection.close()

    ready = all(item.passed for item in checks if item.severity == "error")
    return ReadinessReport(
        database_path=str(path),
        generated_at=_iso(generated),
        ready=ready,
        schema_version=schema_version,
        checks=checks,
        counts=counts,
    )


def _schema_version(connection: sqlite3.Connection, available_tables: set[str]) -> int:
    if "schema_migrations" not in available_tables:
        return 0
    row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0] or 0)


def _scalar(
    connection: sqlite3.Connection,
    statement: str,
    available_tables: set[str],
    required_table: str,
    parameters: tuple[Any, ...] = (),
) -> int:
    if required_table not in available_tables:
        return 0
    row = connection.execute(statement, parameters).fetchone()
    return int(row[0] or 0)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
