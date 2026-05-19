from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from sqlite3 import Connection

from .closed_loop_store import _runtime_code_version, utc_now
from .config import AppPaths
from .db import connect


@dataclass(frozen=True)
class RunPruneItem:
    table: str
    status: str
    dry_run: bool
    candidate_count: int
    deleted_count: int
    candidate_ids: tuple[str, ...]
    candidate_ids_truncated: bool
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RunPruneReport:
    dry_run: bool
    current_code_version: str
    suite_id: str | None
    older_than_days: int | None
    keep_current_code_version: bool
    keep_latest_code_versions: int
    allow_without_current_baseline: bool
    archive_path: str | None
    started_at: str
    finished_at: str
    status: str
    summary: dict[str, int]
    items: tuple[RunPruneItem, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "dry_run": self.dry_run,
            "current_code_version": self.current_code_version,
            "suite_id": self.suite_id,
            "older_than_days": self.older_than_days,
            "keep_current_code_version": self.keep_current_code_version,
            "keep_latest_code_versions": self.keep_latest_code_versions,
            "allow_without_current_baseline": self.allow_without_current_baseline,
            "archive_path": self.archive_path,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "summary": self.summary,
            "items": [item.to_dict() for item in self.items],
        }


def prune_stale_runs(
    workspace_root: Path,
    *,
    suite_id: str | None = None,
    older_than_days: int | None = None,
    keep_current_code_version: bool = True,
    keep_latest_code_versions: int = 0,
    allow_without_current_baseline: bool = False,
    archive_dir: Path | None = None,
    dry_run: bool = True,
) -> RunPruneReport:
    started_at = utc_now()
    current_code_version = _runtime_code_version()
    cutoff = _cutoff(older_than_days)
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        retrieval_ids = _candidate_retrieval_run_ids(
            connection,
            current_code_version=current_code_version,
            cutoff=cutoff,
            keep_current_code_version=keep_current_code_version,
            keep_latest_code_versions=keep_latest_code_versions,
        ) if suite_id is None else []
        eval_ids = _candidate_eval_run_ids(
            connection,
            current_code_version=current_code_version,
            suite_id=suite_id,
            cutoff=cutoff,
            keep_current_code_version=keep_current_code_version,
            keep_latest_code_versions=keep_latest_code_versions,
        )
        baseline = _current_baseline_counts(
            connection,
            current_code_version=current_code_version,
            suite_id=suite_id,
        )
        blocked_reason = _baseline_block_reason(
            baseline,
            retrieval_ids=retrieval_ids,
            eval_ids=eval_ids,
            suite_id=suite_id,
            dry_run=dry_run,
            allow_without_current_baseline=allow_without_current_baseline,
        )
        archive_path = None
        if blocked_reason is None and not dry_run and (retrieval_ids or eval_ids):
            archive_path = _archive_prune_candidates(
                connection,
                paths,
                retrieval_ids=retrieval_ids,
                eval_ids=eval_ids,
                archive_dir=archive_dir,
                current_code_version=current_code_version,
                suite_id=suite_id,
                older_than_days=older_than_days,
                keep_current_code_version=keep_current_code_version,
                keep_latest_code_versions=keep_latest_code_versions,
            )
        retrieval_item = _retrieval_runs_item(
            connection,
            suite_id=suite_id,
            ids=retrieval_ids,
            dry_run=dry_run,
            blocked_reason=blocked_reason,
        )
        eval_item, eval_results_item = _eval_runs_items(
            connection,
            eval_ids=eval_ids,
            dry_run=dry_run,
            blocked_reason=blocked_reason,
        )
        if blocked_reason is None and not dry_run:
            connection.commit()
    finally:
        connection.close()

    items = (retrieval_item, eval_results_item, eval_item)
    finished_at = utc_now()
    summary = _summary(items)
    return RunPruneReport(
        dry_run=dry_run,
        current_code_version=current_code_version,
        suite_id=suite_id,
        older_than_days=older_than_days,
        keep_current_code_version=keep_current_code_version,
        keep_latest_code_versions=max(0, int(keep_latest_code_versions or 0)),
        allow_without_current_baseline=allow_without_current_baseline,
        archive_path=str(archive_path) if archive_path is not None else None,
        started_at=started_at,
        finished_at=finished_at,
        status="warn" if blocked_reason else "ok",
        summary={**summary, **baseline},
        items=items,
    )


