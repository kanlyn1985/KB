from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from agent_kb.storage.recovery import (
    DEFAULT_REQUIRED_TABLES as RECOVERY_REQUIRED_TABLES,
    run_recovery_drill,
)

from .readiness import DEFAULT_REQUIRED_TABLES as READINESS_REQUIRED_TABLES
from .readiness import evaluate_readiness


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-kb-ops",
        description="Agent KB Core operational verification CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    readiness = subparsers.add_parser(
        "readiness",
        help="Run a read-only release-readiness gate against one SQLite knowledge store.",
    )
    readiness.add_argument("--db", type=Path, required=True)
    readiness.add_argument("--min-schema-version", type=int, default=8)
    readiness.add_argument("--require-documents", action="store_true")
    readiness.add_argument("--require-backup", action="store_true")
    readiness.add_argument("--max-failed-jobs", type=int, default=0)
    readiness.add_argument("--max-stale-running-jobs", type=int, default=0)
    readiness.add_argument("--stale-job-age-seconds", type=int, default=900)
    readiness.add_argument("--require-table", action="append", dest="required_tables")
    readiness.add_argument("--output", type=Path)

    recovery = subparsers.add_parser(
        "recovery-drill",
        help="Restore a backup in an isolated workspace and verify readable state.",
    )
    recovery.add_argument("--backup-path", type=Path, required=True)
    recovery.add_argument("--workspace-dir", type=Path)
    recovery.add_argument("--keep-restored-copy", action="store_true")
    recovery.add_argument("--require-table", action="append", dest="required_tables")
    recovery.add_argument("--output", type=Path)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "readiness":
        report = evaluate_readiness(
            args.db,
            min_schema_version=max(0, args.min_schema_version),
            require_documents=args.require_documents,
            require_backup=args.require_backup,
            max_failed_jobs=max(0, args.max_failed_jobs),
            max_stale_running_jobs=max(0, args.max_stale_running_jobs),
            stale_job_age_seconds=max(1, args.stale_job_age_seconds),
            required_tables=tuple(args.required_tables or READINESS_REQUIRED_TABLES),
        )
        _emit(report.to_dict(), args.output)
        return 0 if report.ready else 1

    if args.command == "recovery-drill":
        report = run_recovery_drill(
            args.backup_path,
            workspace_dir=args.workspace_dir,
            required_tables=tuple(args.required_tables or RECOVERY_REQUIRED_TABLES),
            keep_restored_copy=args.keep_restored_copy,
        )
        _emit(report.to_dict(), args.output)
        return 0 if report.status == "passed" else 1

    parser.error(f"unsupported command: {args.command}")
    return 2


def _emit(payload: dict[str, object], output: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    raise SystemExit(main())
