from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from typing import Any

from .backup import SQLiteBackupManager
from .migrations import SchemaMigrator


@dataclass(frozen=True)
class RecoveryDrillReport:
    backup_path: str
    restored_path: str
    integrity_ok: bool
    schema_version: int
    required_tables: list[str]
    missing_tables: list[str]
    table_counts: dict[str, int]
    cleanup_performed: bool
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
)


def run_recovery_drill(
    backup_path: str | Path,
    *,
    workspace_dir: str | Path | None = None,
    required_tables: tuple[str, ...] = DEFAULT_REQUIRED_TABLES,
    keep_restored_copy: bool = False,
) -> RecoveryDrillReport:
    """Restore a backup into an isolated workspace and verify readable state.

    The live database is never modified. The restored copy is deleted by
    default after verification; set `keep_restored_copy=True` for inspection.
    """

    backup = Path(backup_path)
    if not SQLiteBackupManager.verify(backup):
        raise ValueError("backup failed SQLite integrity verification")
    owned_workspace = workspace_dir is None
    workspace = Path(workspace_dir) if workspace_dir is not None else Path(mkdtemp(prefix="agent-kb-recovery-"))
    workspace.mkdir(parents=True, exist_ok=True)
    restored = workspace / f"restored-{backup.name}"
    SQLiteBackupManager(restored).restore(backup)

    connection = sqlite3.connect(restored)
    try:
        integrity_row = connection.execute("PRAGMA integrity_check").fetchone()
        integrity_ok = bool(integrity_row and str(integrity_row[0]).lower() == "ok")
        available = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
        missing = sorted(table for table in required_tables if table not in available)
        counts: dict[str, int] = {}
        for table in required_tables:
            if table not in available:
                continue
            row = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
            counts[table] = int(row[0] or 0)
        schema_version = SchemaMigrator(connection).current_version()
    finally:
        connection.close()

    status = "passed" if integrity_ok and not missing else "failed"
    cleanup_performed = False
    report_path = str(restored)
    if not keep_restored_copy:
        restored.unlink(missing_ok=True)
        if owned_workspace:
            rmtree(workspace, ignore_errors=True)
        cleanup_performed = True

    return RecoveryDrillReport(
        backup_path=str(backup),
        restored_path=report_path,
        integrity_ok=integrity_ok,
        schema_version=schema_version,
        required_tables=list(required_tables),
        missing_tables=missing,
        table_counts=counts,
        cleanup_performed=cleanup_performed,
        status=status,
    )