def _retrieval_runs_item(
    connection: Connection,
    *,
    suite_id: str | None,
    ids: list[str],
    dry_run: bool,
    blocked_reason: str | None,
) -> RunPruneItem:
    if suite_id:
        return RunPruneItem(
            table="retrieval_runs",
            status="skipped",
            dry_run=dry_run,
            candidate_count=0,
            deleted_count=0,
            candidate_ids=(),
            candidate_ids_truncated=False,
            message="retrieval_runs has no suite_id column; skipped because suite_id filter was provided",
        )
    deleted_count = 0
    if ids and not dry_run and blocked_reason is None:
        connection.executemany("DELETE FROM retrieval_runs WHERE run_id = ?", [(run_id,) for run_id in ids])
        deleted_count = len(ids)
    status = "planned" if dry_run else "blocked" if blocked_reason else "done"
    return RunPruneItem(
        table="retrieval_runs",
        status=status,
        dry_run=dry_run,
        candidate_count=len(ids),
        deleted_count=deleted_count,
        candidate_ids=_sample_ids(ids),
        candidate_ids_truncated=_ids_truncated(ids),
        message=blocked_reason or "retrieval stale/unknown runs selected by code_version and age filters",
    )


def _eval_runs_items(
    connection: Connection,
    *,
    eval_ids: list[str],
    dry_run: bool,
    blocked_reason: str | None,
) -> tuple[RunPruneItem, RunPruneItem]:
    eval_result_count = _eval_result_count(connection, eval_ids)
    deleted_eval_results = 0
    deleted_eval_runs = 0
    if eval_ids and not dry_run and blocked_reason is None:
        connection.executemany("DELETE FROM eval_results WHERE eval_run_id = ?", [(eval_id,) for eval_id in eval_ids])
        deleted_eval_results = eval_result_count
        connection.executemany("DELETE FROM eval_runs WHERE eval_run_id = ?", [(eval_id,) for eval_id in eval_ids])
        deleted_eval_runs = len(eval_ids)
    status = "planned" if dry_run else "blocked" if blocked_reason else "done"
    eval_results_item = RunPruneItem(
        table="eval_results",
        status=status,
        dry_run=dry_run,
        candidate_count=eval_result_count,
        deleted_count=deleted_eval_results,
        candidate_ids=_sample_ids(eval_ids),
        candidate_ids_truncated=_ids_truncated(eval_ids),
        message=blocked_reason or "eval_results selected through stale/unknown eval_runs",
    )
    eval_runs_item = RunPruneItem(
        table="eval_runs",
        status=status,
        dry_run=dry_run,
        candidate_count=len(eval_ids),
        deleted_count=deleted_eval_runs,
        candidate_ids=_sample_ids(eval_ids),
        candidate_ids_truncated=_ids_truncated(eval_ids),
        message=blocked_reason or "eval stale/unknown runs selected by code_version, suite_id, and age filters",
    )
    return eval_runs_item, eval_results_item


def _current_baseline_counts(
    connection: Connection,
    *,
    current_code_version: str,
    suite_id: str | None,
) -> dict[str, int]:
    retrieval_count = 0
    if suite_id is None:
        retrieval_count = int(
            connection.execute(
                "SELECT count(*) FROM retrieval_runs WHERE code_version = ?",
                (current_code_version,),
            ).fetchone()[0]
        )
    if suite_id:
        eval_count = int(
            connection.execute(
                "SELECT count(*) FROM eval_runs WHERE code_version = ? AND suite_id = ?",
                (current_code_version, suite_id),
            ).fetchone()[0]
        )
    else:
        eval_count = int(
            connection.execute(
                "SELECT count(*) FROM eval_runs WHERE code_version = ?",
                (current_code_version,),
            ).fetchone()[0]
        )
    return {
        "current_retrieval_runs": retrieval_count,
        "current_eval_runs": eval_count,
    }


