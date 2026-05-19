from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .config import AppPaths
from .db import apply_schema, connect, list_tables


@dataclass(frozen=True)
class ResetWorkspaceResult:
    deleted_rows: dict[str, int]
    deleted_files: dict[str, int]
    keep_raw: bool


def reset_workspace_data(workspace_root: Path, *, keep_raw: bool = True) -> ResetWorkspaceResult:
    paths = AppPaths.from_root(workspace_root)
    deleted_rows: dict[str, int] = {}
    try:
        connection = connect(paths.db_file)
        try:
            preferred_order = [
                "edge_evidence_map",
                "fact_evidence_map",
                "source_unit_evidence_map",
                "source_unit_fact_map",
                "repair_tasks",
                "eval_results",
                "eval_runs",
                "retrieval_runs",
                "golden_cases",
                "source_units",
                "graph_edges",
                "wiki_pages",
                "entities",
                "facts",
                "evidence",
                "blocks",
                "pages",
                "quality_reports",
                "jobs",
                "audit_log",
                "dependencies",
                "documents",
                "system_counters",
            ]
            existing_tables = list_tables(connection)
            ordered_tables = [table for table in preferred_order if table in existing_tables]
            ordered_tables.extend(table for table in existing_tables if table not in ordered_tables)
            for table in ordered_tables:
                count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                deleted_rows[table] = int(count)
                connection.execute(f"DELETE FROM {table}")
            connection.commit()
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        if paths.db_file.exists():
            paths.db_file.unlink()
        connection = connect(paths.db_file)
        try:
            schema_path = Path(__file__).with_name("schema.sql")
            apply_schema(connection, schema_path)
        finally:
            connection.close()
        deleted_rows["database_recreated"] = 1

    deleted_files = {
        "normalized": _clear_directory(paths.normalized),
        "evidence": _clear_directory(paths.evidence),
        "facts": _clear_directory(paths.facts),
        "wiki": _clear_directory(paths.wiki),
        "coverage_reports": _clear_directory(paths.coverage_reports),
        "review_queue": _clear_directory(paths.review_queue),
        "quality_reports": _clear_directory(paths.quality_reports),
        "logs": _clear_directory(paths.logs),
    }
    if not keep_raw:
        deleted_files["raw"] = _clear_directory(paths.raw)

    return ResetWorkspaceResult(
        deleted_rows=deleted_rows,
        deleted_files=deleted_files,
        keep_raw=keep_raw,
    )


def _clear_directory(directory: Path) -> int:
    if not directory.exists():
        return 0
    deleted = 0
    for child in directory.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
            deleted += 1
        else:
            child.unlink()
            deleted += 1
    return deleted
