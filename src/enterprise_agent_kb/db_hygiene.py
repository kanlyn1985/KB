from __future__ import annotations

import shutil
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from .closed_loop_store import utc_now
from .config import AppPaths


@dataclass(frozen=True)
class DatabaseHygieneItem:
    path: str
    reason: str
    status: str
    dry_run: bool
    size_bytes: int | None
    quarantine_path: str | None
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DatabaseHygieneReport:
    dry_run: bool
    workspace_root: str
    database_path: str
    started_at: str
    finished_at: str
    status: str
    summary: dict[str, int]
    items: tuple[DatabaseHygieneItem, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "dry_run": self.dry_run,
            "workspace_root": self.workspace_root,
            "database_path": self.database_path,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "summary": self.summary,
            "items": [item.to_dict() for item in self.items],
        }


def quarantine_suspicious_db_files(workspace_root: Path, *, dry_run: bool = True) -> DatabaseHygieneReport:
    started_at = utc_now()
    paths = AppPaths.from_root(workspace_root)
    items: list[DatabaseHygieneItem] = []
    for db_file in _candidate_db_files(paths):
        reason = _suspicious_reason(paths, db_file)
        if reason is None:
            continue
        quarantine_path = _quarantine_path(paths, db_file)
        if dry_run:
            items.append(
                _item(
                    paths,
                    db_file,
                    reason=reason,
                    status="planned",
                    dry_run=True,
                    quarantine_path=quarantine_path,
                    message="database file would be moved to quarantine",
                )
            )
            continue
        size_bytes = _file_size(db_file)
        quarantine_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(db_file), str(quarantine_path))
        items.append(
            _item(
                paths,
                quarantine_path,
                reason=reason,
                status="quarantined",
                dry_run=False,
                quarantine_path=quarantine_path,
                message="database file moved to quarantine",
                original_path=db_file,
                size_bytes=size_bytes,
            )
        )
    finished_at = utc_now()
    summary = {
        "planned": sum(1 for item in items if item.status == "planned"),
        "quarantined": sum(1 for item in items if item.status == "quarantined"),
        "skipped": sum(1 for item in items if item.status == "skipped"),
    }
    return DatabaseHygieneReport(
        dry_run=dry_run,
        workspace_root=str(paths.root),
        database_path=str(paths.db_file),
        started_at=started_at,
        finished_at=finished_at,
        status="ok",
        summary=summary,
        items=tuple(items),
    )


def _candidate_db_files(paths: AppPaths) -> tuple[Path, ...]:
    if not paths.root.exists():
        return ()
    candidates = {path.resolve() for path in paths.root.glob("*.db")}
    if paths.db_dir.exists():
        candidates.update(path.resolve() for path in paths.db_dir.glob("*.db"))
    primary = paths.db_file.resolve()
    return tuple(sorted(path for path in candidates if path != primary))


def _suspicious_reason(paths: AppPaths, db_file: Path) -> str | None:
    try:
        size = db_file.stat().st_size
    except OSError:
        return "unreadable_db_file"
    if size == 0:
        return "empty_db_file"
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
        return "unreadable_db_file"
    if int(table_count) == 0:
        return "empty_schema_db_file"
    return None


def _quarantine_path(paths: AppPaths, db_file: Path) -> Path:
    relative = _relative_to_root(paths.root, db_file)
    base = paths.root / "quarantine" / "db" / str(relative).replace(":", "").replace("\\", "__").replace("/", "__")
    if not base.exists():
        return base
    stem = base.stem
    suffix = base.suffix
    index = 1
    while True:
        candidate = base.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _item(
    paths: AppPaths,
    current_path: Path,
    *,
    reason: str,
    status: str,
    dry_run: bool,
    quarantine_path: Path,
    message: str,
    original_path: Path | None = None,
    size_bytes: int | None = None,
) -> DatabaseHygieneItem:
    path = original_path or current_path
    if size_bytes is None:
        size_bytes = _file_size(path)
    return DatabaseHygieneItem(
        path=str(_relative_to_root(paths.root, path)),
        reason=reason,
        status=status,
        dry_run=dry_run,
        size_bytes=size_bytes,
        quarantine_path=str(_relative_to_root(paths.root, quarantine_path)),
        message=message,
    )


def _file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def _relative_to_root(root: Path, path: Path) -> Path:
    try:
        return path.relative_to(root.resolve())
    except ValueError:
        return path