def _baseline_block_reason(
    baseline: dict[str, int],
    *,
    retrieval_ids: list[str],
    eval_ids: list[str],
    suite_id: str | None,
    dry_run: bool,
    allow_without_current_baseline: bool,
) -> str | None:
    if dry_run or allow_without_current_baseline:
        return None
    missing: list[str] = []
    if suite_id is None and retrieval_ids and baseline["current_retrieval_runs"] <= 0:
        missing.append("retrieval_runs")
    if eval_ids and baseline["current_eval_runs"] <= 0:
        missing.append("eval_runs")
    if not missing:
        return None
    return (
        "prune blocked: current code version has no baseline rows in "
        + ", ".join(missing)
        + "; run current-version evals first or pass --allow-without-current-baseline"
    )


def _candidate_retrieval_run_ids(
    connection: Connection,
    *,
    current_code_version: str,
    cutoff: datetime | None,
    keep_current_code_version: bool,
    keep_latest_code_versions: int,
) -> list[str]:
    rows = connection.execute(
        """
        SELECT run_id, code_version, created_at
        FROM retrieval_runs
        ORDER BY created_at ASC, run_id ASC
        """
    ).fetchall()
    protected_versions = _latest_code_versions(rows, "code_version", "created_at", keep_latest_code_versions)
    return [
        str(row["run_id"])
        for row in rows
        if _is_prune_candidate(
            str(row["code_version"] or ""),
            row["created_at"],
            current_code_version=current_code_version,
            cutoff=cutoff,
            keep_current_code_version=keep_current_code_version,
            protected_versions=protected_versions,
        )
    ]


def _candidate_eval_run_ids(
    connection: Connection,
    *,
    current_code_version: str,
    suite_id: str | None,
    cutoff: datetime | None,
    keep_current_code_version: bool,
    keep_latest_code_versions: int,
) -> list[str]:
    params: list[object] = []
    suite_filter = ""
    if suite_id:
        suite_filter = "WHERE suite_id = ?"
        params.append(suite_id)
    rows = connection.execute(
        f"""
        SELECT eval_run_id, suite_id, code_version, started_at
        FROM eval_runs
        {suite_filter}
        ORDER BY started_at ASC, eval_run_id ASC
        """,
        params,
    ).fetchall()
    protected_versions = _latest_code_versions(rows, "code_version", "started_at", keep_latest_code_versions)
    return [
        str(row["eval_run_id"])
        for row in rows
        if _is_prune_candidate(
            str(row["code_version"] or ""),
            row["started_at"],
            current_code_version=current_code_version,
            cutoff=cutoff,
            keep_current_code_version=keep_current_code_version,
            protected_versions=protected_versions,
        )
    ]


def _is_prune_candidate(
    code_version: str,
    timestamp: object,
    *,
    current_code_version: str,
    cutoff: datetime | None,
    keep_current_code_version: bool,
    protected_versions: set[str] | None = None,
) -> bool:
    normalized_code_version = code_version.strip()
    if keep_current_code_version and normalized_code_version == current_code_version:
        return False
    if normalized_code_version and normalized_code_version == current_code_version:
        return False
    if normalized_code_version and protected_versions and normalized_code_version in protected_versions:
        return False
    if cutoff is not None:
        parsed = _parse_datetime(timestamp)
        if parsed is None or parsed > cutoff:
            return False
    return True


def _latest_code_versions(
    rows: list[object],
    code_version_key: str,
    timestamp_key: str,
    keep_latest_code_versions: int,
) -> set[str]:
    limit = max(0, int(keep_latest_code_versions or 0))
    if limit <= 0:
        return set()
    latest_by_version: dict[str, datetime] = {}
    for row in rows:
        version = str(row[code_version_key] or "").strip()
        if not version:
            continue
        parsed = _parse_datetime(row[timestamp_key])
        if parsed is None:
            continue
        current = latest_by_version.get(version)
        if current is None or parsed > current:
            latest_by_version[version] = parsed
    ordered = sorted(latest_by_version.items(), key=lambda item: item[1], reverse=True)
    return {version for version, _ in ordered[:limit]}


def _eval_result_count(connection: Connection, eval_ids: list[str]) -> int:
    if not eval_ids:
        return 0
    placeholders = ", ".join("?" for _ in eval_ids)
    return int(
        connection.execute(
            f"SELECT count(*) FROM eval_results WHERE eval_run_id IN ({placeholders})",
            eval_ids,
        ).fetchone()[0]
    )


def _archive_prune_candidates(
    connection: Connection,
    paths: AppPaths,
    *,
    retrieval_ids: list[str],
    eval_ids: list[str],
    archive_dir: Path | None,
    current_code_version: str,
    suite_id: str | None,
    older_than_days: int | None,
    keep_current_code_version: bool,
    keep_latest_code_versions: int,
) -> Path:
    target_dir = archive_dir or paths.root / "quarantine" / "run-prune"
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive_path = target_dir / f"run-prune-{timestamp}.json"
    index = 1
    while archive_path.exists():
        archive_path = target_dir / f"run-prune-{timestamp}-{index}.json"
        index += 1
    payload = {
        "created_at": utc_now(),
        "current_code_version": current_code_version,
        "filters": {
            "suite_id": suite_id,
            "older_than_days": older_than_days,
            "keep_current_code_version": keep_current_code_version,
            "keep_latest_code_versions": keep_latest_code_versions,
        },
        "retrieval_runs": _rows_by_ids(connection, "retrieval_runs", "run_id", retrieval_ids),
        "eval_runs": _rows_by_ids(connection, "eval_runs", "eval_run_id", eval_ids),
        "eval_results": _rows_by_ids(connection, "eval_results", "eval_run_id", eval_ids),
    }
    archive_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return archive_path


def _rows_by_ids(connection: Connection, table_name: str, id_column: str, ids: list[str]) -> list[dict[str, object]]:
    if not ids:
        return []
    placeholders = ", ".join("?" for _ in ids)
    rows = connection.execute(
        f"SELECT * FROM {table_name} WHERE {id_column} IN ({placeholders}) ORDER BY {id_column}",
        ids,
    ).fetchall()
    return [dict(row) for row in rows]


def _cutoff(older_than_days: int | None) -> datetime | None:
    if older_than_days is None:
        return None
    return datetime.now(UTC) - timedelta(days=max(0, int(older_than_days)))


def _parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _summary(items: tuple[RunPruneItem, ...]) -> dict[str, int]:
    return {
        "retrieval_runs": sum(item.candidate_count for item in items if item.table == "retrieval_runs"),
        "eval_runs": sum(item.candidate_count for item in items if item.table == "eval_runs"),
        "eval_results": sum(item.candidate_count for item in items if item.table == "eval_results"),
        "deleted_retrieval_runs": sum(item.deleted_count for item in items if item.table == "retrieval_runs"),
        "deleted_eval_runs": sum(item.deleted_count for item in items if item.table == "eval_runs"),
        "deleted_eval_results": sum(item.deleted_count for item in items if item.table == "eval_results"),
        "skipped": sum(1 for item in items if item.status == "skipped"),
    }


def _sample_ids(ids: list[str], limit: int = 50) -> tuple[str, ...]:
    return tuple(ids[:limit])


def _ids_truncated(ids: list[str], limit: int = 50) -> bool:
    return len(ids) > limit
